"""Structured operational logging that intentionally excludes sensitive content."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any


SAFE_LOG_ATTRIBUTES = frozenset(
    {
        "correlation_id",
        "event",
        "route",
        "status_code",
        "error_code",
        "attempt",
    }
)


def safe_log(logger: logging.Logger, event: str, attributes: Mapping[str, Any] | None = None) -> None:
    values = {"event": event}
    for key, value in (attributes or {}).items():
        if key in SAFE_LOG_ATTRIBUTES and isinstance(value, (str, int, float, bool)):
            values[key] = value
    logger.info("operational_event=%s", values)
