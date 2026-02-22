from __future__ import annotations

import uuid

from sqlalchemy import select

from ember_backend.model.entities import FinanceAccount, FinanceBalance, FinanceTransaction, HealthSample
from ember_backend.support.rate_limit import InMemoryRateLimiter
from tests.helpers import assert_error_schema, finance_payload, health_payload, register_and_get_token


def test_export_sync_health_idempotency_and_dedupe(client, db_session) -> None:
    token, _ = register_and_get_token(client, device_id="device-export")
    payload = health_payload("device-export")
    idem_key = str(uuid.uuid4())

    response1 = client.post(
        "/v1/export/sync",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": idem_key},
    )
    assert response1.status_code == 200
    assert response1.json() == {
        "status": "ok",
        "received": 3,
        "next": {"suggestedSyncAfterSeconds": 21600},
    }

    response2 = client.post(
        "/v1/export/sync",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": idem_key},
    )
    assert response2.status_code == 200
    assert response2.json() == response1.json()

    response3 = client.post(
        "/v1/export/sync",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response3.status_code == 200

    samples = db_session.scalars(select(HealthSample)).all()
    assert len(samples) == 1


def test_export_accepts_healthkit_extended_fields_and_user_annotated_medications(client) -> None:
    token, _ = register_and_get_token(client, device_id="device-health-extended")
    payload = health_payload("device-health-extended")
    payload["health"]["samples"][0]["document"] = {
        "documentType": "HKDocumentTypeIdentifierCDA",
        "title": "Example",
        "dataFormat": "cda-xml-base64",
        "documentData": "PD94bWwgdmVyc2lvbj0iMS4wIj8+",
    }
    payload["health"]["samples"][0]["clinicalRecord"] = {
        "displayName": "AllergyIntolerance",
        "resourceType": "AllergyIntolerance",
        "identifier": "allergy-123",
        "fhirJSON": "{\"resourceType\":\"AllergyIntolerance\"}",
        "fhirJSONIsBase64": False,
    }
    payload["health"]["samples"][0]["heartbeatSeries"] = {
        "measurements": [
            {"timeSinceStart": 0.12, "precededByGap": False},
            {"timeSinceStart": 1.01, "precededByGap": True},
        ]
    }
    payload["health"]["userAnnotatedMedications"] = [
        {
            "nickname": "Evening aspirin",
            "isArchived": False,
            "hasSchedule": True,
            "medication": {
                "identifier": "HKHealthConceptIdentifier(1191)",
                "domain": "HKHealthConceptDomainMedication",
                "displayText": "Aspirin",
                "generalForm": "HKMedicationGeneralFormTablet",
                "relatedCodings": [
                    {"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "version": None, "code": "1191"}
                ],
            },
        }
    ]

    response = client.post(
        "/v1/export/sync",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["received"] == 4


def test_export_sync_finance_source_matches_spec_shape(client, db_session) -> None:
    token, _ = register_and_get_token(client, device_id="device-finance")
    payload = finance_payload("device-finance")

    response = client.post(
        "/v1/export/sync",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["received"] == 3
    assert response.json()["next"]["suggestedSyncAfterSeconds"] == 21600

    assert len(db_session.scalars(select(FinanceAccount)).all()) == 1
    assert len(db_session.scalars(select(FinanceTransaction)).all()) == 1
    assert len(db_session.scalars(select(FinanceBalance)).all()) == 1


def test_export_allows_future_source_values(client) -> None:
    token, _ = register_and_get_token(client, device_id="device-future-source")
    payload = {
        "source": "sleepkit",
        "device": {
            "deviceId": "device-future-source",
            "platform": "ios",
            "appVersion": "1.0.0",
            "timezone": "UTC",
        },
        "range": None,
        "reason": "manual",
        "health": None,
        "finance": None,
    }

    response = client.post(
        "/v1/export/sync",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    assert response.json()["received"] == 0


def test_export_rejects_device_mismatch(client) -> None:
    token, _ = register_and_get_token(client, device_id="device-a")
    payload = health_payload("device-b")

    response = client.post(
        "/v1/export/sync",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    error = assert_error_schema(response, expected_code="forbidden", expected_status=403)
    assert error["details"]["deviceId"] == "device-b"


def test_export_rejects_invalid_idempotency_key(client) -> None:
    token, _ = register_and_get_token(client, device_id="device-idem")
    payload = health_payload("device-idem")

    response = client.post(
        "/v1/export/sync",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "not-a-uuid"},
    )
    assert_error_schema(response, expected_code="invalid_request", expected_status=400)


def test_health_samples_require_range(client) -> None:
    token, _ = register_and_get_token(client, device_id="device-range")
    payload = health_payload("device-range")
    payload["range"] = None

    response = client.post(
        "/v1/export/sync",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert_error_schema(response, expected_code="invalid_request", expected_status=400)


def test_health_metadata_values_must_be_stringified(client) -> None:
    token, _ = register_and_get_token(client, device_id="device-metadata")
    payload = health_payload("device-metadata")
    payload["health"]["samples"][0]["metadata"] = {"HKWasUserEntered": False}

    response = client.post(
        "/v1/export/sync",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert_error_schema(response, expected_code="invalid_request", expected_status=400)


def test_invalid_bearer_token_returns_spec_error_shape(client) -> None:
    payload = finance_payload("device-token")
    response = client.post(
        "/v1/export/sync",
        json=payload,
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert_error_schema(response, expected_code="invalid_token", expected_status=401)


def test_rate_limit_returns_backoff_hint(client, app) -> None:
    app.state.rate_limiter = InMemoryRateLimiter(limit_per_minute=2)

    response1 = client.post("/v1/auth/passkey/register/begin", json={"deviceId": "device-rate"})
    assert response1.status_code == 200
    response2 = client.post("/v1/auth/passkey/register/begin", json={"deviceId": "device-rate"})
    assert response2.status_code == 200
    response3 = client.post("/v1/auth/passkey/register/begin", json={"deviceId": "device-rate"})

    error = assert_error_schema(response3, expected_code="rate_limited", expected_status=429)
    assert "retryAfterSeconds" in error["details"]
