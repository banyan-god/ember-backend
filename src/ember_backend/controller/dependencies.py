from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ember_backend.config.database import get_db_session
from ember_backend.repository.auth_repository import AuthRepository
from ember_backend.repository.export_repository import ExportRepository
from ember_backend.service.auth_service import AuthService
from ember_backend.service.export_service import ExportService


def get_auth_service(request: Request, db: Session = Depends(get_db_session)) -> AuthService:
    return AuthService(
        repository=AuthRepository(db),
        settings=request.app.state.settings,
        webauthn_service=request.app.state.webauthn,
        token_service=request.app.state.token_service,
        rate_limiter=request.app.state.rate_limiter,
    )


def get_export_service(request: Request, db: Session = Depends(get_db_session)) -> ExportService:
    return ExportService(
        repository=ExportRepository(db),
        settings=request.app.state.settings,
        rate_limiter=request.app.state.rate_limiter,
    )
