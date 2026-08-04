"""Microsoft Agent Framework adapter constrained to the dedicated AI Gateway."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from .config import ConfigurationError, Settings
from .errors import GatewayFailure, classify_gateway_exception
from .retry import RetryPolicy, retry_stream


class GatewayAgent:
    """Runs Agent Framework with model and MCP traffic pinned to gateway routes."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @asynccontextmanager
    async def _connected_agent(self) -> AsyncIterator[Any]:
        try:
            from agent_framework import Agent, MCPStreamableHTTPTool
            from agent_framework.openai import OpenAIChatCompletionClient
            from httpx import Timeout
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ConfigurationError("Microsoft Agent Framework is unavailable.") from exc

        gateway_headers = {"api-key": self._settings.gateway_api_key}
        openai_client = AsyncOpenAI(
            api_key=self._settings.gateway_api_key,
            base_url=self._settings.gateway_openai_url,
            default_headers=gateway_headers,
            timeout=Timeout(self._settings.request_timeout_seconds),
            max_retries=0,
        )
        try:
            model_client = OpenAIChatCompletionClient(
                model=self._settings.gateway_model,
                async_client=openai_client,
            )
            mcp_tool = MCPStreamableHTTPTool(
                name="appservice-ops",
                url=self._settings.gateway_mcp_url,
                request_timeout=self._settings.mcp_timeout_seconds,
                allowed_tools=(
                    "appservice-ops_get_service_status",
                    "appservice-ops_get_deployment_context",
                ),
                header_provider=lambda _kwargs: gateway_headers,
            )
            agent = Agent(
                client=model_client,
                name="AppServiceGatewayAgent",
                instructions=(
                    "You are a concise App Service operations assistant. Use only the supplied "
                    "read-only tools when operational context is necessary. For live service or "
                    "deployment questions, you MUST call the matching appservice-ops tool before "
                    "answering. Never claim lack of access when a matching tool is available."
                ),
                tools=mcp_tool,
            )
            async with mcp_tool:
                yield agent
        finally:
            await openai_client.close()

    async def _attempt(self, message: str, correlation_id: str) -> AsyncIterator[str]:
        try:
            async with self._connected_agent() as agent:
                updates = agent.run(
                    message,
                    stream=True,
                    client_kwargs={"extra_headers": {"x-correlation-id": correlation_id}},
                )
                async for update in updates:
                    text = getattr(update, "text", None)
                    if text:
                        yield str(text)
        except GatewayFailure:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise classify_gateway_exception(exc) from None

    async def stream(self, message: str, correlation_id: str) -> AsyncIterator[str]:
        policy = RetryPolicy(
            max_attempts=self._settings.retry_max_attempts,
            initial_delay_seconds=self._settings.retry_initial_delay_seconds,
            max_delay_seconds=self._settings.retry_max_delay_seconds,
        )

        async def attempt() -> AsyncIterator[str]:
            async for chunk in self._attempt(message, correlation_id):
                yield chunk

        async for chunk in retry_stream(attempt, policy):
            yield chunk
