# Development Guide

## Overview
Ember Backend is a Python API service for Ember Pulse passkey auth and multi-source data sync.

## Prerequisites
- Python 3.12+
- `uv`
- SQL Server reachable from local environment (or Docker Compose stack)

## Local Configuration
1. Copy env template:
   ```sh
   cp .env.example .env
   ```
2. Set database and auth values in `.env`.
3. Ensure database exists:
   ```sh
   uv run python scripts/create_database.py
   ```

### WebAuthn Environment Values
- `WEBAUTHN_RP_ID`
  - Domain only (no `https://`, no path).
  - Must match the iOS relying party identifier and associated domains.
- `WEBAUTHN_ALLOWED_ORIGINS`
  - Comma-separated HTTPS origins.
  - Example: `https://your-domain.com,https://staging.your-domain.com`
- `WEBAUTHN_MODE`
  - `stub` for local/dev.
  - `strict` for staging/production.

Example:
```sh
WEBAUTHN_RP_ID=your-domain.com
WEBAUTHN_ALLOWED_ORIGINS=https://your-domain.com
WEBAUTHN_MODE=stub
```

## Run
```sh
uv sync --all-groups
uv run ember-backend
```

## Test
```sh
uv run pytest
```

## Docker Workflow
```sh
cp .env.docker.example .env.docker
# Set SQLSERVER_HOST/credentials for your existing SQL Server
docker compose --env-file .env.docker up --build -d
curl http://localhost:8080/healthz
docker compose --env-file .env.docker down
```

Optional database bootstrap from container:
```sh
docker compose --env-file .env.docker run --rm api uv run python scripts/create_database.py
```

## Validation Loop (Required)
1. Run tests.
2. Smoke-check `/healthz`.
3. Validate auth begin/finish and one export sync call.
4. Record commands and outcomes in PR/commit notes.
