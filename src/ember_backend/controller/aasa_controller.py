from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["aasa"])


def _aasa_payload(request: Request) -> dict:
    app_ids = request.app.state.settings.apple_app_site_association_app_ids
    return {
        "webcredentials": {
            "apps": app_ids,
        }
    }


@router.get("/.well-known/apple-app-site-association")
def aasa_well_known(request: Request) -> JSONResponse:
    return JSONResponse(content=_aasa_payload(request), media_type="application/json")


@router.get("/apple-app-site-association")
def aasa_root(request: Request) -> JSONResponse:
    return JSONResponse(content=_aasa_payload(request), media_type="application/json")
