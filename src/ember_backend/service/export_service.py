from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from ember_backend.config.settings import Settings
from ember_backend.dto.api import ExportSyncRequest, ExportSyncResponse, NextSyncAdvice
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
