"""A small, read-only JSON-RPC MCP endpoint for gateway-mediated tool calls."""

from __future__ import annotations

import hmac
import logging
import os
from collections.abc import Mapping
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from .safe_logging import safe_log


MCP_SECRET_HEADER = "x-appservice-mcp-secret"
MCP_PROTOCOL_VERSION = "2025-06-18"


class ReadOnlyMcpServer:
    """Serves a fixed allow-list of operational tools after backend authentication."""

    def __init__(self, backend_secret: str | None) -> None:
        self._backend_secret = backend_secret or ""

    def _authorized(self, request: Request) -> bool:
        supplied = request.headers.get(MCP_SECRET_HEADER, "")
        return bool(self._backend_secret) and hmac.compare_digest(supplied, self._backend_secret)

    def _server_info(self) -> dict[str, Any]:
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "appservice-ops", "version": "0.1.0"},
        }

    def _tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "get_service_status",
                "description": "Return non-sensitive App Service runtime status.",
                "inputSchema": {"type": "object", "additionalProperties": False},
            },
            {
                "name": "get_deployment_context",
                "description": "Return non-sensitive site and slot context.",
                "inputSchema": {"type": "object", "additionalProperties": False},
            },
        ]

    def _tool_result(self, name: str) -> dict[str, Any] | None:
        if name == "get_service_status":
            return {
                "service": "app-service-ai-gateway-tier",
                "status": "healthy",
                "instance": os.environ.get("WEBSITE_INSTANCE_ID", "local"),
            }
        if name == "get_deployment_context":
            return {
                "site": os.environ.get("WEBSITE_SITE_NAME", "local"),
                "slot": os.environ.get("WEBSITE_SLOT_NAME", "Production"),
                "region": os.environ.get("REGION_NAME", "local"),
            }
        return None

    async def get(self, request: Request) -> Response:
        if not self._authorized(request):
            return JSONResponse({"error": "backend authentication required"}, status_code=401)
        return JSONResponse({"jsonrpc": "2.0", "result": self._server_info()})

    async def post(self, request: Request) -> Response:
        if not self._authorized(request):
            return JSONResponse({"error": "backend authentication required"}, status_code=401)
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({"error": "invalid JSON-RPC request"}, status_code=400)
        if not isinstance(body, Mapping):
            return JSONResponse({"error": "invalid JSON-RPC request"}, status_code=400)

        method = body.get("method")
        message_id = body.get("id")
        if method == "initialize":
            return JSONResponse({"jsonrpc": "2.0", "id": message_id, "result": self._server_info()})
        if method == "notifications/initialized":
            return Response(status_code=202)
        if method == "tools/list":
            return JSONResponse(
                {"jsonrpc": "2.0", "id": message_id, "result": {"tools": self._tools()}}
            )
        if method == "tools/call":
            params = body.get("params")
            name = params.get("name") if isinstance(params, Mapping) else None
            result = self._tool_result(name) if isinstance(name, str) else None
            if result is None:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": message_id,
                        "error": {"code": -32601, "message": "read-only tool not found"},
                    }
                )
            safe_log(
                logging.getLogger("app.mcp"),
                "mcp_tool_called",
                {"event": "mcp_tool_called", "route": "/mcp"},
            )
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {"content": [{"type": "text", "text": str(result)}]},
                }
            )
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {"code": -32601, "message": "method not found"},
            }
        )
