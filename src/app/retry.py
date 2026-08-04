"""Bounded retry behavior for unstarted gateway streams."""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from .errors import GatewayFailure


AttemptFactory = Callable[[], AsyncIterator[str]]
SleepFunction = Callable[[float], Awaitable[None]]
RandomFunction = Callable[[], float]


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    initial_delay_seconds: float
    max_delay_seconds: float

    def delay_for(self, failure: GatewayFailure, attempt_index: int, random_value: float) -> float:
        if failure.status_code == 429 and failure.retry_after_seconds is not None:
            return min(self.max_delay_seconds, failure.retry_after_seconds)
        base = min(self.max_delay_seconds, self.initial_delay_seconds * (2**attempt_index))
        return min(self.max_delay_seconds, base + (base * 0.2 * max(0.0, random_value)))


async def retry_stream(
    attempt_factory: AttemptFactory,
    policy: RetryPolicy,
    *,
    sleep: SleepFunction = asyncio.sleep,
    random_value: RandomFunction = random.random,
) -> AsyncIterator[str]:
    """Retry only failures before a first chunk; never replay a partial response."""

    for attempt_index in range(policy.max_attempts):
        emitted_chunk = False
        try:
            async for chunk in attempt_factory():
                emitted_chunk = True
                yield chunk
            return
        except GatewayFailure as failure:
            is_last_attempt = attempt_index + 1 >= policy.max_attempts
            if emitted_chunk or not failure.retryable or is_last_attempt:
                raise
            await sleep(policy.delay_for(failure, attempt_index, random_value()))
