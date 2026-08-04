"""Request correlation without collecting request content."""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_VALID_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
correlation_id_context: ContextVar[str] = ContextVar("correlation_id", default="")


def correlation_id_for(request: Request) -> str:
    candidate = request.headers.get("x-correlation-id", "")
    return candidate if _VALID_CORRELATION_ID.fullmatch(candidate) else str(uuid.uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Adds a safe correlation identifier to each response and async context."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        correlation_id = correlation_id_for(request)
        token = correlation_id_context.set(correlation_id)
        request.state.correlation_id = correlation_id
        try:
            response = await call_next(request)
        finally:
            correlation_id_context.reset(token)
        response.headers["x-correlation-id"] = correlation_id
        return response
