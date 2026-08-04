"""Azure Monitor setup with a deliberately small telemetry attribute allow-list."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any


SAFE_TELEMETRY_ATTRIBUTES = frozenset(
    {
        "correlation_id",
        "http.route",
        "http.response.status_code",
        "gateway.status_code",
        "gateway.error_code",
        "service.name",
    }
)


def safe_telemetry_attributes(attributes: Mapping[str, Any]) -> dict[str, str | int | float | bool]:
    """Keep only operational metadata; never accept prompts, responses, or secrets."""

    safe: dict[str, str | int | float | bool] = {}
    for key, value in attributes.items():
        if key in SAFE_TELEMETRY_ATTRIBUTES and isinstance(value, (str, int, float, bool)):
            safe[key] = value
    return safe


def set_safe_attributes(span: Any, attributes: Mapping[str, Any]) -> None:
    for key, value in safe_telemetry_attributes(attributes).items():
        span.set_attribute(key, value)


def configure_telemetry(connection_string: str | None) -> bool:
    """Configure Azure Monitor only when App Service supplies its connection string."""

    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "false"
    if not connection_string:
        return False
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=connection_string)
        return True
    except Exception:
        logging.getLogger("app.telemetry").warning("telemetry_configuration_unavailable")
        return False
