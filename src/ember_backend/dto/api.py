from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


class RegisterBeginRequest(BaseModel):
    deviceId: str


class RegisterBeginResponse(BaseModel):
    challenge: str
    userId: str
    userName: str
    displayName: str
    rpId: str
    timeoutMs: int


class RegisterFinishRequest(BaseModel):
    deviceId: str
    userId: str
    credentialId: str
    attestationObject: str
    clientDataJSON: str


class AuthenticateBeginRequest(BaseModel):
    deviceId: str


class AuthenticateBeginResponse(BaseModel):
    challenge: str
    rpId: str
    allowCredentials: list[str]
    timeoutMs: int


class AuthenticateFinishRequest(BaseModel):
    deviceId: str
    credentialId: str
    authenticatorData: str
    clientDataJSON: str
    signature: str


class AuthTokensResponse(BaseModel):
    token: str
    refreshToken: str


class PasswordRegisterRequest(BaseModel):
    deviceId: str
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class PasswordLoginRequest(BaseModel):
    deviceId: str
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class RefreshTokenRequest(BaseModel):
    deviceId: str
    refreshToken: str = Field(min_length=32, max_length=1024)


class DateRange(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_order(self) -> "DateRange":
        if self.end < self.start:
            raise ValueError("range.end must be greater than or equal to range.start")
        return self


class DeviceInfo(BaseModel):
    deviceId: str
    platform: str
    appVersion: str
    timezone: str


class QuantityPayload(BaseModel):
    value: float
    unit: str


class WorkoutPayload(BaseModel):
    activityType: int
    durationSeconds: float
    totalEnergyBurned: float | None = None
    totalDistanceMeters: float | None = None


class SamplePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    start: datetime
    end: datetime
    source: str
    device: str | None = None
    metadata: dict[str, StrictStr] | None = None
    quantity: QuantityPayload | None = None
    categoryValue: int | None = None
    workout: WorkoutPayload | None = None
    correlation: list["SamplePayload"] | None = None
    document: dict[str, Any] | None = None
    clinicalRecord: dict[str, Any] | None = None
    electrocardiogram: dict[str, Any] | None = None
    audiogram: dict[str, Any] | None = None
    visionPrescription: dict[str, Any] | None = None
    stateOfMind: dict[str, Any] | None = None
    medicationDoseEvent: dict[str, Any] | None = None
    workoutRoute: dict[str, Any] | None = None
    heartbeatSeries: dict[str, Any] | None = None


class CharacteristicPayload(BaseModel):
    type: str
    value: str


class DateComponentsPayload(BaseModel):
    year: int
    month: int
    day: int


class ActivitySummaryPayload(BaseModel):
    dateComponents: DateComponentsPayload
    activeEnergyBurned: float
    appleExerciseTime: float
    appleStandHours: float
    appleMoveTime: float


class HealthPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    samples: list[SamplePayload] = []
    characteristics: list[CharacteristicPayload] = []
    activitySummaries: list[ActivitySummaryPayload] = []
    userAnnotatedMedications: list[dict[str, Any]] = []


class FinanceAccountPayload(BaseModel):
    id: str
    name: str
    type: str
    currencyCode: str


class FinanceTransactionPayload(BaseModel):
    id: str
    accountId: str
    amount: float
    currencyCode: str
    date: datetime
    description: str
    category: str | None = None


class FinanceBalancePayload(BaseModel):
    accountId: str
    available: float
    current: float
    currencyCode: str
    asOf: datetime


class FinancePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    accounts: list[FinanceAccountPayload] = []
    transactions: list[FinanceTransactionPayload] = []
    balances: list[FinanceBalancePayload] = []


class ExportSyncRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    device: DeviceInfo
    range: DateRange | None = None
    reason: str
    health: HealthPayload | None = None
    finance: FinancePayload | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "ExportSyncRequest":
        if not self.source:
            raise ValueError("source is required")
        if self.source == "healthkit":
            if self.health is None:
                raise ValueError("health payload is required when source=healthkit")
            if self.health.samples and self.range is None:
                raise ValueError("range is required when sending health.samples")
        if self.source == "financekit" and self.finance is None:
            raise ValueError("finance payload is required when source=financekit")
        return self


class NextSyncAdvice(BaseModel):
    suggestedSyncAfterSeconds: int


class ExportSyncResponse(BaseModel):
    status: Literal["ok"]
    received: int
    next: NextSyncAdvice
