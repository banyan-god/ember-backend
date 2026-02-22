from __future__ import annotations

import uuid
from datetime import timedelta

from ember_backend.config.settings import Settings
from ember_backend.dto.api import (
    AuthenticateBeginRequest,
    AuthenticateBeginResponse,
    AuthenticateFinishRequest,
    RegisterBeginRequest,
    RegisterBeginResponse,
    RegisterFinishRequest,
    TokenResponse,
)
from ember_backend.exception.api_error import APIError
from ember_backend.model.entities import PasskeyCredential
from ember_backend.repository.auth_repository import AuthRepository
from ember_backend.security.token_service import TokenService
from ember_backend.security.webauthn_service import WebAuthnService
from ember_backend.support.rate_limit import InMemoryRateLimiter
from ember_backend.support.utils import b64url_encode, utcnow


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        settings: Settings,
        webauthn_service: WebAuthnService,
        token_service: TokenService,
        rate_limiter: InMemoryRateLimiter,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.webauthn_service = webauthn_service
        self.token_service = token_service
        self.rate_limiter = rate_limiter

    def register_begin(self, payload: RegisterBeginRequest) -> RegisterBeginResponse:
        self._enforce_rate_limit(payload.deviceId)
        try:
            user, _ = self.repository.get_or_create_user_by_device(payload.deviceId)
            challenge = self.webauthn_service.generate_challenge()
            self.repository.create_challenge(
                flow="register",
                user_id=user.id,
                device_id=payload.deviceId,
                challenge_b64=challenge,
                expires_at=utcnow() + timedelta(seconds=self.settings.challenge_ttl_seconds),
            )
            self.repository.commit()
        except RuntimeError as exc:
            self.repository.rollback()
            raise APIError(500, "internal_error", str(exc)) from exc

        user_handle = b64url_encode(uuid.UUID(user.id).bytes)
        return RegisterBeginResponse(
            challenge=challenge,
            userId=user_handle,
            userName=f"{payload.deviceId}@ember.local",
            displayName="Ember User",
            rpId=self.settings.webauthn_rp_id,
            timeoutMs=60000,
        )

    def register_finish(self, payload: RegisterFinishRequest) -> TokenResponse:
        self._enforce_rate_limit(payload.deviceId)

        device = self.repository.get_device(payload.deviceId)
        if device is None:
            raise APIError(400, "invalid_request", "Unknown deviceId")

        challenge = self.repository.get_active_challenge(payload.deviceId, "register")
        if challenge is None:
            raise APIError(400, "invalid_request", "No active challenge found. Start begin endpoint again.")

        expected_user_handle = b64url_encode(uuid.UUID(device.user_id).bytes)
        if payload.userId != expected_user_handle:
            raise APIError(400, "invalid_request", "userId does not match expected user handle")

        verification = self.webauthn_service.verify_registration(payload, challenge.challenge_b64)

        existing_credential = self.repository.get_credential_by_id(payload.credentialId)
        if existing_credential and existing_credential.user_id != device.user_id:
            raise APIError(409, "conflict", "credentialId is already bound to a different user")

        if existing_credential is None:
            self.repository.save_credential(
                PasskeyCredential(
                    credential_id=payload.credentialId,
                    user_id=device.user_id,
                    user_handle=payload.userId,
                    public_key=verification.public_key,
                    sign_count=verification.sign_count,
                    rp_id=self.settings.webauthn_rp_id,
                )
            )
        else:
            existing_credential.public_key = verification.public_key
            existing_credential.sign_count = verification.sign_count
            existing_credential.user_handle = payload.userId
            existing_credential.rp_id = self.settings.webauthn_rp_id

        self.repository.mark_challenge_used(challenge)
        self.repository.touch_device(device)
        self.repository.commit()

        token = self.token_service.create_access_token(user_id=device.user_id, device_id=device.id)
        return TokenResponse(token=token)

    def authenticate_begin(self, payload: AuthenticateBeginRequest) -> AuthenticateBeginResponse:
        self._enforce_rate_limit(payload.deviceId)

        device = self.repository.get_device(payload.deviceId)
        if device is None:
            raise APIError(400, "invalid_request", "Unknown deviceId")

        credentials = self.repository.list_credentials_for_user(device.user_id)
        if not credentials:
            raise APIError(400, "invalid_request", "No passkey credentials available for this device")

        challenge = self.webauthn_service.generate_challenge()
        self.repository.create_challenge(
            flow="authenticate",
            user_id=device.user_id,
            device_id=device.id,
            challenge_b64=challenge,
            expires_at=utcnow() + timedelta(seconds=self.settings.challenge_ttl_seconds),
        )
        self.repository.touch_device(device)
        self.repository.commit()

        return AuthenticateBeginResponse(
            challenge=challenge,
            rpId=self.settings.webauthn_rp_id,
            allowCredentials=[cred.credential_id for cred in credentials],
            timeoutMs=60000,
        )

    def authenticate_finish(self, payload: AuthenticateFinishRequest) -> TokenResponse:
        self._enforce_rate_limit(payload.deviceId)

        device = self.repository.get_device(payload.deviceId)
        if device is None:
            raise APIError(400, "invalid_request", "Unknown deviceId")

        challenge = self.repository.get_active_challenge(payload.deviceId, "authenticate")
        if challenge is None:
            raise APIError(400, "invalid_request", "No active challenge found. Start begin endpoint again.")

        credential = self.repository.get_credential_for_user(device.user_id, payload.credentialId)
        if credential is None:
            raise APIError(400, "invalid_request", "credentialId is not registered")

        new_sign_count = self.webauthn_service.verify_authentication(
            payload,
            expected_challenge=challenge.challenge_b64,
            stored_public_key=credential.public_key,
            stored_sign_count=credential.sign_count,
        )
        credential.sign_count = new_sign_count

        self.repository.mark_challenge_used(challenge)
        self.repository.touch_device(device)
        self.repository.commit()

        token = self.token_service.create_access_token(user_id=device.user_id, device_id=device.id)
        return TokenResponse(token=token)

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
