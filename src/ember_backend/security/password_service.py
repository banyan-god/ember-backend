from __future__ import annotations

import base64
import hashlib
import hmac
import os


class PasswordService:
    _algorithm = "pbkdf2_sha256"
    _iterations = 310000
    _salt_bytes = 16
    _dklen = 32

    def hash_password(self, password: str) -> str:
        salt = os.urandom(self._salt_bytes)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self._iterations,
            dklen=self._dklen,
        )
        salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
        digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
        return f"{self._algorithm}${self._iterations}${salt_b64}${digest_b64}"

    def verify_password(self, password: str, encoded: str) -> bool:
        try:
            algorithm, iterations_str, salt_b64, digest_b64 = encoded.split("$", 3)
            if algorithm != self._algorithm:
                return False
            iterations = int(iterations_str)
            salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
            expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        except Exception:
            return False

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected),
        )
        return hmac.compare_digest(expected, actual)
