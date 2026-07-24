from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

correlation_id_context: ContextVar[str] = ContextVar("correlation_id", default="")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        correlation_id = str(uuid4())
        request.state.correlation_id = correlation_id
        token = correlation_id_context.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            correlation_id_context.reset(token)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
