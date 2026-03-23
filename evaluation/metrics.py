# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Metrics collection for multi-model debate evaluation.

Builds structured EvaluationRecord dicts from model response data.
"""

from datetime import datetime, timezone
from typing import Any, Optional


def build_evaluation_record(
    event: str,
    session_id: str,
    trace_id: str,
    alias: str,
    model: str,
    provider: str,
    task_type: str,
    round_num: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    status: str = "success",
    is_follow_up: bool = False,
    exchange_number: int = 1,
    context_requests_count: int = 0,
    error_message: Optional[str] = None,
) -> dict[str, Any]:
    """
    Build a structured evaluation record.

    Args:
        event: Event type (model_response, debate_round, synthesis, follow_up).
        session_id: Debate session ID.
        trace_id: End-to-end trace ID.
        alias: Model alias.
        model: Model identifier.
        provider: Provider name.
        task_type: Tool that initiated.
        round_num: Debate round number.
        input_tokens: Tokens sent to model.
        output_tokens: Tokens received.
        latency_ms: Response time.
        status: success/timeout/error/rate_limited.
        is_follow_up: Whether this was a follow-up exchange.
        exchange_number: Exchange count within session.
        context_requests_count: Number of context requests returned.
        error_message: Error details if applicable.

    Returns:
        Dict ready for EvaluationLogger.log_event().
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "session_id": session_id,
        "trace_id": trace_id,
        "alias": alias,
        "model": model,
        "provider": provider,
        "task_type": task_type,
        "round": round_num,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
        "status": status,
        "is_follow_up": is_follow_up,
        "exchange_number": exchange_number,
        "context_requests_count": context_requests_count,
        "error_message": error_message,
    }
