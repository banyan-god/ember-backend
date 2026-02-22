from __future__ import annotations

from fastapi import APIRouter, Depends

from ember_backend.controller.dependencies import get_auth_service
from ember_backend.dto.api import (
    AuthenticateBeginRequest,
    AuthenticateBeginResponse,
    AuthenticateFinishRequest,
    RegisterBeginRequest,
    RegisterBeginResponse,
    RegisterFinishRequest,
    TokenResponse,
)
from ember_backend.service.auth_service import AuthService

router = APIRouter(prefix="/v1/auth/passkey", tags=["auth"])


@router.post("/register/begin", response_model=RegisterBeginResponse)
def register_begin(payload: RegisterBeginRequest, service: AuthService = Depends(get_auth_service)) -> RegisterBeginResponse:
    return service.register_begin(payload)


@router.post("/register/finish", response_model=TokenResponse)
def register_finish(payload: RegisterFinishRequest, service: AuthService = Depends(get_auth_service)) -> TokenResponse:
    return service.register_finish(payload)


@router.post("/authenticate/begin", response_model=AuthenticateBeginResponse)
def authenticate_begin(
    payload: AuthenticateBeginRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthenticateBeginResponse:
    return service.authenticate_begin(payload)


@router.post("/authenticate/finish", response_model=TokenResponse)
def authenticate_finish(
    payload: AuthenticateFinishRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return service.authenticate_finish(payload)
