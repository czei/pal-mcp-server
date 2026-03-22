# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Circuit breaker for per-provider health tracking.

Prevents retrying consistently failing providers. After failure_threshold
consecutive failures, the circuit opens and all calls fail immediately
for reset_timeout_ms. After timeout, a single probe call is allowed.
"""

import asyncio
import logging
import time
from enum import Enum

from debate.errors import ProviderUnavailableError

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing — reject all calls
    HALF_OPEN = "half_open"  # Probing — allow one call


class CircuitBreaker:
    """Per-provider circuit breaker with configurable thresholds."""

    def __init__(
        self,
        provider: str,
        failure_threshold: int = 3,
        reset_timeout_ms: int = 60000,
    ):
        """
        Args:
            provider: Provider name.
            failure_threshold: Consecutive failures before opening circuit.
            reset_timeout_ms: Time before attempting a probe after opening.
        """
        self.provider = provider
        self.failure_threshold = failure_threshold
        self.reset_timeout_ms = reset_timeout_ms

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    async def check(self) -> None:
        """
        Check if a call is allowed. Raises if circuit is open.

        Transitions OPEN → HALF_OPEN if reset timeout has elapsed.

        Raises:
            ProviderUnavailableError: If circuit is open.
        """
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return

            if self._state == CircuitState.OPEN:
                elapsed_ms = (time.monotonic() - self._last_failure_time) * 1000
                if elapsed_ms >= self.reset_timeout_ms:
                    self._state = CircuitState.HALF_OPEN
                    logger.info(
                        f"Circuit breaker for '{self.provider}' → HALF_OPEN "
                        f"(probing after {elapsed_ms:.0f}ms)"
                    )
                    return  # Allow probe call
                raise ProviderUnavailableError(
                    provider=self.provider,
                    reason=f"Circuit breaker open (resets in "
                    f"{self.reset_timeout_ms - elapsed_ms:.0f}ms)",
                )

            # HALF_OPEN: allow the probe call through
            return

    async def record_success(self) -> None:
        """Record a successful call. Closes circuit if half-open."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    f"Circuit breaker for '{self.provider}' → CLOSED (probe succeeded)"
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed call. Opens circuit if threshold reached."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — reopen
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker for '{self.provider}' → OPEN "
                    f"(probe failed)"
                )
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker for '{self.provider}' → OPEN "
                    f"({self._failure_count} consecutive failures)"
                )

    async def reset(self) -> None:
        """Force reset to closed state."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
