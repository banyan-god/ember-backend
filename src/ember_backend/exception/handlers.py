from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ember_backend.exception.api_error import APIError, to_error_payload


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def api_error_handler(_request: Request, exc: APIError):
        return JSONResponse(status_code=exc.status_code, content=to_error_payload(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_request: Request, exc: RequestValidationError):
        details: dict[str, str] = {}
        for err in exc.errors():
            location = ".".join(str(part) for part in err.get("loc", []))
            details[location] = err.get("msg", "invalid")
        return JSONResponse(
            status_code=400,
            content=to_error_payload("invalid_request", "Invalid request payload", details),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, _exc: Exception):
        return JSONResponse(
            status_code=500,
            content=to_error_payload("internal_error", "Unexpected server error"),
        )
