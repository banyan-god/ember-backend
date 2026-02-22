from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from ember_backend.model.entities import AuthChallenge, Device, PasskeyCredential, User
from ember_backend.support.utils import utcnow


class AuthRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_device(self, device_id: str) -> Device | None:
        return self.db.get(Device, device_id)

    def get_user(self, user_id: str) -> User | None:
        return self.db.get(User, user_id)

    def get_or_create_user_by_device(self, device_id: str) -> tuple[User, Device]:
        device = self.get_device(device_id)
        if device is not None:
            device.last_seen = utcnow()
            user = self.get_user(device.user_id)
            if user is None:
                raise RuntimeError("Device references a missing user record")
            return user, device

        user = User(id=str(uuid.uuid4()))
        self.db.add(user)
        self.db.flush()
        device = Device(id=device_id, user_id=user.id, platform="ios", last_seen=utcnow())
        self.db.add(device)
        self.db.flush()
        return user, device

    def create_challenge(self, flow: str, user_id: str | None, device_id: str, challenge_b64: str, expires_at: datetime) -> AuthChallenge:
        challenge = AuthChallenge(
            id=str(uuid.uuid4()),
            flow=flow,
            user_id=user_id,
            device_id=device_id,
            challenge_b64=challenge_b64,
            expires_at=expires_at,
        )
        self.db.add(challenge)
        return challenge

    def get_active_challenge(self, device_id: str, flow: str) -> AuthChallenge | None:
        return self.db.scalar(
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

    def mark_challenge_used(self, challenge: AuthChallenge) -> None:
        challenge.used_at = utcnow()

    def list_credentials_for_user(self, user_id: str) -> list[PasskeyCredential]:
        return self.db.scalars(
            select(PasskeyCredential)
            .where(PasskeyCredential.user_id == user_id)
            .order_by(PasskeyCredential.id.asc())
        ).all()

    def get_credential_for_user(self, user_id: str, credential_id: str) -> PasskeyCredential | None:
        return self.db.scalar(
            select(PasskeyCredential).where(
                and_(
                    PasskeyCredential.user_id == user_id,
                    PasskeyCredential.credential_id == credential_id,
                )
            )
        )

    def get_credential_by_id(self, credential_id: str) -> PasskeyCredential | None:
        return self.db.scalar(select(PasskeyCredential).where(PasskeyCredential.credential_id == credential_id))

    def save_credential(self, credential: PasskeyCredential) -> None:
        self.db.add(credential)

    def touch_device(self, device: Device) -> None:
        device.last_seen = utcnow()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
