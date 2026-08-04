from __future__ import annotations

from typing import Any

import agent_framework
import agent_framework.openai as agent_framework_openai
import openai
import pytest
from agent_framework import MCPStreamableHTTPTool
from mcp import types

from app.agent import GatewayAgent


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
