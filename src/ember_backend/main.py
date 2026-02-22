from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import and_, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ember_backend.auth import AuthContext, create_access_token, require_auth
from ember_backend.config import Settings, get_settings
from ember_backend.db import build_engine_and_session, create_schema, get_db_session
from ember_backend.errors import APIError, to_error_payload
from ember_backend.models import (
    ActivitySummary,
    AuthChallenge,
    Device,
    ExportBatch,
    ExportIdempotency,
    FinanceAccount,
    FinanceBalance,
    FinanceTransaction,
    HealthCharacteristic,
    HealthSample,
    PasskeyCredential,
    User,
)
from ember_backend.rate_limit import InMemoryRateLimiter
from ember_backend.schemas import (
    AuthenticateBeginRequest,
    AuthenticateBeginResponse,
    AuthenticateFinishRequest,
    ExportSyncRequest,
    ExportSyncResponse,
    NextSyncAdvice,
    RegisterBeginRequest,
    RegisterBeginResponse,
    RegisterFinishRequest,
    TokenResponse,
)
from ember_backend.utils import b64url_encode, utcnow
from ember_backend.webauthn_service import WebAuthnService, build_webauthn_service


def create_app(
    settings: Settings | None = None,
    *,
    engine_and_session: tuple[Any, sessionmaker[Session]] | None = None,
    webauthn_service: WebAuthnService | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    if engine_and_session is None:
        engine_and_session = build_engine_and_session(settings.sqlalchemy_database_url)
    engine, session_factory = engine_and_session

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        create_schema(app_instance.state.engine)
        yield

    app = FastAPI(title="Ember Backend", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.webauthn = webauthn_service or build_webauthn_service(settings)
    app.state.rate_limiter = InMemoryRateLimiter(settings.rate_limit_per_minute)

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(APIError)
    async def api_error_handler(_request: Request, exc: APIError):
        return JSONResponse(status_code=exc.status_code, content=to_error_payload(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_request: Request, exc: RequestValidationError):
        details: dict[str, str] = {}
        for err in exc.errors():
            location = ".".join(str(part) for part in err.get("loc", []))
            details[location] = err.get("msg", "invalid")
        return JSONResponse(
            status_code=400,
            content=to_error_payload("invalid_request", "Invalid request payload", details),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, _exc: Exception):
        return JSONResponse(
            status_code=500,
            content=to_error_payload("internal_error", "Unexpected server error"),
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/auth/passkey/register/begin", response_model=RegisterBeginResponse)
    def register_begin(payload: RegisterBeginRequest, db: Session = Depends(get_db_session)) -> RegisterBeginResponse:
        _enforce_rate_limit(app, payload.deviceId)
        user = _get_or_create_user_by_device(db, payload.deviceId)

        challenge = app.state.webauthn.generate_challenge()
        db.add(
            AuthChallenge(
                id=str(uuid.uuid4()),
                flow="register",
                user_id=user.id,
                device_id=payload.deviceId,
                challenge_b64=challenge,
                expires_at=utcnow() + timedelta(seconds=app.state.settings.challenge_ttl_seconds),
            )
        )
        db.commit()

        user_handle = b64url_encode(uuid.UUID(user.id).bytes)
        return RegisterBeginResponse(
            challenge=challenge,
            userId=user_handle,
            userName=f"{payload.deviceId}@ember.local",
            displayName="Ember User",
            rpId=app.state.settings.webauthn_rp_id,
            timeoutMs=60000,
        )

    @app.post("/v1/auth/passkey/register/finish", response_model=TokenResponse)
    def register_finish(payload: RegisterFinishRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
        _enforce_rate_limit(app, payload.deviceId)

        device = db.get(Device, payload.deviceId)
        if device is None:
            raise APIError(400, "invalid_request", "Unknown deviceId")

        challenge = _get_active_challenge(db, payload.deviceId, "register")
        expected_user_handle = b64url_encode(uuid.UUID(device.user_id).bytes)
        if payload.userId != expected_user_handle:
            raise APIError(400, "invalid_request", "userId does not match expected user handle")

        verification = app.state.webauthn.verify_registration(payload, challenge.challenge_b64)
        existing_credential = db.scalar(
            select(PasskeyCredential).where(PasskeyCredential.credential_id == payload.credentialId)
        )
        if existing_credential and existing_credential.user_id != device.user_id:
            raise APIError(409, "conflict", "credentialId is already bound to a different user")

        if existing_credential is None:
            db.add(
                PasskeyCredential(
                    credential_id=payload.credentialId,
                    user_id=device.user_id,
                    user_handle=payload.userId,
                    public_key=verification.public_key,
                    sign_count=verification.sign_count,
                    rp_id=app.state.settings.webauthn_rp_id,
                )
            )
        else:
            existing_credential.public_key = verification.public_key
            existing_credential.sign_count = verification.sign_count
            existing_credential.user_handle = payload.userId
            existing_credential.rp_id = app.state.settings.webauthn_rp_id

        challenge.used_at = utcnow()
        device.last_seen = utcnow()
        db.commit()

        token = create_access_token(app.state.settings, user_id=device.user_id, device_id=device.id)
        return TokenResponse(token=token)

    @app.post("/v1/auth/passkey/authenticate/begin", response_model=AuthenticateBeginResponse)
    def authenticate_begin(payload: AuthenticateBeginRequest, db: Session = Depends(get_db_session)) -> AuthenticateBeginResponse:
        _enforce_rate_limit(app, payload.deviceId)

        device = db.get(Device, payload.deviceId)
        if device is None:
            raise APIError(400, "invalid_request", "Unknown deviceId")
        credentials = db.scalars(
            select(PasskeyCredential).where(PasskeyCredential.user_id == device.user_id).order_by(PasskeyCredential.id.asc())
        ).all()
        if not credentials:
            raise APIError(400, "invalid_request", "No passkey credentials available for this device")

        challenge = app.state.webauthn.generate_challenge()
        db.add(
            AuthChallenge(
                id=str(uuid.uuid4()),
                flow="authenticate",
                user_id=device.user_id,
                device_id=device.id,
                challenge_b64=challenge,
                expires_at=utcnow() + timedelta(seconds=app.state.settings.challenge_ttl_seconds),
            )
        )
        device.last_seen = utcnow()
        db.commit()

        return AuthenticateBeginResponse(
            challenge=challenge,
            rpId=app.state.settings.webauthn_rp_id,
            allowCredentials=[cred.credential_id for cred in credentials],
            timeoutMs=60000,
        )

    @app.post("/v1/auth/passkey/authenticate/finish", response_model=TokenResponse)
    def authenticate_finish(payload: AuthenticateFinishRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
        _enforce_rate_limit(app, payload.deviceId)

        device = db.get(Device, payload.deviceId)
        if device is None:
            raise APIError(400, "invalid_request", "Unknown deviceId")

        challenge = _get_active_challenge(db, payload.deviceId, "authenticate")
        credential = db.scalar(
            select(PasskeyCredential).where(
                and_(
                    PasskeyCredential.user_id == device.user_id,
                    PasskeyCredential.credential_id == payload.credentialId,
                )
            )
        )
        if credential is None:
            raise APIError(400, "invalid_request", "credentialId is not registered")

        new_sign_count = app.state.webauthn.verify_authentication(
            payload,
            expected_challenge=challenge.challenge_b64,
            stored_public_key=credential.public_key,
            stored_sign_count=credential.sign_count,
        )
        credential.sign_count = new_sign_count
        challenge.used_at = utcnow()
        device.last_seen = utcnow()
        db.commit()

        token = create_access_token(app.state.settings, user_id=device.user_id, device_id=device.id)
        return TokenResponse(token=token)

    @app.post("/v1/export/sync", response_model=ExportSyncResponse)
    def export_sync(
        payload: ExportSyncRequest,
        request: Request,
        auth: AuthContext = Depends(require_auth),
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        db: Session = Depends(get_db_session),
    ) -> ExportSyncResponse | JSONResponse:
        _enforce_rate_limit(app, auth.device_id)
        if payload.device.deviceId != auth.device_id:
            raise APIError(
                403,
                "forbidden",
                "Payload deviceId does not match authenticated device",
                details={"deviceId": payload.device.deviceId},
            )

        if idempotency_key is not None:
            try:
                parsed_key = uuid.UUID(idempotency_key)
                if parsed_key.version != 4:
                    raise ValueError("Idempotency key must be UUID v4")
            except ValueError as exc:
                raise APIError(400, "invalid_request", "Idempotency-Key must be a UUID v4") from exc

            existing_recent = db.scalar(
                select(ExportIdempotency).where(
                    and_(
                        ExportIdempotency.user_id == auth.user_id,
                        ExportIdempotency.idempotency_key == idempotency_key,
                        ExportIdempotency.created_at >= utcnow() - timedelta(hours=24),
                    )
                )
            )
            if existing_recent is not None:
                return JSONResponse(
                    status_code=existing_recent.response_status,
                    content=json.loads(existing_recent.response_json),
                )

        device = db.get(Device, auth.device_id)
        if device is None or device.user_id != auth.user_id:
            raise APIError(401, "unauthorized", "Token is bound to unknown device")

        try:
            device.platform = payload.device.platform
            device.last_seen = utcnow()
            batch = ExportBatch(
                id=str(uuid.uuid4()),
                user_id=auth.user_id,
                device_id=auth.device_id,
                source=payload.source,
                reason=payload.reason,
                range_start=payload.range.start if payload.range else None,
                range_end=payload.range.end if payload.range else None,
                payload_json=payload.model_dump_json(),
            )
            db.add(batch)
            db.flush()

            _persist_normalized_export(db, batch_id=batch.id, payload=payload)
            received_count = _count_received_records(payload)
            response = ExportSyncResponse(
                status="ok",
                received=received_count,
                next=NextSyncAdvice(suggestedSyncAfterSeconds=app.state.settings.suggested_sync_after_seconds),
            )

            if idempotency_key is not None:
                entry = db.scalar(
                    select(ExportIdempotency).where(
                        and_(
                            ExportIdempotency.user_id == auth.user_id,
                            ExportIdempotency.idempotency_key == idempotency_key,
                        )
                    )
                )
                if entry is None:
                    db.add(
                        ExportIdempotency(
                            user_id=auth.user_id,
                            idempotency_key=idempotency_key,
                            response_json=response.model_dump_json(),
                            response_status=200,
                            created_at=utcnow(),
                        )
                    )
                else:
                    entry.response_json = response.model_dump_json()
                    entry.response_status = 200
                    entry.created_at = utcnow()

            db.commit()
            return response
        except IntegrityError as exc:
            db.rollback()
            raise APIError(409, "conflict", "Database conflict while processing export") from exc

    return app


def _get_or_create_user_by_device(db: Session, device_id: str) -> User:
    device = db.get(Device, device_id)
    if device is not None:
        device.last_seen = utcnow()
        user = db.get(User, device.user_id)
        if user is None:
            raise APIError(500, "internal_error", "Device references a missing user record")
        return user

    user = User(id=str(uuid.uuid4()))
    db.add(user)
    db.flush()
    db.add(Device(id=device_id, user_id=user.id, platform="ios", last_seen=utcnow()))
    return user


def _get_active_challenge(db: Session, device_id: str, flow: str) -> AuthChallenge:
    challenge = db.scalar(
        select(AuthChallenge)
        .where(
            and_(
                AuthChallenge.device_id == device_id,
                AuthChallenge.flow == flow,
                AuthChallenge.used_at.is_(None),
                AuthChallenge.expires_at > utcnow(),
            )
        )
        .order_by(desc(AuthChallenge.created_at))
    )
    if challenge is None:
        raise APIError(400, "invalid_request", "No active challenge found. Start begin endpoint again.")
    return challenge


def _enforce_rate_limit(app: FastAPI, key: str) -> None:
    allowed, retry_after = app.state.rate_limiter.allow(key)
    if allowed:
        return
    raise APIError(
        429,
        "rate_limited",
        "Rate limit exceeded",
        details={"retryAfterSeconds": retry_after},
    )


def _persist_normalized_export(db: Session, *, batch_id: str, payload: ExportSyncRequest) -> None:
    if payload.health:
        for sample in payload.health.samples:
            exists = db.scalar(
                select(func.count(HealthSample.id)).where(
                    and_(
                        HealthSample.device_id == payload.device.deviceId,
                        HealthSample.sample_type == sample.type,
                        HealthSample.start_at == sample.start,
                        HealthSample.end_at == sample.end,
                        HealthSample.source_name == sample.source,
                    )
                )
            )
            if exists:
                continue

            quantity_value = None
            quantity_unit = None
            if sample.quantity is not None:
                quantity_value = str(sample.quantity.value)
                quantity_unit = sample.quantity.unit

            db.add(
                HealthSample(
                    batch_id=batch_id,
                    device_id=payload.device.deviceId,
                    sample_type=sample.type,
                    start_at=sample.start,
                    end_at=sample.end,
                    source_name=sample.source,
                    device_name=sample.device,
                    quantity_value=quantity_value,
                    quantity_unit=quantity_unit,
                    category_value=sample.categoryValue,
                    metadata_json=json.dumps(sample.metadata) if sample.metadata is not None else None,
                )
            )

        for characteristic in payload.health.characteristics:
            db.add(
                HealthCharacteristic(
                    batch_id=batch_id,
                    characteristic_type=characteristic.type,
                    value=characteristic.value,
                )
            )

        for summary in payload.health.activitySummaries:
            summary_date = date(
                year=summary.dateComponents.year,
                month=summary.dateComponents.month,
                day=summary.dateComponents.day,
            )
            db.add(
                ActivitySummary(
                    batch_id=batch_id,
                    date=summary_date,
                    active_energy=summary.activeEnergyBurned,
                    exercise_time=summary.appleExerciseTime,
                    stand_hours=summary.appleStandHours,
                    move_time=summary.appleMoveTime,
                )
            )

    if payload.finance:
        for account in payload.finance.accounts:
            db.add(
                FinanceAccount(
                    batch_id=batch_id,
                    account_id=account.id,
                    name=account.name,
                    account_type=account.type,
                    currency_code=account.currencyCode,
                )
            )
        for tx in payload.finance.transactions:
            db.add(
                FinanceTransaction(
                    batch_id=batch_id,
                    transaction_id=tx.id,
                    account_id=tx.accountId,
                    amount=tx.amount,
                    currency_code=tx.currencyCode,
                    date=tx.date,
                    description=tx.description,
                    category=tx.category,
                )
            )
        for balance in payload.finance.balances:
            db.add(
                FinanceBalance(
                    batch_id=batch_id,
                    account_id=balance.accountId,
                    available=balance.available,
                    current=balance.current,
                    currency_code=balance.currencyCode,
                    as_of=balance.asOf,
                )
            )


def _count_received_records(payload: ExportSyncRequest) -> int:
    health_count = 0
    finance_count = 0
    if payload.health:
        health_count += len(payload.health.samples)
        health_count += len(payload.health.characteristics)
        health_count += len(payload.health.activitySummaries)
    if payload.finance:
        finance_count += len(payload.finance.accounts)
        finance_count += len(payload.finance.transactions)
        finance_count += len(payload.finance.balances)
    return health_count + finance_count


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("ember_backend.main:app", host="0.0.0.0", port=8080, reload=False)
