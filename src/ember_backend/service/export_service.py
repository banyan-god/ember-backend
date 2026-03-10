from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from ember_backend.config.settings import Settings
from ember_backend.dto.api import (
    BulkExportSyncRequest,
    BulkExportSyncResponse,
    BulkExportSyncSummary,
    BulkExportSyncItemResult,
    ErrorPayload,
    ExportSyncRequest,
    ExportSyncResponse,
    NextSyncAdvice,
)
from ember_backend.exception.api_error import APIError
from ember_backend.repository.export_repository import ExportRepository
from ember_backend.security.token_service import AuthContext
from ember_backend.support.rate_limit import InMemoryRateLimiter


@dataclass(frozen=True)
class ReplayResponse:
    status_code: int
    body: dict


class ExportService:
    def __init__(
        self,
        repository: ExportRepository,
        settings: Settings,
        rate_limiter: InMemoryRateLimiter,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.rate_limiter = rate_limiter

    def sync(self, payload: ExportSyncRequest, auth: AuthContext, idempotency_key: str | None) -> ExportSyncResponse | ReplayResponse:
        return self._sync_internal(payload, auth, idempotency_key, enforce_rate_limit=True)

    def sync_bulk(self, payload: BulkExportSyncRequest, auth: AuthContext) -> BulkExportSyncResponse:
        self._enforce_rate_limit(auth.device_id)

        results: list[BulkExportSyncItemResult] = []
        ok_count = 0
        replayed_count = 0
        error_count = 0

        for index, item in enumerate(payload.items):
            try:
                parsed_payload = ExportSyncRequest.model_validate(item.payload)
                result = self._sync_internal(
                    parsed_payload,
                    auth,
                    item.idempotencyKey,
                    enforce_rate_limit=False,
                )
                if isinstance(result, ReplayResponse):
                    replayed_count += 1
                    results.append(self._to_replay_result(index, result))
                else:
                    ok_count += 1
                    results.append(
                        BulkExportSyncItemResult(
                            index=index,
                            status="ok",
                            received=result.received,
                            next=result.next,
                        )
                    )
            except ValidationError as exc:
                error_count += 1
                results.append(
                    BulkExportSyncItemResult(
                        index=index,
                        status="error",
                        error=ErrorPayload(
                            code="invalid_request",
                            message="Invalid request payload",
                            details=self._validation_details(exc),
                        ),
                    )
                )
            except APIError as exc:
                error_count += 1
                results.append(
                    BulkExportSyncItemResult(
                        index=index,
                        status="error",
                        error=ErrorPayload(
                            code=exc.code,
                            message=exc.message,
                            details=exc.details,
                        ),
                    )
                )
            except Exception:
                self.repository.rollback()
                error_count += 1
                results.append(
                    BulkExportSyncItemResult(
                        index=index,
                        status="error",
                        error=ErrorPayload(
                            code="internal_error",
                            message="Unexpected error processing item",
                        ),
                    )
                )

        return BulkExportSyncResponse(
            status="ok",
            summary=BulkExportSyncSummary(
                total=len(payload.items),
                ok=ok_count,
                replayed=replayed_count,
                error=error_count,
            ),
            results=results,
        )

    def _sync_internal(
        self,
        payload: ExportSyncRequest,
        auth: AuthContext,
        idempotency_key: str | None,
        *,
        enforce_rate_limit: bool,
    ) -> ExportSyncResponse | ReplayResponse:
        if enforce_rate_limit:
            self._enforce_rate_limit(auth.device_id)

        if payload.device.deviceId != auth.device_id:
            raise APIError(
                403,
                "forbidden",
                "Payload deviceId does not match authenticated device",
                details={"deviceId": payload.device.deviceId},
            )

        if idempotency_key is not None:
            self._validate_idempotency_key(idempotency_key)
            existing_recent = self.repository.get_recent_idempotency(auth.user_id, idempotency_key, within_hours=24)
            if existing_recent is not None:
                return ReplayResponse(
                    status_code=existing_recent.response_status,
                    body=json.loads(existing_recent.response_json),
                )

        device = self.repository.get_device_for_user(auth.user_id, auth.device_id)
        if device is None:
            raise APIError(401, "unauthorized", "Token is bound to unknown device")

        try:
            self.repository.update_device_seen(device, payload.device.platform)
            batch = self.repository.create_export_batch(auth.user_id, auth.device_id, payload)
            self.repository.persist_normalized(batch.id, payload)

            response = ExportSyncResponse(
                status="ok",
                received=self._count_received_records(payload),
                next=NextSyncAdvice(suggestedSyncAfterSeconds=self.settings.suggested_sync_after_seconds),
            )

            if idempotency_key is not None:
                self.repository.save_idempotency(
                    user_id=auth.user_id,
                    idempotency_key=idempotency_key,
                    response_json=response.model_dump_json(),
                    response_status=200,
                )

            self.repository.commit()
            return response
        except IntegrityError as exc:
            self.repository.rollback()
            raise APIError(409, "conflict", "Database conflict while processing export") from exc
        except Exception:
            self.repository.rollback()
            raise

    def _enforce_rate_limit(self, key: str) -> None:
        allowed, retry_after = self.rate_limiter.allow(key)
        if allowed:
            return
        raise APIError(
            429,
            "rate_limited",
            "Rate limit exceeded",
            details={"retryAfterSeconds": retry_after},
        )

    def _validate_idempotency_key(self, idempotency_key: str) -> None:
        try:
            parsed = uuid.UUID(idempotency_key)
            if parsed.version != 4:
                raise ValueError
        except ValueError as exc:
            raise APIError(400, "invalid_request", "Idempotency-Key must be a UUID v4") from exc

    def _to_replay_result(self, index: int, replay: ReplayResponse) -> BulkExportSyncItemResult:
        body = replay.body
        received_raw = body.get("received")
        received = received_raw if isinstance(received_raw, int) else 0
        suggested = self.settings.suggested_sync_after_seconds
        next_raw = body.get("next")
        if isinstance(next_raw, dict):
            suggested_raw = next_raw.get("suggestedSyncAfterSeconds")
            if isinstance(suggested_raw, int):
                suggested = suggested_raw
        return BulkExportSyncItemResult(
            index=index,
            status="replayed",
            received=received,
            next=NextSyncAdvice(suggestedSyncAfterSeconds=suggested),
        )

    @staticmethod
    def _validation_details(exc: ValidationError) -> dict[str, str]:
        details: dict[str, str] = {}
        for err in exc.errors():
            location = ".".join(str(part) for part in err.get("loc", []))
            details[location] = err.get("msg", "invalid")
        return details

    @staticmethod
    def _count_received_records(payload: ExportSyncRequest) -> int:
        health_count = 0
        finance_count = 0
        if payload.health:
            health_count += len(payload.health.samples)
            health_count += len(payload.health.characteristics)
            health_count += len(payload.health.activitySummaries)
            health_count += len(payload.health.userAnnotatedMedications)
        if payload.finance:
            finance_count += len(payload.finance.accounts)
            finance_count += len(payload.finance.transactions)
            finance_count += len(payload.finance.balances)
        return health_count + finance_count
