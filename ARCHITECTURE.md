# Architecture

## Core Flow
1. Device requests passkey registration/authentication challenge.
2. Backend validates WebAuthn response and issues a short-lived bearer token.
3. Client uploads source payloads to `/v1/export/sync`.
4. Backend persists raw batch payload + normalized records and returns deterministic acknowledgement.

## Key Components
- `main.py`: FastAPI app wiring, endpoint handlers, error handlers, middleware.
- `webauthn_service.py`: WebAuthn verification service interface with strict/stub implementations.
- `auth.py`: bearer token creation/validation and auth dependency.
- `schemas.py`: request/response validation and business rules.
- `models.py`: SQLAlchemy persistence model for auth and export data.
- `db.py`: engine/session factory and schema initialization.
- `rate_limit.py`: in-memory soft limiter with retry hints.

## Extensibility
- Add new export sources by extending payload handling without breaking existing source contracts.
- Swap WebAuthn verification behavior via `WEBAUTHN_MODE` and `WebAuthnService`.
- Supports SQL Server by default and sqlite for test/local fallback.
