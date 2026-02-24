from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from ember_backend.controller.dependencies import get_export_service
from ember_backend.dto.api import BulkExportSyncRequest, BulkExportSyncResponse, ExportSyncRequest, ExportSyncResponse
from ember_backend.security.token_service import AuthContext, require_auth
from ember_backend.service.export_service import ExportService, ReplayResponse

router = APIRouter(prefix="/v1/export", tags=["export"])


@router.post("/sync", response_model=ExportSyncResponse)
def export_sync(
    payload: ExportSyncRequest,
    auth: AuthContext = Depends(require_auth),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    service: ExportService = Depends(get_export_service),
) -> ExportSyncResponse | JSONResponse:
    result = service.sync(payload, auth, idempotency_key)
    if isinstance(result, ReplayResponse):
        return JSONResponse(status_code=result.status_code, content=result.body)
    return result


@router.post("/sync/bulk", response_model=BulkExportSyncResponse)
def export_sync_bulk(
    payload: BulkExportSyncRequest,
    auth: AuthContext = Depends(require_auth),
    service: ExportService = Depends(get_export_service),
) -> BulkExportSyncResponse:
    return service.sync_bulk(payload, auth)
