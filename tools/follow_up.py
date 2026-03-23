# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Follow-up tool for stateful multi-model debate sessions.

Sends a follow-up question to a specific model within an existing debate
session. The model receives its accumulated context (messages[] array)
along with the new question.
"""

import logging
import time
from typing import Any

from debate.errors import AliasNotFoundError, SessionNotFoundError
from debate.routing import build_provider_call_fn
from evaluation.logger import EvaluationLogger
from evaluation.metrics import build_evaluation_record
from sessions.memory import (
    build_context_for_model,
    create_checkpoint,
)
from tools.models import ToolOutput

_eval_logger = EvaluationLogger()

logger = logging.getLogger(__name__)


async def execute_follow_up(
    session_manager,
    session_id: str,
    alias: str,
    prompt: str,
    attachments: list[str] = None,
    checkpoint_name: str = None,
) -> dict[str, Any]:
    """
    Execute a follow-up to a specific model in a debate session.

    Args:
        session_manager: The shared SessionManager instance.
        session_id: Debate session ID.
        alias: Model alias to follow up with.
        prompt: Follow-up question or instruction.
        attachments: Optional additional file paths.
        checkpoint_name: Optional checkpoint to create after this exchange.

    Returns:
        Dict with response content, metadata, and session info.
    """
    import asyncio

    # Look up session
    session = await session_manager.get_session(session_id)
    if not session:
        raise SessionNotFoundError(session_id)

    # Look up worker runtime
    runtime = session_manager.get_worker_runtime(session_id, alias)
    if not runtime:
        raise AliasNotFoundError(session_id, alias)

    model_state = session.models.get(alias)
    if not model_state:
        raise AliasNotFoundError(session_id, alias)

    # Build context — append to existing messages[]
    runtime.messages = build_context_for_model(
        model_state=model_state,
        messages=runtime.messages,
        new_prompt=prompt,
        system_prompt=session.shared_context.task_specific_prompt,
    )

    # Call provider
    provider_call_fn = build_provider_call_fn()

    start = time.monotonic()
    try:
        response = await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(
                session_manager.executor,
                provider_call_fn,
                runtime.messages,
                model_state.model_id,
            ),
            timeout=session.debate_config.per_model_timeout_ms / 1000.0,
        )
    except asyncio.TimeoutError:
        return {
            "alias": alias,
            "model": model_state.model_id,
            "content": f"[Timeout after {session.debate_config.per_model_timeout_ms}ms]",
            "latency_ms": int((time.monotonic() - start) * 1000),
            "tokens": {"input": 0, "output": 0},
            "session_exchanges_total": model_state.total_exchange_count,
            "summary_included": False,
            "session_id": session_id,
            "error": "timeout",
        }

    elapsed_ms = int((time.monotonic() - start) * 1000)
    content = response.get("content", "")
    tokens = response.get("tokens", {"input": 0, "output": 0})

    # Append response to messages
    runtime.messages.append({"role": "assistant", "content": content})

    # Update model state
    model_state.total_exchange_count += 1
    model_state.total_input_tokens += tokens.get("input", 0)
    model_state.total_output_tokens += tokens.get("output", 0)

    # Check if compression was triggered
    current_tokens = sum(len(m.get("content", "")) // 4 for m in runtime.messages)
    summary_included = current_tokens > model_state.compression_threshold * 0.5

    # Log to evaluation (fix #1 — follow-ups were untracked)
    await _eval_logger.log_event(
        build_evaluation_record(
            event="follow_up",
            session_id=session_id,
            trace_id=session.trace_id,
            alias=alias,
            model=model_state.model_id,
            provider=model_state.provider_name,
            task_type=session.task_type,
            round_num=model_state.total_exchange_count,
            input_tokens=tokens.get("input", 0),
            output_tokens=tokens.get("output", 0),
            latency_ms=elapsed_ms,
            status="success",
            is_follow_up=True,
            exchange_number=model_state.total_exchange_count,
        )
    )

    # Create checkpoint if requested
    if checkpoint_name:
        create_checkpoint(model_state, checkpoint_name)

    # Update session
    session.touch()
    await session_manager.update_session(session)

    return {
        "alias": alias,
        "model": model_state.model_id,
        "content": content,
        "latency_ms": elapsed_ms,
        "tokens": tokens,
        "session_exchanges_total": model_state.total_exchange_count,
        "summary_included": summary_included,
        "session_id": session_id,
    }


class FollowUpTool:
    """
    MCP tool for stateful follow-up conversations.

    Registered in server.py as "follow_up".
    """

    def __init__(self):
        self._session_manager = None

    def get_name(self) -> str:
        return "follow_up"

    def get_description(self) -> str:
        return (
            "Send a follow-up question to a specific model within an existing "
            "multi-model debate session. The model receives its accumulated "
            "context and responds in the context of its prior analysis."
        )

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Debate session ID from a prior debate_mode response.",
                },
                "alias": {
                    "type": "string",
                    "description": "Model alias to follow up with (e.g., 'analyst').",
                },
                "prompt": {
                    "type": "string",
                    "description": "Follow-up question or instruction.",
                },
                "attachments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional file paths to include.",
                },
                "checkpoint_name": {
                    "type": "string",
                    "description": "Optional: create a named checkpoint after this exchange.",
                },
            },
            "required": ["session_id", "alias", "prompt"],
            "additionalProperties": False,
        }

    def requires_model(self) -> bool:
        return False

    async def execute(self, arguments: dict) -> list:
        """Execute the follow-up tool call."""
        from mcp.types import TextContent

        if not self._session_manager:
            error = ToolOutput(
                status="error",
                content="Debate infrastructure not initialized.",
            )
            return [TextContent(type="text", text=error.model_dump_json())]

        try:
            result = await execute_follow_up(
                session_manager=self._session_manager,
                session_id=arguments["session_id"],
                alias=arguments["alias"],
                prompt=arguments["prompt"],
                attachments=arguments.get("attachments"),
                checkpoint_name=arguments.get("checkpoint_name"),
            )

            output = ToolOutput(
                status="success",
                content=result["content"],
                content_type="markdown",
                metadata=result,
            )
            return [TextContent(type="text", text=output.model_dump_json())]

        except (SessionNotFoundError, AliasNotFoundError) as e:
            return [TextContent(type="text", text=e.payload)]
        except Exception as e:
            error = ToolOutput(status="error", content=str(e))
            return [TextContent(type="text", text=error.model_dump_json())]
