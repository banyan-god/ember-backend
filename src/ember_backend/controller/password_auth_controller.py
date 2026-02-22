from __future__ import annotations

from fastapi import APIRouter, Depends

from ember_backend.controller.dependencies import get_auth_service
from ember_backend.dto.api import AuthTokensResponse, PasswordLoginRequest, PasswordRegisterRequest
from ember_backend.service.auth_service import AuthService

router = APIRouter(prefix="/v1/auth/password", tags=["auth"])


@router.post("/register", response_model=AuthTokensResponse)
def password_register(payload: PasswordRegisterRequest, service: AuthService = Depends(get_auth_service)) -> AuthTokensResponse:
    return service.password_register(payload)


@router.post("/login", response_model=AuthTokensResponse)
def password_login(payload: PasswordLoginRequest, service: AuthService = Depends(get_auth_service)) -> AuthTokensResponse:
    return service.password_login(payload)
