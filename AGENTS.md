# Repository Guidelines

## Project Structure & Module Organization
- `src/ember_backend/controller/` route/controller layer.
- `src/ember_backend/service/` business logic layer.
- `src/ember_backend/repository/` data access layer.
- `src/ember_backend/model/` ORM entities.
- `src/ember_backend/dto/` request/response DTO models.
- `src/ember_backend/security/` token + WebAuthn security components.
- `src/ember_backend/config/` settings and database/session wiring.
- `src/ember_backend/exception/` API exceptions and handler mapping.
- `src/ember_backend/support/` shared utilities.
- `tests/` pytest suite for endpoint and behavior coverage.
- `scripts/` operational scripts (database bootstrap).
- `docs/` engineering docs (`DEVELOPMENT.md`, `BACKEND_SPEC.md`).
- Root docs: `API_SPEC.md`, `ARCHITECTURE.md`, `README.md`.

## Build, Test, and Development Commands
- Install deps:
  ```sh
  uv sync --all-groups
  ```
- Run tests:
  ```sh
  uv run pytest
  ```
- Run API locally:
  ```sh
  uv run ember-backend
  ```
- Ensure SQL Server database exists:
  ```sh
  uv run python scripts/create_database.py
  ```
- Run Docker stack:
  ```sh
  cp .env.docker.example .env.docker
  docker compose --env-file .env.docker up --build -d
  ```

## Coding Style & Naming Conventions
- Python indentation: 4 spaces; explicit typing for non-trivial paths.
- Classes: `UpperCamelCase`; functions/variables/modules: `snake_case`.
- Keep route handlers thin; isolate domain logic in dedicated helpers/services.
- Do not commit secrets or environment-specific credentials.

## SOLID Principles
- Single Responsibility: separate transport, validation, auth, and persistence.
- Open/Closed: add new export source types without rewriting existing source flows.
- Liskov Substitution: `WebAuthnService` implementations (`strict`/`stub`) remain interchangeable.
- Interface Segregation: keep request/response models and service contracts focused.
- Dependency Inversion: inject settings/session/service dependencies rather than hard-coding globals.

## Testing Guidelines
- Framework: pytest.
- Naming: files start with `test_`; test functions start with `test_`.
- Required coverage:
  - all public API endpoints
  - success and error schema cases
  - auth/token checks
  - export idempotency and dedupe behavior
  - spec rules (`range`, metadata stringification, device binding)

## Quality Bar & Validation Loop
- No merge-ready change without green tests.
- Close the loop after changes:
  1. `uv sync --all-groups`
  2. `uv run pytest`
  3. optional local smoke checks:
     - `curl http://localhost:8080/healthz`
     - passkey begin/finish flow
     - export sync call with `Idempotency-Key`
- Document exact commands and outcomes in PR/commit notes.

## Commit & Pull Request Guidelines
- Follow Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).
- Include in PR description:
  - change summary
  - testing commands + outcomes
  - config or migration notes
  - linked issue/ticket if available

## Security & Configuration Tips
- Keep `.env` and `.env.docker` local only.
- Use strong `JWT_SECRET` (32+ bytes) in non-dev environments.
- Keep `WEBAUTHN_RP_ID` and `WEBAUTHN_ALLOWED_ORIGINS` aligned with deployment domains.
- Prefer TLS-terminated deployments and least-privilege DB credentials.
