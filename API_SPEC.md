# Ember Backend API Spec (v1)

This backend follows Ember Pulse client contracts.

## Conventions
- Base path: `/v1/`
- Content type: `application/json`
- Dates: RFC 3339 / ISO-8601 UTC
- Auth: `Authorization: Bearer <token>`
- Idempotency: `Idempotency-Key: <uuid-v4>` (recommended on export)

### Error Schema (all endpoints)
```json
{
  "error": {
    "code": "invalid_request",
    "message": "Human-readable message",
    "details": { "field": "reason" }
  }
}
```

## Auth (Passkeys / WebAuthn)

### POST `/v1/auth/passkey/register/begin`
Request:
```json
{ "deviceId": "uuid" }
```

Response:
```json
{
  "challenge": "base64url",
  "userId": "base64url",
  "userName": "device-or-user@example.com",
  "displayName": "User Name",
  "rpId": "example.com",
  "timeoutMs": 60000
}
```

### POST `/v1/auth/passkey/register/finish`
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
{ "token": "jwt-or-opaque-token" }
```

### POST `/v1/auth/passkey/authenticate/begin`
Request:
```json
{ "deviceId": "uuid" }
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

### POST `/v1/auth/passkey/authenticate/finish`
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
{ "token": "jwt-or-opaque-token" }
```

## Export

### POST `/v1/export/sync`
Headers:
- `Authorization: Bearer <token>`
- Optional: `Idempotency-Key: <uuid-v4>`

Request shape supports HealthKit and FinanceKit payloads from Ember Pulse.

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
- Server enforces device-token binding (`payload.device.deviceId` must match token `device_id`).
- HealthKit with non-empty `samples` requires `range`.
- Health sample dedupe key: `(deviceId, type, start, end, source)`.
- Idempotency key repeats within 24 hours return the prior response.
