from __future__ import annotations

from fastapi import APIRouter, Depends

from ember_backend.controller.dependencies import get_auth_service
from ember_backend.dto.api import AuthTokensResponse, RefreshTokenRequest
from ember_backend.service.auth_service import AuthService

router = APIRouter(prefix="/v1/auth/token", tags=["auth"])


@router.post("/refresh", response_model=AuthTokensResponse)
def refresh_token(payload: RefreshTokenRequest, service: AuthService = Depends(get_auth_service)) -> AuthTokensResponse:
    return service.refresh_access_token(payload)
