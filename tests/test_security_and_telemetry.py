from __future__ import annotations

import logging
import sys
from types import ModuleType

import httpx
import pytest

from app.agent import GatewayAgent
from app.safe_logging import safe_log
from app.telemetry import safe_telemetry_attributes


def test_safe_logging_never_records_secret_values(caplog) -> None:
    logger = logging.getLogger("test.safe")
    with caplog.at_level(logging.INFO):
        safe_log(
            logger,
            "gateway_call",
            {
                "correlation_id": "trace-1",
                "api_key": "opaque-runtime-value",
                "prompt": "private prompt",
            },
        )
    assert "opaque-runtime-value" not in caplog.text
    assert "private prompt" not in caplog.text
    assert "trace-1" in caplog.text


def test_telemetry_attributes_exclude_prompt_response_and_secrets() -> None:
    attributes = safe_telemetry_attributes(
        {
            "correlation_id": "trace-1",
            "http.route": "/api/chat/stream",
            "prompt": "private prompt",
            "response": "private response",
            "api-key": "opaque-runtime-value",
        }
    )
    assert attributes == {"correlation_id": "trace-1", "http.route": "/api/chat/stream"}


@pytest.mark.asyncio
async def test_agent_framework_uses_explicit_gateway_transport_and_mcp_route(
    settings, monkeypatch, caplog
) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs) -> None:
            captured["transport"] = kwargs
            self.closed = False

        async def close(self) -> None:
            self.closed = True
            captured["transport_closed"] = self.closed

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured["client"] = kwargs

    class FakeMcp:
        def __init__(self, **kwargs) -> None:
            captured["mcp"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

    class FakeAgent:
        def __init__(self, **kwargs) -> None:
            captured["agent"] = kwargs

    framework = ModuleType("agent_framework")
    framework.Agent = FakeAgent
    framework.MCPStreamableHTTPTool = FakeMcp
    framework_openai = ModuleType("agent_framework.openai")
    framework_openai.OpenAIChatCompletionClient = FakeClient
    openai = ModuleType("openai")
    openai.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "agent_framework", framework)
    monkeypatch.setitem(sys.modules, "agent_framework.openai", framework_openai)
    monkeypatch.setitem(sys.modules, "openai", openai)

    with caplog.at_level(logging.INFO):
        async with GatewayAgent(settings)._connected_agent():
            pass

    client = captured["client"]
    mcp = captured["mcp"]
    transport = captured["transport"]
    assert isinstance(client, dict)
    assert isinstance(mcp, dict)
    assert isinstance(transport, dict)
    assert transport["base_url"] == settings.gateway_openai_url
    assert transport["default_headers"] == {"api-key": settings.gateway_api_key}
    assert transport["max_retries"] == 0
    assert isinstance(transport["timeout"], httpx.Timeout)
    assert transport["timeout"].read == settings.request_timeout_seconds
    assert client["async_client"].closed is True
    assert captured["transport_closed"] is True
    assert mcp["url"] == settings.gateway_mcp_url
    assert mcp["tool_name_prefix"] == "appservice-ops"
    assert mcp["allowed_tools"] == (
        "get_service_status",
        "get_deployment_context",
    )
    assert mcp["header_provider"]({}) == {"api-key": settings.gateway_api_key}
    assert settings.gateway_api_key not in caplog.text
