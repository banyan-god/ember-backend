from __future__ import annotations

from tests.helpers import assert_error_schema, build_client_data, register_and_get_auth_tokens, register_and_get_token


def test_aasa_well_known_endpoint(client) -> None:
    response = client.get("/.well-known/apple-app-site-association")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "webcredentials": {
            "apps": ["ABCDE12345.com.sabareesh.emberpulse"],
        }
    }


def test_aasa_root_endpoint(client) -> None:
    response = client.get("/apple-app-site-association")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "webcredentials": {
            "apps": ["ABCDE12345.com.sabareesh.emberpulse"],
        }
    }


def test_healthz_endpoint(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_password_register_and_login_flow(client) -> None:
    register_response = client.post(
        "/v1/auth/password/register",
        json={
            "deviceId": "pw-device-1",
            "username": "Alice@Example.com",
            "password": "StrongPassword123!",
        },
    )
    assert register_response.status_code == 200
    assert isinstance(register_response.json()["token"], str)
    assert isinstance(register_response.json()["refreshToken"], str)

    login_response = client.post(
        "/v1/auth/password/login",
        json={
            "deviceId": "pw-device-2",
            "username": "alice@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert login_response.status_code == 200
    assert isinstance(login_response.json()["token"], str)
    assert isinstance(login_response.json()["refreshToken"], str)


def test_password_register_rejects_duplicate_username(client) -> None:
    first = client.post(
        "/v1/auth/password/register",
        json={
            "deviceId": "dup-device-1",
            "username": "duplicate@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/v1/auth/password/register",
        json={
            "deviceId": "dup-device-2",
            "username": "duplicate@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert_error_schema(second, expected_code="conflict", expected_status=409)


def test_password_login_rejects_invalid_credentials(client) -> None:
    register_response = client.post(
        "/v1/auth/password/register",
        json={
            "deviceId": "invalid-cred-device",
            "username": "loginfail@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert register_response.status_code == 200

    invalid_login = client.post(
        "/v1/auth/password/login",
        json={
            "deviceId": "invalid-cred-device-2",
            "username": "loginfail@example.com",
            "password": "WrongPassword123!",
        },
    )
    assert_error_schema(invalid_login, expected_code="invalid_credentials", expected_status=401)


def test_password_login_rejects_device_bound_to_another_user(client) -> None:
    first_user = client.post(
        "/v1/auth/password/register",
        json={
            "deviceId": "bound-device-1",
            "username": "userone@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert first_user.status_code == 200
    second_user = client.post(
        "/v1/auth/password/register",
        json={
            "deviceId": "bound-device-2",
            "username": "usertwo@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert second_user.status_code == 200

    conflicting_login = client.post(
        "/v1/auth/password/login",
        json={
            "deviceId": "bound-device-1",
            "username": "usertwo@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert_error_schema(conflicting_login, expected_code="conflict", expected_status=409)


def test_register_begin_response_matches_spec_shape(client) -> None:
    response = client.post("/v1/auth/passkey/register/begin", json={"deviceId": "device-register-shape"})
    assert response.status_code == 200
    body = response.json()

    assert isinstance(body["challenge"], str) and body["challenge"]
    assert isinstance(body["userId"], str) and body["userId"]
    assert isinstance(body["userName"], str) and body["userName"].endswith("@ember.local")
    assert isinstance(body["displayName"], str) and body["displayName"] == "Ember User"
    assert body["rpId"] == "example.com"
    assert body["timeoutMs"] == 60000


def test_register_finish_fails_without_active_challenge(client) -> None:
    begin_response = client.post("/v1/auth/passkey/register/begin", json={"deviceId": "device-no-challenge"})
    assert begin_response.status_code == 200
    begin_body = begin_response.json()

    payload = {
        "deviceId": "device-no-challenge",
        "userId": begin_body["userId"],
        "credentialId": "Y3JlZDE",
        "attestationObject": "YXR0ZXN0YXRpb24",
        "clientDataJSON": build_client_data(begin_body["challenge"], "webauthn.create"),
    }
    first_finish = client.post("/v1/auth/passkey/register/finish", json=payload)
    assert first_finish.status_code == 200

    second_finish = client.post("/v1/auth/passkey/register/finish", json=payload)
    assert_error_schema(second_finish, expected_code="invalid_request", expected_status=400)


def test_register_rejects_untrusted_origin(client) -> None:
    begin = client.post("/v1/auth/passkey/register/begin", json={"deviceId": "device-origin"})
    assert begin.status_code == 200
    begin_body = begin.json()

    finish = client.post(
        "/v1/auth/passkey/register/finish",
        json={
            "deviceId": "device-origin",
            "userId": begin_body["userId"],
            "credentialId": "Y3JlZC1vcmlnaW4",
            "attestationObject": "YXR0ZXN0YXRpb24",
            "clientDataJSON": build_client_data(
                begin_body["challenge"],
                "webauthn.create",
                origin="https://malicious.example.net",
            ),
        },
    )
    assert_error_schema(finish, expected_code="invalid_request", expected_status=400)


def test_authenticate_begin_requires_registered_credential(client) -> None:
    register_begin = client.post("/v1/auth/passkey/register/begin", json={"deviceId": "device-no-cred"})
    assert register_begin.status_code == 200

    auth_begin = client.post("/v1/auth/passkey/authenticate/begin", json={"deviceId": "device-no-cred"})
    assert_error_schema(auth_begin, expected_code="invalid_request", expected_status=400)


def test_register_and_authenticate_flow(client) -> None:
    _, credential_id = register_and_get_token(client, device_id="device-auth")

    begin = client.post("/v1/auth/passkey/authenticate/begin", json={"deviceId": "device-auth"})
    assert begin.status_code == 200
    begin_body = begin.json()
    assert isinstance(begin_body["challenge"], str) and begin_body["challenge"]
    assert begin_body["rpId"] == "example.com"
    assert credential_id in begin_body["allowCredentials"]
    assert begin_body["timeoutMs"] == 60000

    finish = client.post(
        "/v1/auth/passkey/authenticate/finish",
        json={
            "deviceId": "device-auth",
            "credentialId": credential_id,
            "authenticatorData": "YXV0aC1kYXRh",
            "clientDataJSON": build_client_data(begin_body["challenge"], "webauthn.get"),
            "signature": "c2lnbmF0dXJl",
        },
    )
    assert finish.status_code == 200
    assert isinstance(finish.json()["token"], str) and finish.json()["token"]
    assert isinstance(finish.json()["refreshToken"], str) and finish.json()["refreshToken"]


def test_authenticate_finish_rejects_unknown_credential(client) -> None:
    register_and_get_token(client, device_id="device-auth-fail", credential_raw=b"known-cred")
    begin = client.post("/v1/auth/passkey/authenticate/begin", json={"deviceId": "device-auth-fail"})
    assert begin.status_code == 200
    begin_body = begin.json()

    finish = client.post(
        "/v1/auth/passkey/authenticate/finish",
        json={
            "deviceId": "device-auth-fail",
            "credentialId": "dW5rbm93bi1jcmVk",
            "authenticatorData": "YXV0aC1kYXRh",
            "clientDataJSON": build_client_data(begin_body["challenge"], "webauthn.get"),
            "signature": "c2lnbmF0dXJl",
        },
    )
    assert_error_schema(finish, expected_code="invalid_request", expected_status=400)


def test_export_requires_token(client) -> None:
    response = client.post(
        "/v1/export/sync",
        json={
            "source": "financekit",
            "device": {
                "deviceId": "device-unauth",
                "platform": "ios",
                "appVersion": "1.0.0",
                "timezone": "UTC",
            },
            "range": None,
            "reason": "manual",
            "health": None,
            "finance": {"accounts": [], "transactions": [], "balances": []},
        },
    )
    assert_error_schema(response, expected_code="unauthorized", expected_status=401)


def test_refresh_token_rotates_and_rejects_reuse(client) -> None:
    register_response = client.post(
        "/v1/auth/password/register",
        json={
            "deviceId": "refresh-device-1",
            "username": "refresh@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert register_response.status_code == 200
    first_tokens = register_response.json()
    assert isinstance(first_tokens["token"], str) and first_tokens["token"]
    assert isinstance(first_tokens["refreshToken"], str) and first_tokens["refreshToken"]

    refresh_response = client.post(
        "/v1/auth/token/refresh",
        json={
            "deviceId": "refresh-device-1",
            "refreshToken": first_tokens["refreshToken"],
        },
    )
    assert refresh_response.status_code == 200
    second_tokens = refresh_response.json()
    assert isinstance(second_tokens["token"], str) and second_tokens["token"]
    assert isinstance(second_tokens["refreshToken"], str) and second_tokens["refreshToken"]
    assert second_tokens["token"] != first_tokens["token"]
    assert second_tokens["refreshToken"] != first_tokens["refreshToken"]

    reused_response = client.post(
        "/v1/auth/token/refresh",
        json={
            "deviceId": "refresh-device-1",
            "refreshToken": first_tokens["refreshToken"],
        },
    )
    assert_error_schema(reused_response, expected_code="invalid_token", expected_status=401)


def test_refresh_token_rejects_wrong_device(client) -> None:
    _, refresh_token, _ = register_and_get_auth_tokens(client, device_id="refresh-device-2")

    response = client.post(
        "/v1/auth/token/refresh",
        json={
            "deviceId": "refresh-device-wrong",
            "refreshToken": refresh_token,
        },
    )
    assert_error_schema(response, expected_code="invalid_token", expected_status=401)
