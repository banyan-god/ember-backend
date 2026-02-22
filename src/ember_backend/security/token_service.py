from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

import jwt
from fastapi import Header, Request
from jwt import ExpiredSignatureError, InvalidTokenError

from ember_backend.config.settings import Settings
from ember_backend.exception.api_error import APIError
from ember_backend.support.utils import utcnow


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    device_id: str


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_access_token(self, user_id: str, device_id: str) -> str:
        now = utcnow()
        payload = {
            "sub": user_id,
            "device_id": device_id,
            "iss": self._settings.jwt_issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self._settings.jwt_ttl_minutes)).timestamp()),
        }
        return jwt.encode(payload, self._settings.jwt_secret, algorithm="HS256")

    def decode_access_token(self, token: str) -> AuthContext:
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=["HS256"],
                issuer=self._settings.jwt_issuer,
            )
        except ExpiredSignatureError as exc:
            raise APIError(401, "invalid_token", "Token has expired") from exc
        except InvalidTokenError as exc:
            raise APIError(401, "invalid_token", "Invalid bearer token") from exc

        user_id = payload.get("sub")
        device_id = payload.get("device_id")
        if not user_id or not device_id:
            raise APIError(401, "invalid_token", "Token payload is incomplete")
        return AuthContext(user_id=str(user_id), device_id=str(device_id))


def require_auth(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> AuthContext:
    if authorization is None:
        raise APIError(401, "unauthorized", "Missing Authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise APIError(401, "unauthorized", "Authorization header must be Bearer token")

    token_service: TokenService = request.app.state.token_service
    return token_service.decode_access_token(parts[1])
