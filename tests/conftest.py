from __future__ import annotations

import pytest

from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        gateway_openai_url="https://gateway.example/default/models/openai/v1/",
        gateway_mcp_url="https://gateway.example/default/toolservers/appservice-ops/mcp/",
        gateway_api_key="opaque-runtime-value",
        mcp_backend_secret="opaque-backend-value",
        application_insights_connection_string=None,
    )
