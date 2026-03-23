# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Token bucket rate limiter for per-provider API call throttling.

Each provider gets its own bucket with configurable requests-per-minute.
Callers await acquire() which blocks until a token is available or the
max wait time is exceeded.
"""

import asyncio
import logging
import time

from debate.errors import ProviderRateLimitError

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Per-provider token bucket rate limiter."""

    def __init__(self, provider: str, rpm: int, max_wait_seconds: float = 30.0):
        """
        Args:
            provider: Provider name (for error messages).
            rpm: Maximum requests per minute.
            max_wait_seconds: Maximum time to wait for a token before erroring.
        """
        self.provider = provider
        self.rpm = rpm
        self.max_wait_seconds = max_wait_seconds

        # Token bucket state
        self._capacity = max(1, rpm)
        self._tokens = float(self._capacity)
        self._refill_rate = rpm / 60.0  # tokens per second
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """
        Acquire a rate limit token. Blocks until available or max_wait exceeded.

        Raises:
            ProviderRateLimitError: If max wait time exceeded.
        """
        deadline = time.monotonic() + self.max_wait_seconds

        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

            # No tokens available — wait and retry
            now = time.monotonic()
            if now >= deadline:
                raise ProviderRateLimitError(
                    provider=self.provider,
                    retry_after_ms=int((1.0 / self._refill_rate) * 1000),
                )

            # Wait for one token to refill (or remaining deadline, whichever is shorter)
            wait_time = min(1.0 / self._refill_rate, deadline - now)
            await asyncio.sleep(wait_time)

    def _refill(self) -> None:
        """Refill tokens based on elapsed time. Must be called under lock."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._capacity, self._tokens + elapsed * self._refill_rate
        )
        self._last_refill = now

    async def release(self) -> None:
        """
        Refund a token after a failed provider call.
        Prevents rate limiter depletion under sustained failures.
        """
        async with self._lock:
            self._tokens = min(self._capacity, self._tokens + 1.0)

    @property
    def available_tokens(self) -> float:
        """Current available tokens (approximate, for monitoring)."""
        return self._tokens
