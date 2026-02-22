from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from sqlalchemy.orm import Session, sessionmaker

from ember_backend.config.database import build_engine_and_session, create_schema
from ember_backend.config.settings import Settings, get_settings
from ember_backend.controller.auth_controller import router as auth_router
from ember_backend.controller.export_controller import router as export_router
from ember_backend.controller.health_controller import router as health_router
from ember_backend.exception.handlers import register_exception_handlers
from ember_backend.security.token_service import TokenService
from ember_backend.security.webauthn_service import WebAuthnService, build_webauthn_service
from ember_backend.support.rate_limit import InMemoryRateLimiter


def create_app(
    settings: Settings | None = None,
    *,
    engine_and_session: tuple[Any, sessionmaker[Session]] | None = None,
    webauthn_service: WebAuthnService | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    if engine_and_session is None:
        engine_and_session = build_engine_and_session(settings.sqlalchemy_database_url)
    engine, session_factory = engine_and_session

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        create_schema(app_instance.state.engine)
        yield

    app = FastAPI(title="Ember Backend", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.webauthn = webauthn_service or build_webauthn_service(settings)
    app.state.token_service = TokenService(settings)
    app.state.rate_limiter = InMemoryRateLimiter(settings.rate_limit_per_minute)

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(export_router)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("ember_backend.main:app", host="0.0.0.0", port=8080, reload=False)
