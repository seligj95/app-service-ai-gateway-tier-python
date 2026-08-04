from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.errors import GatewayFailure, parse_retry_after
from app.retry import RetryPolicy, retry_stream


async def collect(stream: AsyncIterator[str]) -> list[str]:
    return [chunk async for chunk in stream]


def policy() -> RetryPolicy:
    return RetryPolicy(max_attempts=3, initial_delay_seconds=1, max_delay_seconds=10)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 404])
async def test_401_and_404_are_never_retried(status: int) -> None:
    attempts = 0

    async def attempt() -> AsyncIterator[str]:
        nonlocal attempts
        attempts += 1
        raise GatewayFailure(status, "gateway_failure")
        yield ""

    with pytest.raises(GatewayFailure):
        await collect(retry_stream(attempt, policy()))
    assert attempts == 1


@pytest.mark.asyncio
async def test_429_honors_retry_after_before_first_chunk() -> None:
    attempts = 0
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async def attempt() -> AsyncIterator[str]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise GatewayFailure(429, "gateway_rate_limited", retry_after_seconds=3)
        yield "ok"

    assert await collect(retry_stream(attempt, policy(), sleep=sleep, random_value=lambda: 0.9)) == [
        "ok"
    ]
    assert attempts == 2
    assert delays == [3]


@pytest.mark.asyncio
async def test_transient_5xx_retries_with_bounded_backoff() -> None:
    attempts = 0
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async def attempt() -> AsyncIterator[str]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise GatewayFailure(503, "gateway_unavailable")
        yield "recovered"

    assert await collect(retry_stream(attempt, policy(), sleep=sleep, random_value=lambda: 0)) == [
        "recovered"
    ]
    assert attempts == 3
    assert delays == [1, 2]


@pytest.mark.asyncio
async def test_retry_count_is_bounded() -> None:
    attempts = 0

    async def attempt() -> AsyncIterator[str]:
        nonlocal attempts
        attempts += 1
        raise GatewayFailure(503, "gateway_unavailable")
        yield ""

    with pytest.raises(GatewayFailure):
        await collect(retry_stream(attempt, policy(), sleep=lambda _: _completed()))
    assert attempts == 3


async def _completed() -> None:
    return None


@pytest.mark.asyncio
async def test_partial_stream_is_never_retried() -> None:
    attempts = 0

    async def attempt() -> AsyncIterator[str]:
        nonlocal attempts
        attempts += 1
        yield "partial"
        raise GatewayFailure(503, "gateway_unavailable")

    stream = retry_stream(attempt, policy())
    assert await anext(stream) == "partial"
    with pytest.raises(GatewayFailure):
        await anext(stream)
    assert attempts == 1


def test_retry_after_parses_delta_seconds() -> None:
    assert parse_retry_after("2.5") == 2.5
    assert parse_retry_after("invalid") is None
