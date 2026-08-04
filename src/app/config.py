"""Strict, gateway-only runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit


GATEWAY_OPENAI_SUFFIX = "/default/models/openai/v1"
GATEWAY_MCP_SUFFIX = "/default/toolservers/appservice-ops/mcp"
STABLE_GATEWAY_MODEL = "appservice-chat"


class ConfigurationError(ValueError):
    """Raised when the sample cannot safely use its dedicated gateway."""


def _required(source: Mapping[str, str], name: str) -> str:
    value = source.get(name, "").strip()
    if not value:
        raise ConfigurationError("Gateway configuration is unavailable.")
    return value


def _positive_int(source: Mapping[str, str], name: str, default: int, maximum: int) -> int:
    raw = source.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError("Gateway configuration is invalid.") from exc
    if not 1 <= value <= maximum:
        raise ConfigurationError("Gateway configuration is invalid.")
    return value


def _normalize_gateway_url(
    value: str,
    expected_suffix: str,
    *,
    trailing_slash: bool,
) -> str:
    normalized = value.rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ConfigurationError("Gateway configuration is invalid.")
    if parsed.query or parsed.fragment or not parsed.path.endswith(expected_suffix):
        raise ConfigurationError("Gateway configuration is invalid.")
    return f"{normalized}/" if trailing_slash else normalized


@dataclass(frozen=True)
class Settings:
    """The only endpoint configuration accepted by the application."""

    gateway_openai_url: str
    gateway_mcp_url: str
    gateway_api_key: str
    mcp_backend_secret: str
    gateway_model: str = STABLE_GATEWAY_MODEL
    request_timeout_seconds: int = 45
    mcp_timeout_seconds: int = 30
    retry_max_attempts: int = 3
    retry_initial_delay_seconds: float = 0.5
    retry_max_delay_seconds: float = 8.0
    application_insights_connection_string: str | None = None
    environment_name: str = "local"
    site_name: str = "local"
    slot_name: str = "Production"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if environ is None else environ
        model = _required(source, "AZURE_AI_GATEWAY_MODEL")
        if model != STABLE_GATEWAY_MODEL:
            raise ConfigurationError("Gateway configuration is invalid.")

        retry_initial = source.get("GATEWAY_RETRY_INITIAL_DELAY_SECONDS", "0.5").strip()
        retry_max_delay = source.get("GATEWAY_RETRY_MAX_DELAY_SECONDS", "8").strip()
        try:
            retry_initial_value = float(retry_initial)
            retry_max_delay_value = float(retry_max_delay)
        except ValueError as exc:
            raise ConfigurationError("Gateway configuration is invalid.") from exc
        if retry_initial_value <= 0 or retry_max_delay_value < retry_initial_value:
            raise ConfigurationError("Gateway configuration is invalid.")

        return cls(
            gateway_openai_url=_normalize_gateway_url(
                _required(source, "AZURE_AI_GATEWAY_BASE_URL"),
                GATEWAY_OPENAI_SUFFIX,
                trailing_slash=True,
            ),
            gateway_mcp_url=_normalize_gateway_url(
                _required(source, "AZURE_AI_GATEWAY_MCP_URL"),
                GATEWAY_MCP_SUFFIX,
                trailing_slash=False,
            ),
            gateway_api_key=_required(source, "AZURE_AI_GATEWAY_API_KEY"),
            mcp_backend_secret=_required(source, "MCP_BACKEND_SECRET"),
            gateway_model=model,
            request_timeout_seconds=_positive_int(
                source, "GATEWAY_REQUEST_TIMEOUT_SECONDS", 45, 120
            ),
            mcp_timeout_seconds=_positive_int(source, "MCP_REQUEST_TIMEOUT_SECONDS", 30, 120),
            retry_max_attempts=_positive_int(source, "GATEWAY_RETRY_MAX_ATTEMPTS", 3, 5),
            retry_initial_delay_seconds=retry_initial_value,
            retry_max_delay_seconds=retry_max_delay_value,
            application_insights_connection_string=source.get(
                "APPLICATIONINSIGHTS_CONNECTION_STRING"
            )
            or None,
            environment_name=source.get("AZURE_ENV_NAME", "local"),
            site_name=source.get("WEBSITE_SITE_NAME", "local"),
            slot_name=source.get("WEBSITE_SLOT_NAME", "Production"),
        )
