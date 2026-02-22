from __future__ import annotations

import json
import uuid
from typing import Any

from ember_backend.utils import b64url_encode


def build_client_data(challenge: str, ctype: str, origin: str = "https://example.com") -> str:
    payload = {"type": ctype, "challenge": challenge, "origin": origin}
    return b64url_encode(json.dumps(payload).encode("utf-8"))


def register_and_get_token(client, *, device_id: str = "device-1", credential_raw: bytes = b"cred-1") -> tuple[str, str]:
    begin_response = client.post("/v1/auth/passkey/register/begin", json={"deviceId": device_id})
    assert begin_response.status_code == 200
    begin_body = begin_response.json()

    credential_id = b64url_encode(credential_raw)
    finish_payload = {
        "deviceId": device_id,
        "userId": begin_body["userId"],
        "credentialId": credential_id,
        "attestationObject": b64url_encode(b"attestation"),
        "clientDataJSON": build_client_data(begin_body["challenge"], "webauthn.create"),
    }
    finish_response = client.post("/v1/auth/passkey/register/finish", json=finish_payload)
    assert finish_response.status_code == 200
    return finish_response.json()["token"], credential_id


def assert_error_schema(response, *, expected_code: str, expected_status: int) -> dict[str, Any]:
    assert response.status_code == expected_status
    body = response.json()
    assert isinstance(body, dict)
    assert "error" in body
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == expected_code
    assert isinstance(error["message"], str)
    assert isinstance(error["details"], dict)
    return error


def health_payload(device_id: str) -> dict[str, Any]:
    return {
        "source": "healthkit",
        "device": {
            "deviceId": device_id,
            "platform": "ios",
            "appVersion": "1.0.0",
            "timezone": "America/Los_Angeles",
        },
        "range": {
            "start": "2026-02-20T00:00:00Z",
            "end": "2026-02-21T00:00:00Z",
        },
        "reason": "manual",
        "health": {
            "samples": [
                {
                    "type": "HKQuantityTypeIdentifierStepCount",
                    "start": "2026-02-20T09:00:00Z",
                    "end": "2026-02-20T10:00:00Z",
                    "source": "iPhone",
                    "device": "iPhone",
                    "metadata": {"HKWasUserEntered": "false"},
                    "quantity": {"value": 1234, "unit": "count"},
                    "categoryValue": None,
                    "workout": None,
                    "correlation": None,
                }
            ],
            "characteristics": [{"type": "biologicalSex", "value": "male"}],
            "activitySummaries": [
                {
                    "dateComponents": {"year": 2026, "month": 2, "day": 20},
                    "activeEnergyBurned": 520,
                    "appleExerciseTime": 42,
                    "appleStandHours": 10,
                    "appleMoveTime": 45,
                }
            ],
        },
        "finance": None,
    }


def finance_payload(device_id: str) -> dict[str, Any]:
    account_id = str(uuid.uuid4())
    tx_id = str(uuid.uuid4())
    return {
        "source": "financekit",
        "device": {
            "deviceId": device_id,
            "platform": "ios",
            "appVersion": "1.0.0",
            "timezone": "America/Los_Angeles",
        },
        "range": None,
        "reason": "manual",
        "health": None,
        "finance": {
            "accounts": [
                {
                    "id": account_id,
                    "name": "Checking",
                    "type": "asset",
                    "currencyCode": "USD",
                }
            ],
            "transactions": [
                {
                    "id": tx_id,
                    "accountId": account_id,
                    "amount": 42.5,
                    "currencyCode": "USD",
                    "date": "2026-02-20T00:00:00Z",
                    "description": "Coffee Shop",
                    "category": "5814",
                }
            ],
            "balances": [
                {
                    "accountId": account_id,
                    "available": 1200.25,
                    "current": 1250.25,
                    "currencyCode": "USD",
                    "asOf": "2026-02-20T00:00:00Z",
                }
            ],
        },
    }
