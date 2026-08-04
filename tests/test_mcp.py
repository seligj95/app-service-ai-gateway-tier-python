from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import create_app
from app.mcp import MCP_SECRET_HEADER


def test_direct_mcp_is_denied_without_backend_secret(settings) -> None:
    client = TestClient(create_app(settings))
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 401
    assert "opaque-backend-value" not in response.text


def test_mcp_only_exposes_read_only_tools(settings) -> None:
    client = TestClient(create_app(settings))
    headers = {MCP_SECRET_HEADER: settings.mcp_backend_secret}
    tools = client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    ).json()["result"]["tools"]
    assert {tool["name"] for tool in tools} == {"get_service_status", "get_deployment_context"}

    response = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "delete_everything", "arguments": {}},
        },
    )
    assert response.json()["error"]["code"] == -32601
