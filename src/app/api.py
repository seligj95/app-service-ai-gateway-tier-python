"""FastAPI application, clean chat UI, health endpoints, and SSE transport."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from opentelemetry import trace
from pydantic import BaseModel, Field

from .agent import GatewayAgent
from .config import ConfigurationError, Settings
from .correlation import CorrelationIdMiddleware
from .errors import GatewayFailure, PUBLIC_ERROR_MESSAGES
from .mcp import ReadOnlyMcpServer
from .safe_logging import safe_log
from .telemetry import configure_telemetry, set_safe_attributes


logger = logging.getLogger("app.api")
APPLICATION_DIRECTORY = Path(__file__).parent
templates = Jinja2Templates(directory=APPLICATION_DIRECTORY / "templates")


class StreamingAgent(Protocol):
    async def stream(self, message: str, correlation_id: str) -> AsyncIterator[str]: ...


@dataclass
class ApplicationState:
    settings: Settings | None
    configuration_error: ConfigurationError | None
    agent: StreamingAgent | None
    telemetry_enabled: bool


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def create_app(
    settings: Settings | None = None,
    agent: StreamingAgent | None = None,
) -> FastAPI:
    """Create an app that stays diagnosable when gateway settings are unavailable."""

    configuration_error: ConfigurationError | None = None
    if settings is None:
        try:
            settings = Settings.from_env()
        except ConfigurationError as exc:
            configuration_error = exc

    telemetry_enabled = configure_telemetry(
        settings.application_insights_connection_string if settings else None
    )
    app_state = ApplicationState(
        settings=settings,
        configuration_error=configuration_error,
        agent=agent or (GatewayAgent(settings) if settings else None),
        telemetry_enabled=telemetry_enabled,
    )

    app = FastAPI(
        title="App Service AI Gateway tier sample",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )
    app.state.application = app_state
    app.add_middleware(CorrelationIdMiddleware)
    app.mount("/static", StaticFiles(directory=APPLICATION_DIRECTORY / "static"), name="static")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": {"code": "invalid_request"}})

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "configured": app_state.settings is not None,
                "site_name": app_state.settings.site_name if app_state.settings else "local",
                "slot_name": app_state.settings.slot_name if app_state.settings else "Production",
            },
        )

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse(
            {
                "status": "healthy",
                "service": "app-service-ai-gateway-tier",
                "gatewayConfigured": app_state.settings is not None,
            }
        )

    @app.get("/status")
    async def status(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ready" if app_state.settings else "configuration_required",
                "stableGatewayModel": app_state.settings.gateway_model if app_state.settings else None,
                "telemetryEnabled": app_state.telemetry_enabled,
                "correlationId": request.state.correlation_id,
            }
        )

    mcp_server = ReadOnlyMcpServer(
        app_state.settings.mcp_backend_secret if app_state.settings else None
    )
    app.add_api_route("/mcp", mcp_server.get, methods=["GET"])
    app.add_api_route("/mcp", mcp_server.post, methods=["POST"])

    @app.post("/api/chat/stream")
    async def chat_stream(request: Request, payload: ChatRequest) -> StreamingResponse:
        if app_state.agent is None or app_state.settings is None:
            raise HTTPException(status_code=503, detail={"code": "gateway_not_configured"})
        correlation_id = request.state.correlation_id

        async def events() -> AsyncIterator[str]:
            tracer = trace.get_tracer("app-service-ai-gateway-tier")
            span_context = tracer.start_as_current_span("gateway.chat") if tracer else nullcontext()
            with span_context as span:
                if span:
                    set_safe_attributes(
                        span,
                        {
                            "correlation_id": correlation_id,
                            "http.route": "/api/chat/stream",
                            "service.name": "app-service-ai-gateway-tier",
                        },
                    )
                safe_log(
                    logger,
                    "chat_stream_started",
                    {"event": "chat_stream_started", "correlation_id": correlation_id, "route": "/api/chat/stream"},
                )
                yield _sse("meta", {"correlationId": correlation_id})
                try:
                    async for chunk in app_state.agent.stream(payload.message, correlation_id):
                        yield _sse("delta", {"text": chunk})
                except GatewayFailure as failure:
                    if span:
                        set_safe_attributes(
                            span,
                            {
                                "gateway.status_code": failure.status_code or 503,
                                "gateway.error_code": failure.code,
                            },
                        )
                    safe_log(
                        logger,
                        "chat_stream_failed",
                        {
                            "event": "chat_stream_failed",
                            "correlation_id": correlation_id,
                            "status_code": failure.status_code or 503,
                            "error_code": failure.code,
                        },
                    )
                    yield _sse(
                        "error",
                        {
                            "code": failure.code,
                            "message": PUBLIC_ERROR_MESSAGES.get(
                                failure.code, "The gateway could not process the request."
                            ),
                        },
                    )
                finally:
                    yield _sse("done", {})

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Correlation-Id": correlation_id,
            },
        )

    return app
