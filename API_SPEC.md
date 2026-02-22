# Data Export API Spec (Draft v2)

This spec defines a minimal backend interface for passkey authentication and multi-source data exports.

## Conventions
- Base path: `/v1/`
- Content type: `application/json`
- Dates: RFC 3339 / ISO‑8601 in UTC
- Auth: `Authorization: Bearer <token>`
- Idempotency: `Idempotency-Key: <uuid>` recommended for export sync

### Error Schema
```json
{
  "error": {
    "code": "invalid_request",
    "message": "Human‑readable message",
    "details": { "field": "reason" }
  }
}
```

## Auth (Passkeys)

### POST /v1/auth/passkey/register/begin
Begin passkey registration.

Request:
```json
{
  "deviceId": "uuid"
}
```

Response:
```json
{
  "challenge": "base64url",
  "userId": "base64url",
  "userName": "user@example.com",
  "displayName": "User Name",
  "rpId": "example.com",
  "timeoutMs": 60000
}
```

### POST /v1/auth/passkey/register/finish
Finish passkey registration.

Request:
```json
{
  "deviceId": "uuid",
  "userId": "base64url",
  "credentialId": "base64url",
  "attestationObject": "base64url",
  "clientDataJSON": "base64url"
}
```

Response:
```json
{
  "token": "jwt-or-opaque-token",
  "refreshToken": "opaque-refresh-token"
}
```

### POST /v1/auth/passkey/authenticate/begin
Begin passkey assertion.

Request:
```json
{
  "deviceId": "uuid"
}
```

Response:
```json
{
  "challenge": "base64url",
  "rpId": "example.com",
  "allowCredentials": ["base64url"],
  "timeoutMs": 60000
}
```

### POST /v1/auth/passkey/authenticate/finish
Finish passkey assertion.

Request:
```json
{
  "deviceId": "uuid",
  "credentialId": "base64url",
  "authenticatorData": "base64url",
  "clientDataJSON": "base64url",
  "signature": "base64url"
}
```

Response:
```json
{
  "token": "jwt-or-opaque-token",
  "refreshToken": "opaque-refresh-token"
}
```

## Auth (Username / Password)

### POST /v1/auth/password/register
Register (or set) username/password credentials for the user bound to `deviceId`.

Request:
```json
{
  "deviceId": "uuid",
  "username": "user@example.com",
  "password": "StrongPassword123!"
}
```

Response:
```json
{
  "token": "jwt-or-opaque-token",
  "refreshToken": "opaque-refresh-token"
}
```

Behavior:
- `username` is case-insensitive (normalized to lowercase).
- `username` must be unique across users.
- If a credential already exists for the current user, password is updated.

### POST /v1/auth/password/login
Authenticate with username/password and issue bearer token bound to `deviceId`.

Request:
```json
{
  "deviceId": "uuid",
  "username": "user@example.com",
  "password": "StrongPassword123!"
}
```

Response:
```json
{
  "token": "jwt-or-opaque-token",
  "refreshToken": "opaque-refresh-token"
}
```

Behavior:
- Returns `401 invalid_credentials` for unknown username or wrong password.
- Returns `409 conflict` if `deviceId` is already bound to a different user.

### POST /v1/auth/token/refresh
Rotate refresh token and issue a new access token pair.

Request:
```json
{
  "deviceId": "uuid",
  "refreshToken": "opaque-refresh-token"
}
```

Response:
```json
{
  "token": "jwt-or-opaque-token",
  "refreshToken": "opaque-refresh-token"
}
```

Behavior:
- Returns `401 invalid_token` when refresh token is invalid, expired, revoked, or used with the wrong device.
- Refresh tokens are single-use and rotated on every successful refresh.

### Access Token Claims (Frontend Guidance)
The `token` returned by auth endpoints is a JWT signed by the backend.

Frontend may decode it to read expiry for session UX decisions (for example, refresh 60 seconds before expiry).

Current claims:
- `sub`: user id
- `device_id`: bound device id
- `iss`: token issuer
- `iat`: issued-at (unix seconds)
- `exp`: expiry (unix seconds)
- `jti`: unique token id

Important:
- Decoding JWT on frontend is informational only.
- Authorization/trust decisions are enforced by backend signature validation and claim checks.

## Export

### POST /v1/export/sync
Upload a batch of data for a given source.

Headers:
- `Authorization: Bearer <token>`
- Optional: `Idempotency-Key: <uuid>`

Request (HealthKit example):
```json
{
  "source": "healthkit",
  "device": {
    "deviceId": "uuid",
    "platform": "ios",
    "appVersion": "1.0.0",
    "timezone": "America/Los_Angeles"
  },
  "range": {
    "start": "2026-02-20T00:00:00Z",
    "end": "2026-02-21T00:00:00Z"
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
        "metadata": { "HKWasUserEntered": "false" },
        "quantity": {
          "value": 1234,
          "unit": "count"
        },
        "categoryValue": null,
        "workout": null,
        "correlation": null
      }
    ],
    "characteristics": [
      { "type": "biologicalSex", "value": "male" },
      { "type": "dateOfBirth", "value": "1985-05-05" }
    ],
    "activitySummaries": [
      {
        "dateComponents": { "year": 2026, "month": 2, "day": 20 },
        "activeEnergyBurned": 520,
        "appleExerciseTime": 42,
        "appleStandHours": 10,
        "appleMoveTime": 45
      }
    ]
  },
  "finance": null
}
```

Request (FinanceKit example):
```json
{
  "source": "financekit",
  "device": {
    "deviceId": "uuid",
    "platform": "ios",
    "appVersion": "1.0.0",
    "timezone": "America/Los_Angeles"
  },
  "range": null,
  "reason": "manual",
  "health": null,
  "finance": {
    "accounts": [
      {
        "id": "uuid",
        "name": "Checking",
        "type": "asset",
        "currencyCode": "USD"
      }
    ],
    "transactions": [
      {
        "id": "uuid",
        "accountId": "uuid",
        "amount": 42.5,
        "currencyCode": "USD",
        "date": "2026-02-20T00:00:00Z",
        "description": "Coffee Shop",
        "category": "5814"
      }
    ],
    "balances": [
      {
        "accountId": "uuid",
        "available": 1200.25,
        "current": 1250.25,
        "currencyCode": "USD",
        "asOf": "2026-02-20T00:00:00Z"
      }
    ]
  }
}
```

Response:
```json
{
  "status": "ok",
  "received": 42,
  "next": {
    "suggestedSyncAfterSeconds": 21600
  }
}
```

## Notes
- Server should treat `(deviceId, source, type, start, end, sourceName)` as idempotent for health samples.
- Passkey endpoints should verify challenge/nonce and bind credential to the user.
- `token` is a short-lived JWT for `Authorization` header.
- `refreshToken` is long-lived and rotates on each refresh call.
- Backend must accept `deviceId`‑only bootstrap for registration and map it to a user record.
