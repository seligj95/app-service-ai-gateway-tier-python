from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import agent_framework
import agent_framework.openai as agent_framework_openai
import openai
import pytest
from agent_framework import MCPStreamableHTTPTool
from mcp import types

from app.agent import (
    DEPLOYMENT_CONTEXT_TOOL,
    SERVICE_STATUS_TOOL,
    GatewayAgent,
    _required_tool_for,
)


@pytest.mark.asyncio
async def test_connected_agent_exposes_prefixed_mcp_tools_and_calls_remote_tool(
    settings, monkeypatch
) -> None:
    remote_calls: list[tuple[str, dict[str, Any]]] = []

    class FakeClientSession:
        _request_id = 1
        _server_capabilities = types.ServerCapabilities(
            tools=types.ToolsCapability(listChanged=False)
        )

        async def send_ping(self) -> None:
            return None

        async def list_tools(self, params=None) -> types.ListToolsResult:
            return types.ListToolsResult(
                tools=[
                    types.Tool(
                        name="appservice-ops_get_service_status",
                        description="Return service status.",
                        inputSchema={"type": "object", "properties": {}},
                    ),
                    types.Tool(
                        name="appservice-ops_get_deployment_context",
                        description="Return deployment context.",
                        inputSchema={"type": "object", "properties": {}},
                    ),
                ]
            )

        async def call_tool(
            self,
            name: str,
            arguments: dict[str, Any] | None = None,
            meta: dict[str, Any] | None = None,
        ) -> types.CallToolResult:
            remote_calls.append((name, arguments or {}))
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text="{'service': 'app-service-ai-gateway-tier', "
                        "'status': 'healthy', 'instance': 'test-instance'}",
                    )
                ]
            )

    session = FakeClientSession()
    framework_mcp_tool = MCPStreamableHTTPTool

    class SessionBackedMcpTool(framework_mcp_tool):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(
                **kwargs,
                session=session,
                load_prompts=False,
            )

    class FakeAsyncOpenAI:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def close(self) -> None:
            return None

    class FakeModelClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

    class FakeAgent:
        def __init__(self, *, tools: Any, **_kwargs: Any) -> None:
            self.tools = tools

    monkeypatch.setattr(agent_framework, "MCPStreamableHTTPTool", SessionBackedMcpTool)
    monkeypatch.setattr(agent_framework, "Agent", FakeAgent)
    monkeypatch.setattr(agent_framework_openai, "OpenAIChatCompletionClient", FakeModelClient)
    monkeypatch.setattr(openai, "AsyncOpenAI", FakeAsyncOpenAI)

    async with GatewayAgent(settings)._connected_agent() as connected_agent:
        functions = {function.name: function for function in connected_agent.tools.functions}
        assert set(functions) == {
            "appservice-ops_get_service_status",
            "appservice-ops_get_deployment_context",
        }

        result = await functions["appservice-ops_get_service_status"].invoke(arguments={})
        result_text = " ".join(
            str(content.text) for content in result if getattr(content, "text", None)
        )

    assert remote_calls == [("appservice-ops_get_service_status", {})]
    assert "'service': 'app-service-ai-gateway-tier'" in result_text
    assert "'status': 'healthy'" in result_text
    assert "'instance': 'test-instance'" in result_text


def test_operational_prompts_select_matching_required_tool() -> None:
    assert _required_tool_for("What is the current service status?") == SERVICE_STATUS_TOOL
    assert (
        _required_tool_for("Which site and deployment slot are you running in?")
        == DEPLOYMENT_CONTEXT_TOOL
    )
    assert _required_tool_for("Explain the App Service and AI Gateway boundary.") is None
    assert _required_tool_for("Explain the service status banner.") is None
    assert _required_tool_for("Discuss deployment context tradeoffs.") is None


@pytest.mark.asyncio
async def test_attempt_requires_selected_tool_but_keeps_general_chat_automatic(
    settings, monkeypatch
) -> None:
    captured_options: list[dict[str, Any] | None] = []

    class FakeConnectedAgent:
        def run(self, _message: str, **kwargs: Any) -> AsyncIterator[Any]:
            captured_options.append(kwargs.get("options"))

            async def updates() -> AsyncIterator[Any]:
                yield type("Update", (), {"text": "ok"})()

            return updates()

    @asynccontextmanager
    async def connected_agent() -> AsyncIterator[FakeConnectedAgent]:
        yield FakeConnectedAgent()

    gateway_agent = GatewayAgent(settings)
    monkeypatch.setattr(gateway_agent, "_connected_agent", connected_agent)

    assert [
        chunk
        async for chunk in gateway_agent._attempt(
            "What is the current service status?", "correlation-id"
        )
    ] == ["ok"]
    assert [
        chunk
        async for chunk in gateway_agent._attempt(
            "Explain the App Service and AI Gateway boundary.", "correlation-id"
        )
    ] == ["ok"]

    assert captured_options == [
        {
            "tool_choice": {
                "mode": "required",
                "required_function_name": SERVICE_STATUS_TOOL,
            }
        },
        None,
    ]
