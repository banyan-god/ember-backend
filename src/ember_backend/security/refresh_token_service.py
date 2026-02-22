from __future__ import annotations

import hashlib
import secrets


class RefreshTokenService:
    def generate(self) -> str:
        return secrets.token_urlsafe(48)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
