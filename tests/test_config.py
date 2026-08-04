from __future__ import annotations

import pytest

from app.config import ConfigurationError, Settings, STABLE_GATEWAY_MODEL


def valid_environment() -> dict[str, str]:
    return {
        "AZURE_AI_GATEWAY_BASE_URL": "https://gateway.example/default/models/openai/v1/",
        "AZURE_AI_GATEWAY_MCP_URL": "https://gateway.example/default/toolservers/appservice-ops/mcp/",
        "AZURE_AI_GATEWAY_API_KEY": "opaque-runtime-value",
        "MCP_BACKEND_SECRET": "opaque-backend-value",
        "AZURE_AI_GATEWAY_MODEL": STABLE_GATEWAY_MODEL,
    }


def test_settings_only_accept_dedicated_gateway_routes() -> None:
    settings = Settings.from_env(valid_environment())
    assert settings.gateway_openai_url.endswith("/default/models/openai/v1/")
    assert settings.gateway_mcp_url.endswith("/default/toolservers/appservice-ops/mcp")
    assert not settings.gateway_mcp_url.endswith("/")
    assert settings.gateway_model == "appservice-chat"


def test_settings_reject_non_gateway_model_or_route() -> None:
    environment = valid_environment()
    environment["AZURE_AI_GATEWAY_MODEL"] = "provider-model"
    with pytest.raises(ConfigurationError):
        Settings.from_env(environment)

    environment = valid_environment()
    environment["AZURE_AI_GATEWAY_BASE_URL"] = "https://provider.example/openai/v1/"
    with pytest.raises(ConfigurationError):
        Settings.from_env(environment)


def test_configuration_never_uses_provider_endpoint_as_a_fallback() -> None:
    environment = {
        "AZURE_OPENAI_ENDPOINT": "https://provider.example/",
        "AZURE_OPENAI_API_KEY": "opaque-provider-value",
    }
    with pytest.raises(ConfigurationError):
        Settings.from_env(environment)
