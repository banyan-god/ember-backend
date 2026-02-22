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
  "token": "jwt-or-opaque-token"
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
  "token": "jwt-or-opaque-token"
}
```

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
- Token can be JWT or opaque; must be accepted by `Authorization` header.
- Backend must accept `deviceId`‑only bootstrap for registration and map it to a user record.
