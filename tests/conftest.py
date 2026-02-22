from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ember_backend.config import Settings
from ember_backend.db import build_engine_and_session
from ember_backend.main import create_app


@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        STORE_TO_SQL=False,
        DATABASE_URL=f"sqlite:///{tmp_path / 'ember_test.db'}",
        JWT_SECRET="test-secret-with-sufficient-length-32-bytes",
        JWT_ISSUER="ember-backend-tests",
        WEBAUTHN_RP_ID="example.com",
        WEBAUTHN_ALLOWED_ORIGINS="https://example.com",
        WEBAUTHN_MODE="stub",
    )


@pytest.fixture()
def engine_and_session(test_settings: Settings) -> Generator[tuple[Engine, sessionmaker[Session]], None, None]:
    engine, session_factory = build_engine_and_session(test_settings.sqlalchemy_database_url)
    try:
        yield engine, session_factory
    finally:
        engine.dispose()


@pytest.fixture()
def app(test_settings: Settings, engine_and_session: tuple[Engine, sessionmaker[Session]]):
    return create_app(settings=test_settings, engine_and_session=engine_and_session)


@pytest.fixture()
def client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session(engine_and_session: tuple[Engine, sessionmaker[Session]]) -> Generator[Session, None, None]:
    _, session_factory = engine_and_session
    with session_factory() as session:
        yield session
