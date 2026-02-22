from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass

from fido2.cose import CoseKey
from fido2.rpid import verify_rp_id
from fido2.webauthn import AttestationObject, AuthenticatorData

from ember_backend.config.settings import Settings
from ember_backend.dto.api import AuthenticateFinishRequest, RegisterFinishRequest
from ember_backend.exception.api_error import APIError
from ember_backend.support.utils import b64url_decode, b64url_encode


@dataclass(frozen=True)
class RegistrationVerification:
    public_key: bytes
    sign_count: int


class WebAuthnService:
    def generate_challenge(self) -> str:
        return b64url_encode(secrets.token_bytes(32))

    def verify_registration(
        self,
        request: RegisterFinishRequest,
        expected_challenge: str,
    ) -> RegistrationVerification:
        raise NotImplementedError

    def verify_authentication(
        self,
        request: AuthenticateFinishRequest,
        expected_challenge: str,
        stored_public_key: bytes,
        stored_sign_count: int,
    ) -> int:
        raise NotImplementedError


class StrictWebAuthnService(WebAuthnService):
    def __init__(self, settings: Settings) -> None:
        self.rp_id = settings.webauthn_rp_id
        self.allowed_origins = settings.allowed_origins
        self.rp_id_hash = hashlib.sha256(self.rp_id.encode("utf-8")).digest()

    def verify_registration(
        self,
        request: RegisterFinishRequest,
        expected_challenge: str,
    ) -> RegistrationVerification:
        self._validate_client_data(
            request.clientDataJSON,
            expected_challenge=expected_challenge,
            expected_type="webauthn.create",
        )

        try:
            attestation_object = AttestationObject(b64url_decode(request.attestationObject))
        except Exception as exc:  # pragma: no cover
            raise APIError(400, "invalid_request", "Invalid attestationObject") from exc

        auth_data = attestation_object.auth_data
        if auth_data.rp_id_hash != self.rp_id_hash:
            raise APIError(400, "invalid_request", "RP ID hash mismatch")
        if (auth_data.flags & 0x01) == 0:
            raise APIError(400, "invalid_request", "User presence flag is not set")
        if auth_data.credential_data is None:
            raise APIError(400, "invalid_request", "Missing credential data in attestation")

        credential_id = b64url_encode(auth_data.credential_data.credential_id)
        if credential_id != request.credentialId:
            raise APIError(400, "invalid_request", "credentialId does not match attestationObject")

        public_key = bytes(auth_data.credential_data.public_key)
        return RegistrationVerification(public_key=public_key, sign_count=int(auth_data.counter))

    def verify_authentication(
        self,
        request: AuthenticateFinishRequest,
        expected_challenge: str,
        stored_public_key: bytes,
        stored_sign_count: int,
    ) -> int:
        client_data_raw = self._validate_client_data(
            request.clientDataJSON,
            expected_challenge=expected_challenge,
            expected_type="webauthn.get",
        )

        try:
            auth_data_bytes = b64url_decode(request.authenticatorData)
            auth_data = AuthenticatorData(auth_data_bytes)
            signature = b64url_decode(request.signature)
        except Exception as exc:  # pragma: no cover
            raise APIError(400, "invalid_request", "Invalid authenticator payload") from exc

        if auth_data.rp_id_hash != self.rp_id_hash:
            raise APIError(400, "invalid_request", "RP ID hash mismatch")
        if (auth_data.flags & 0x01) == 0:
            raise APIError(400, "invalid_request", "User presence flag is not set")

        signed_data = auth_data_bytes + hashlib.sha256(client_data_raw).digest()
        try:
            cose_key = CoseKey.parse(stored_public_key)
            verified = cose_key.verify(signed_data, signature)
        except Exception as exc:  # pragma: no cover
            raise APIError(401, "invalid_request", "Signature verification failed") from exc

        if verified is False:
            raise APIError(401, "invalid_request", "Signature verification failed")

        new_sign_count = int(auth_data.counter)
        if stored_sign_count > 0 and new_sign_count <= stored_sign_count:
            raise APIError(401, "invalid_request", "Authenticator sign count replay detected")
        return new_sign_count

    def _validate_client_data(self, client_data_b64: str, expected_challenge: str, expected_type: str) -> bytes:
        try:
            raw = b64url_decode(client_data_b64)
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise APIError(400, "invalid_request", "Invalid clientDataJSON") from exc

        challenge = payload.get("challenge")
        ctype = payload.get("type")
        origin = payload.get("origin")
        if ctype != expected_type:
            raise APIError(400, "invalid_request", f"clientDataJSON type must be {expected_type}")
        if challenge != expected_challenge:
            raise APIError(400, "invalid_request", "Challenge mismatch")
        if not origin:
            raise APIError(400, "invalid_request", "Missing origin in clientDataJSON")
        if self.allowed_origins and origin not in self.allowed_origins:
            raise APIError(400, "invalid_request", "Origin not allowed")
        if not verify_rp_id(self.rp_id, origin):
            raise APIError(400, "invalid_request", "Origin does not match RP ID")
        return raw


class StubWebAuthnService(WebAuthnService):
    def __init__(self, settings: Settings) -> None:
        self.rp_id = settings.webauthn_rp_id
        self.allowed_origins = settings.allowed_origins

    def verify_registration(
        self,
        request: RegisterFinishRequest,
        expected_challenge: str,
    ) -> RegistrationVerification:
        self._validate_client_data(request.clientDataJSON, expected_challenge, "webauthn.create")
        _ = b64url_decode(request.attestationObject)
        public_key = request.credentialId.encode("utf-8")
        return RegistrationVerification(public_key=public_key, sign_count=0)

    def verify_authentication(
        self,
        request: AuthenticateFinishRequest,
        expected_challenge: str,
        stored_public_key: bytes,
        stored_sign_count: int,
    ) -> int:
        self._validate_client_data(request.clientDataJSON, expected_challenge, "webauthn.get")
        _ = b64url_decode(request.authenticatorData)
        _ = b64url_decode(request.signature)
        if not stored_public_key:
            raise APIError(401, "invalid_request", "Missing stored credential key")
        return stored_sign_count + 1

    def _validate_client_data(self, client_data_b64: str, expected_challenge: str, expected_type: str) -> None:
        try:
            raw = b64url_decode(client_data_b64)
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise APIError(400, "invalid_request", "Invalid clientDataJSON") from exc

        challenge = payload.get("challenge")
        ctype = payload.get("type")
        origin = payload.get("origin")
        if ctype != expected_type:
            raise APIError(400, "invalid_request", f"clientDataJSON type must be {expected_type}")
        if challenge != expected_challenge:
            raise APIError(400, "invalid_request", "Challenge mismatch")
        if not origin:
            raise APIError(400, "invalid_request", "Missing origin in clientDataJSON")
        if self.allowed_origins and origin not in self.allowed_origins:
            raise APIError(400, "invalid_request", "Origin not allowed")
        if not verify_rp_id(self.rp_id, origin):
            raise APIError(400, "invalid_request", "Origin does not match RP ID")


def build_webauthn_service(settings: Settings) -> WebAuthnService:
    if settings.webauthn_mode.lower() == "stub":
        return StubWebAuthnService(settings)
    return StrictWebAuthnService(settings)
