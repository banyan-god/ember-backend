## Ember Backend

Python backend for Ember Pulse with:
- Passkey auth endpoints under `/v1/auth/passkey/*`
- Export ingestion endpoint `/v1/export/sync`
- SQL Server persistence (raw + normalized export data)
- Idempotent export handling and health sample dedupe

## Stack
- Python 3.12+
- FastAPI
- SQLAlchemy
- MS SQL Server (`mssql+pyodbc`)
- `uv` for dependency and task execution

## Project Layout (Spring-Style)
- `src/ember_backend/controller/`: HTTP controllers (route layer)
- `src/ember_backend/service/`: business use-cases
- `src/ember_backend/repository/`: data-access layer
- `src/ember_backend/model/`: persistence entities
- `src/ember_backend/dto/`: request/response DTOs
- `src/ember_backend/security/`: token + WebAuthn security logic
- `src/ember_backend/config/`: settings and DB wiring
- `src/ember_backend/exception/`: error types and global handlers
- `src/ember_backend/support/`: shared utilities and rate limiter

## Quick Start
1. Install dependencies:
   ```bash
   uv sync
   ```
2. Configure environment:
   ```bash
   cp .env.example .env
   ```
3. Ensure database exists:
   ```bash
   uv run python scripts/create_database.py
   ```
4. Run server:
   ```bash
   uv run ember-backend
   ```

Server runs on `http://0.0.0.0:8080`.

## Docker
Run backend container with your existing SQL Server:

1. Create Docker env file:
   ```bash
   cp .env.docker.example .env.docker
   ```
2. Start stack:
   ```bash
   docker compose --env-file .env.docker up --build -d
   ```
3. Verify API:
   ```bash
   curl http://localhost:8080/healthz
   ```
4. Stop stack:
   ```bash
   docker compose --env-file .env.docker down
   ```

Notes:
- `docker-compose.yml` starts only `api`; it expects an external SQL Server.
- Set `SQLSERVER_HOST` in `.env.docker` to your SQL Server host/IP.
- If you need to create the database from the container:
  ```bash
  docker compose --env-file .env.docker run --rm api uv run python scripts/create_database.py
  ```
- Default `WEBAUTHN_MODE` in Docker is `stub` for local development. Set `WEBAUTHN_MODE=strict` in `.env.docker` for full verification.

## Test
```bash
uv run pytest
```

## Environment Variables
Core variables:
- `STORE_TO_SQL`
- `SQLSERVER_HOST`
- `SQLSERVER_PORT`
- `SQLSERVER_DATABASE`
- `SQLSERVER_USER`
- `SQLSERVER_PASSWORD`
- `SQLSERVER_TRUST_SERVER_CERT`

Auth and passkey settings:
- `JWT_SECRET`
- `JWT_ISSUER`
- `JWT_TTL_MINUTES`
- `WEBAUTHN_RP_ID`
- `WEBAUTHN_ALLOWED_ORIGINS`
- `WEBAUTHN_MODE` (`strict` or `stub`)
- `AASA_APP_IDS` (comma-separated `TEAMID.bundleid` entries)

## WebAuthn Env Setup
Use these rules when setting WebAuthn variables:

- `WEBAUTHN_RP_ID`
  - Domain only (no scheme, no path).
  - Must match iOS passkey relying party identifier.
  - Should align with Associated Domains (`webcredentials:<rp_id>`).
  - Example: `WEBAUTHN_RP_ID=your-domain.com`

- `WEBAUTHN_ALLOWED_ORIGINS`
  - Comma-separated HTTPS origins.
  - Include scheme (`https://`), no trailing slash.
  - Must correspond to the RP ID domain(s).
  - Example: `WEBAUTHN_ALLOWED_ORIGINS=https://your-domain.com,https://staging.your-domain.com`

- `WEBAUTHN_MODE`
  - `stub`: local/dev mode with relaxed verification.
  - `strict`: full WebAuthn verification for staging/production.

Recommended:
- Local/dev: `WEBAUTHN_MODE=stub` with your tunnel/dev HTTPS domain.
- Staging/prod: `WEBAUTHN_MODE=strict` with real deployed HTTPS origins.

## Apple App Site Association (AASA)
This backend serves AASA at both Apple-supported paths:
- `/.well-known/apple-app-site-association`
- `/apple-app-site-association`

Configure app bindings with:
- `AASA_APP_IDS=TEAMID.com.your.bundleid[,TEAMID.com.your.otherbundle]`

Example for Ember production:
```env
WEBAUTHN_RP_ID=ember.sabareesh.com
WEBAUTHN_ALLOWED_ORIGINS=https://ember.sabareesh.com
WEBAUTHN_MODE=strict
AASA_APP_IDS=ABCDE12345.com.sabareesh.emberpulse
```

Verification checklist:
1. `curl -i https://ember.sabareesh.com/.well-known/apple-app-site-association`
2. `curl -i https://ember.sabareesh.com/apple-app-site-association`
3. Confirm `HTTP 200` and JSON includes `webcredentials.apps` with your app id.

## API
Implements the contract defined in:
- `API_SPEC.md`
- `docs/BACKEND_SPEC.md`

## Docs
- `AGENTS.md`
- `ARCHITECTURE.md`
- `docs/DEVELOPMENT.md`
