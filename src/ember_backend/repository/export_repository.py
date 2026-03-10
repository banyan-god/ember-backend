from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError as SAIntegrityError
from sqlalchemy.orm import Session

from ember_backend.dto.api import ExportSyncRequest
from ember_backend.model.entities import (
    ActivitySummary,
    Device,
    ExportBatch,
    ExportIdempotency,
    FinanceAccount,
    FinanceBalance,
    FinanceTransaction,
    HealthCharacteristic,
    HealthSample,
)
from ember_backend.support.utils import utcnow


class ExportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_device_for_user(self, user_id: str, device_id: str) -> Device | None:
        device = self.db.get(Device, device_id)
        if device is None or device.user_id != user_id:
            return None
        return device

    def get_recent_idempotency(self, user_id: str, idempotency_key: str, *, within_hours: int = 24) -> ExportIdempotency | None:
        cutoff = utcnow() - timedelta(hours=within_hours)
        return self.db.scalar(
            select(ExportIdempotency).where(
                and_(
                    ExportIdempotency.user_id == user_id,
                    ExportIdempotency.idempotency_key == idempotency_key,
                    ExportIdempotency.created_at >= cutoff,
                )
            )
        )

    def get_idempotency(self, user_id: str, idempotency_key: str) -> ExportIdempotency | None:
        return self.db.scalar(
            select(ExportIdempotency).where(
                and_(
                    ExportIdempotency.user_id == user_id,
                    ExportIdempotency.idempotency_key == idempotency_key,
                )
            )
        )

    def save_idempotency(self, user_id: str, idempotency_key: str, response_json: str, response_status: int = 200) -> None:
        entry = self.get_idempotency(user_id, idempotency_key)
        if entry is None:
            self.db.add(
                ExportIdempotency(
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    response_json=response_json,
                    response_status=response_status,
                    created_at=utcnow(),
                )
            )
            return

        entry.response_json = response_json
        entry.response_status = response_status
        entry.created_at = utcnow()

    def create_export_batch(self, user_id: str, device_id: str, payload: ExportSyncRequest) -> ExportBatch:
        batch = ExportBatch(
            id=str(uuid.uuid4()),
            user_id=user_id,
            device_id=device_id,
            source=payload.source,
            reason=payload.reason,
            range_start=payload.range.start if payload.range else None,
            range_end=payload.range.end if payload.range else None,
            payload_json=payload.model_dump_json(),
        )
        self.db.add(batch)
        self.db.flush()
        return batch

    def update_device_seen(self, device: Device, platform: str) -> None:
        device.platform = platform
        device.last_seen = utcnow()

    def persist_normalized(self, batch_id: str, payload: ExportSyncRequest) -> None:
        if payload.health:
            if payload.health.samples:
                self._persist_health_samples(batch_id, payload)


            for characteristic in payload.health.characteristics:
                self.db.add(
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
                self.db.add(
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
                self.db.add(
                    FinanceAccount(
                        batch_id=batch_id,
                        account_id=account.id,
                        name=account.name,
                        account_type=account.type,
                        currency_code=account.currencyCode,
                    )
                )
            for tx in payload.finance.transactions:
                self.db.add(
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
                self.db.add(
                    FinanceBalance(
                        batch_id=batch_id,
                        account_id=balance.accountId,
                        available=balance.available,
                        current=balance.current,
                        currency_code=balance.currencyCode,
                        as_of=balance.asOf,
                    )
                )

    def _persist_health_samples(self, batch_id: str, payload: ExportSyncRequest) -> None:
        device_id = payload.device.deviceId

        for sample in payload.health.samples:
            quantity_value = None
            quantity_unit = None
            if sample.quantity is not None:
                quantity_value = str(sample.quantity.value)
                quantity_unit = sample.quantity.unit

            # Use a savepoint so a duplicate (IntegrityError from the unique
            # constraint) only rolls back this single insert, not the whole
            # transaction.  This replaces the old N+1 SELECT-per-sample pattern
            # that was holding DB connections for minutes and exhausting the pool.
            nested = self.db.begin_nested()
            try:
                self.db.add(
                    HealthSample(
                        batch_id=batch_id,
                        device_id=device_id,
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
                nested.commit()
            except SAIntegrityError:
                nested.rollback()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
