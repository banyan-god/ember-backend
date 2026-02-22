# Backend Technical Specification

## 1. Scope and Goals
The backend must:
- Authenticate users via passkeys (WebAuthn).
- Accept multi-source export payloads from iOS and return deterministic acknowledgements.
- Preserve raw data while enabling normalized query paths for future analytics.
- Provide stable, versioned APIs compatible with `API_SPEC.md`.

Non-goals: data visualization, analytics dashboards, or third‑party sharing.

## 2. API Conventions
- Base path: `/v1/`
- Content type: `application/json; charset=utf-8`
- Dates: RFC 3339 / ISO‑8601 in UTC.
- Auth: `Authorization: Bearer <token>`.
- Idempotency: `Idempotency-Key` (UUID v4) recommended for export.

### Error Schema (All Endpoints)
```json
{
  "error": {
    "code": "invalid_request",
    "message": "Human‑readable message",
    "details": { "field": "reason" }
  }
}
```

## 3. Passkey Authentication (WebAuthn)
Backend must implement WebAuthn server validation. The iOS client uses:
- Registration: `ASAuthorizationPlatformPublicKeyCredentialRegistration`
- Assertion: `ASAuthorizationPlatformPublicKeyCredentialAssertion`

### 3.1 Register Begin
`POST /v1/auth/passkey/register/begin`
Request:
```json
{ "deviceId": "uuid" }
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
Server responsibilities:
- Create or look up a user by `deviceId` (initial bootstrap).
- Generate a cryptographically strong challenge (>= 32 bytes).
- Return `rpId` matching Associated Domains.
- Store challenge with short TTL (<= 5 minutes).

### 3.2 Register Finish
`POST /v1/auth/passkey/register/finish`
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
Validation:
- Verify challenge, origin, RP ID, and attestation per WebAuthn.
- Persist credential public key, sign count, and user handle.
- Issue a token bound to the user and device.

### 3.3 Authenticate Begin
`POST /v1/auth/passkey/authenticate/begin`
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
Server responsibilities:
- Lookup credentials for the user (by deviceId).
- Provide allowList (credential IDs).

### 3.4 Authenticate Finish
`POST /v1/auth/passkey/authenticate/finish`
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
Validation:
- Verify challenge, origin, RP ID, signature, and sign count.
- Update stored sign count to prevent replay.

### Token Rules
- Short‑lived access token (e.g., 30–60 minutes).
- Long-lived refresh token (default 3650 days) for persistent login.
- Refresh tokens are rotated on every successful refresh call.
- Refresh tokens are device-bound.

### 3.5 Username/Password Authentication (Fallback)
Backend also supports username/password authentication for clients that cannot use passkeys.

### Register
`POST /v1/auth/password/register`
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
Rules:
- Normalize username to lowercase.
- Enforce global username uniqueness.
- Hash password using a strong KDF (PBKDF2/Argon2/bcrypt class algorithms, never plaintext).
- If credential exists for same user, update password hash.

### Login
`POST /v1/auth/password/login`
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
Rules:
- Return `401 invalid_credentials` for invalid username/password.
- Keep device-token binding semantics consistent with passkey flow.
- Return `409 conflict` when logging into a device bound to another user.

### Refresh
`POST /v1/auth/token/refresh`
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
Rules:
- Reject invalid/expired/revoked refresh token with `401 invalid_token`.
- Reject refresh token for wrong device with `401 invalid_token`.
- Rotate refresh token after each successful refresh.

## 4. Export API
### 4.1 Sync
`POST /v1/export/sync`
Headers:
- `Authorization: Bearer <token>`
- `Idempotency-Key: <uuid>` (recommended)

Payload: see `API_SPEC.md`. Key validation rules:
- `source`: enum `healthkit`, `financekit`, future sources allowed.
- `device.deviceId` must match authenticated user’s device.
- `range` is required for `health.samples` batches, optional otherwise.
- `health.samples[].metadata` must be stringified values.
- Extended HealthKit sample fields (`document`, `clinicalRecord`, `electrocardiogram`, `audiogram`, `visionPrescription`, `stateOfMind`, `medicationDoseEvent`, `workoutRoute`, `heartbeatSeries`) are optional.
- `health.userAnnotatedMedications` is optional.

Response:
```json
{
  "status": "ok",
  "received": 42,
  "next": { "suggestedSyncAfterSeconds": 21600 }
}
```

### 4.2 Idempotency
Implement idempotent write behavior:
- If `Idempotency-Key` repeats within 24 hours, return the previous response.
- For HealthKit samples, additionally de‑duplicate by `(deviceId, type, start, end, source)`.

## 5. Data Model (Recommended)
Minimum tables (or equivalent collections):
- `users` (id, created_at)
- `devices` (id, user_id, platform, last_seen)
- `passkey_credentials` (id, user_id, public_key, sign_count, rp_id, created_at)
- `user_password_credentials` (id, user_id, username, password_hash, created_at, updated_at)
- `refresh_tokens` (id, token_hash, user_id, device_id, expires_at, created_at, revoked_at)
- `export_batches` (id, user_id, device_id, source, reason, range_start, range_end, received_at, payload_json)

Optional normalized tables:
- `health_samples` (batch_id, type, start, end, quantity_value, unit, category_value, source, device, metadata_json)
- `health_documents` (batch_id, type, title, patient_name, author_name, custodian_name, document_data)
- `health_clinical_records` (batch_id, type, display_name, resource_type, resource_id, fhir_json, source_url)
- `health_ecg_measurements` (batch_id, sample_id, t_offset, voltage, unit)
- `health_heartbeat_series` (batch_id, sample_id, t_offset, preceded_by_gap)
- `health_workout_routes` (batch_id, sample_id, lat, lon, altitude, accuracy, speed, course, timestamp)
- `health_audiograms` (batch_id, sample_id, frequency_hz, sensitivity_dbhl, side)
- `health_state_of_mind` (batch_id, sample_id, kind, valence, labels, associations)
- `health_medication_dose_events` (batch_id, sample_id, schedule_type, log_status, dose_qty, unit, concept_id)
- `health_user_annotated_medications` (batch_id, nickname, is_archived, has_schedule, concept_id)
- `health_characteristics` (batch_id, type, value)
- `activity_summaries` (batch_id, date, active_energy, exercise_time, stand_hours, move_time)
- `finance_accounts` (batch_id, id, name, type, currency_code)
- `finance_transactions` (batch_id, id, account_id, amount, currency_code, date, description, category)
- `finance_balances` (batch_id, account_id, available, current, currency_code, as_of)

## 6. Ingestion Pipeline
- **Sync endpoint** should validate and enqueue writes.
- Persist raw payload immediately in `export_batches`.
- Optional async workers normalize into tables.
- Return response once raw payload is durable (not after async normalization).

## 7. Security & Privacy
- TLS only.
- Encrypt data at rest.
- Separate PII and health/finance data if possible.
- Log minimal sensitive data (redact tokens, credential IDs, and payloads).

## 8. Observability
- Metrics: request rate, latency, error rate, ingest lag.
- Tracing: include request IDs; propagate `Idempotency-Key`.
- Audit: record auth events and export batch metadata.

## 9. Rate Limiting
- Soft limits per device (e.g., 60 req/min) with backoff hints in error responses.

## 10. UAT Checklist (Backend)
- Passkey register + sign‑in end‑to‑end.
- Export sync accepts payloads and deduplicates repeats.
- Token expiry + invalid token errors return proper schema.
