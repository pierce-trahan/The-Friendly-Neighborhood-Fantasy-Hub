from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from friendly_hub.core.errors import HubError

logger = logging.getLogger("friendly_hub.api")


def _correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unavailable")


def _payload(
    *,
    code: str,
    message: str,
    action: str,
    severity: str,
    retryable: bool,
    correlation_id: str,
    field_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "action": action,
        "severity": severity,
        "retryable": retryable,
        "correlation_id": correlation_id,
    }
    if field_errors:
        error["field_errors"] = field_errors
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HubError)
    async def handle_hub_error(request: Request, exc: HubError) -> JSONResponse:
        correlation_id = _correlation_id(request)
        logger.warning(
            "request.failed",
            extra={"correlation_id": correlation_id, "error_code": exc.code},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(
                code=exc.code,
                message=exc.message,
                action=exc.action,
                severity=exc.severity,
                retryable=exc.retryable,
                correlation_id=correlation_id,
                field_errors=exc.field_errors,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        field_errors = [
            {
                "path": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_payload(
                code="VALIDATION.REQUEST.INVALID",
                message="Some information could not be accepted.",
                action="Review the highlighted fields and try again.",
                severity="error",
                retryable=False,
                correlation_id=_correlation_id(request),
                field_errors=field_errors,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = _correlation_id(request)
        logger.exception(
            "request.unexpected",
            extra={"correlation_id": correlation_id, "error_code": "INTERNAL.UNEXPECTED"},
        )
        return JSONResponse(
            status_code=500,
            content=_payload(
                code="INTERNAL.REQUEST.UNEXPECTED",
                message="The Hub encountered an unexpected problem.",
                action="Your saved data should be unchanged. Restart the Hub and try again.",
                severity="error",
                retryable=True,
                correlation_id=correlation_id,
            ),
        )
