# Backend Technical Specification

## 1. Scope and Goals
The backend must:
- Authenticate users via passkeys (WebAuthn).
- Accept export payloads from Ember Pulse and return deterministic acknowledgements.
- Preserve raw payloads and optionally normalize records for downstream analytics.
- Match the API contract in `API_SPEC.md`.

Non-goals:
- Analytics dashboards.
- Third-party distribution pipelines.

## 2. API Conventions
- Base path: `/v1/`
- Content type: `application/json; charset=utf-8`
- Dates: RFC 3339 / ISO-8601 UTC
- Auth: Bearer token in `Authorization` header
- Idempotency: UUID v4 in `Idempotency-Key` for export endpoint

## 3. Passkey Authentication
Endpoints:
- `POST /v1/auth/passkey/register/begin`
- `POST /v1/auth/passkey/register/finish`
- `POST /v1/auth/passkey/authenticate/begin`
- `POST /v1/auth/passkey/authenticate/finish`

Validation requirements:
- challenge + origin + RP ID checks
- attestation/assertion payload validation
- credential binding to user/device
- sign counter replay protection

## 4. Export Sync
Endpoint: `POST /v1/export/sync`

Rules:
- `payload.device.deviceId` must match authenticated token device.
- `health.samples` requires `range`.
- `health.samples[].metadata` values must be stringified strings.
- dedupe HealthKit samples by `(deviceId, type, start, end, source)`.
- idempotency-key replay within 24h returns prior response.

Response:
```json
{
  "status": "ok",
  "received": 42,
  "next": { "suggestedSyncAfterSeconds": 21600 }
}
```

## 5. Persistence Model
Core tables:
- `users`
- `devices`
- `passkey_credentials`
- `auth_challenges`
- `export_batches`
- `export_idempotency`

Normalized tables:
- `health_samples`
- `health_characteristics`
- `activity_summaries`
- `finance_accounts`
- `finance_transactions`
- `finance_balances`

## 6. Security and Privacy
- TLS required outside local dev.
- Redact secrets and tokens from logs.
- Environment-only secrets (`JWT_SECRET`, DB credentials).

## 7. Observability and Operations
- Request IDs attached to responses (`X-Request-ID`).
- Soft per-device rate limiting with backoff hint.
- Docker stack supports deterministic local boot (`sqlserver` -> `db-init` -> `api`).
