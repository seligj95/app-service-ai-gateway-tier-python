"""Sanitized gateway failures and retry metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Mapping


class GatewayFailure(Exception):
    """A failure whose public representation never includes upstream content."""

    def __init__(
        self,
        status_code: int | None,
        code: str,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.retry_after_seconds = retry_after_seconds

    @property
    def retryable(self) -> bool:
        return self.status_code == 429 or (
            self.status_code is not None and 500 <= self.status_code <= 599
        )


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Parse delta-seconds or an HTTP date without exposing upstream values."""

    if not value:
        return None
    try:
        parsed_seconds = float(value)
    except ValueError:
        try:
            target = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        current = now or datetime.now(UTC)
        return max(0.0, (target - current).total_seconds())
    return max(0.0, parsed_seconds)


def _headers_from_exception(error: BaseException) -> Mapping[str, str]:
    response = getattr(error, "response", None)
    headers: Any = getattr(response, "headers", None)
    if isinstance(headers, Mapping):
        return headers
    headers = getattr(error, "headers", None)
    return headers if isinstance(headers, Mapping) else {}


def _http_error_from_chain(error: BaseException) -> tuple[BaseException, int | None]:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        status = getattr(current, "status_code", None)
        response = getattr(current, "response", None)
        if status is None:
            status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return current, status
        current = current.__cause__ or current.__context__
    return error, None


def classify_gateway_exception(error: BaseException) -> GatewayFailure:
    """Classify common HTTP client failures without retaining response bodies."""

    http_error, status = _http_error_from_chain(error)
    if status is None:
        return GatewayFailure(503, "gateway_unavailable")

    headers = _headers_from_exception(http_error)
    retry_after = parse_retry_after(headers.get("retry-after") or headers.get("Retry-After"))
    if status == 401:
        return GatewayFailure(status, "gateway_unauthorized")
    if status == 404:
        return GatewayFailure(status, "gateway_not_found")
    if status == 429:
        return GatewayFailure(status, "gateway_rate_limited", retry_after_seconds=retry_after)
    if 500 <= status <= 599:
        return GatewayFailure(status, "gateway_unavailable")
    return GatewayFailure(status, "gateway_request_failed")


PUBLIC_ERROR_MESSAGES = {
    "gateway_unauthorized": "The gateway rejected the request.",
    "gateway_not_found": "The requested gateway model was not found.",
    "gateway_rate_limited": "The gateway is temporarily rate limited.",
    "gateway_unavailable": "The gateway is temporarily unavailable.",
    "gateway_request_failed": "The gateway could not process the request.",
}
