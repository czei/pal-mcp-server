# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Error types for multi-model debate orchestration.

All errors extend ToolExecutionError so they propagate correctly
through the MCP protocol with isError=True on CallToolResult.
"""

import json
from typing import Optional

from tools.shared.exceptions import ToolExecutionError


class DebateError(ToolExecutionError):
    """Base class for all debate-related errors."""

    def __init__(self, error_type: str, message: str, **kwargs):
        payload = json.dumps({"error": {"type": error_type, "message": message, **kwargs}})
        super().__init__(payload)
        self.error_type = error_type
        self.message = message


class ProviderUnavailableError(DebateError):
    """API key missing, network down, or circuit breaker open."""

    def __init__(self, provider: str, reason: str):
        super().__init__(
            error_type="ProviderUnavailableError",
            message=f"Provider '{provider}' unavailable: {reason}",
            provider=provider,
            reason=reason,
        )


class ProviderRateLimitError(DebateError):
    """Rate limit exceeded for a provider."""

    def __init__(self, provider: str, retry_after_ms: Optional[int] = None):
        super().__init__(
            error_type="ProviderRateLimitError",
            message=f"Rate limit exceeded for provider '{provider}'",
            provider=provider,
            retry_after_ms=retry_after_ms,
        )
        self.retry_after_ms = retry_after_ms


class ProviderTimeoutError(DebateError):
    """Provider call exceeded the configured timeout."""

    def __init__(self, provider: str, timeout_ms: int):
        super().__init__(
            error_type="ProviderTimeoutError",
            message=f"Provider '{provider}' timed out after {timeout_ms}ms",
            provider=provider,
            timeout_ms=timeout_ms,
        )


class ProviderContentFilterError(DebateError):
    """Model refused the prompt due to content filtering."""

    def __init__(self, provider: str, filter_reason: str = "content policy"):
        super().__init__(
            error_type="ProviderContentFilterError",
            message=f"Provider '{provider}' refused prompt: {filter_reason}",
            provider=provider,
            filter_reason=filter_reason,
        )


class SessionNotFoundError(DebateError):
    """Session ID not found or expired."""

    def __init__(self, session_id: str):
        super().__init__(
            error_type="SessionNotFoundError",
            message=f"Session '{session_id}' not found (may have been garbage collected)",
            session_id=session_id,
        )


class AliasNotFoundError(DebateError):
    """Model alias not found in session."""

    def __init__(self, session_id: str, alias: str):
        super().__init__(
            error_type="AliasNotFoundError",
            message=f"Alias '{alias}' not found in session '{session_id}'",
            session_id=session_id,
            alias=alias,
        )


class ConfigurationError(DebateError):
    """Invalid debate configuration."""

    def __init__(self, field: str, reason: str):
        super().__init__(
            error_type="ConfigurationError",
            message=f"Invalid configuration for '{field}': {reason}",
            field=field,
            reason=reason,
        )
