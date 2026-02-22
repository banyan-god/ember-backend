# Architecture

## Core Flow
1. Device requests passkey registration/authentication challenge.
2. Backend validates WebAuthn response and issues a short-lived bearer token.
3. Client uploads source payloads to `/v1/export/sync`.
4. Backend persists raw batch payload + normalized records and returns deterministic acknowledgement.

## Key Components
- `controller/*`: route/controller layer.
- `service/*`: business logic orchestration.
- `repository/*`: database data-access logic.
- `model/entities.py`: SQLAlchemy persistence entities.
- `dto/api.py`: request/response DTOs and validation rules.
- `security/*`: token and WebAuthn security flows.
- `config/*`: settings and DB/session setup.
- `exception/*`: typed API errors and global exception mapping.
- `support/*`: cross-cutting utility helpers.

## Extensibility
- Add new export sources by extending payload handling without breaking existing source contracts.
- Swap WebAuthn verification behavior via `WEBAUTHN_MODE` and `WebAuthnService`.
- Supports SQL Server by default and sqlite for test/local fallback.
