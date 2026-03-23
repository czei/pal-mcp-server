# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Stratified memory management for multi-model debate sessions.

Handles context construction, compression (template and LLM-assisted),
provider-aware thresholds, and checkpoint creation.

See research.md R-011 for context architecture.
"""

import logging
import re
from typing import Any

from sessions.types import Checkpoint, ModelState, PinnedFact

logger = logging.getLogger(__name__)


# =============================================================================
# Context Construction (T030)
# =============================================================================


def build_context_for_model(
    model_state: ModelState,
    messages: list[dict[str, Any]],
    new_prompt: str,
    system_prompt: str = "",
    shared_context_text: str = "",
) -> list[dict[str, Any]]:
    """
    Construct the messages array for a follow-up call.

    If the messages array is already within budget, just append the new prompt.
    If approaching the compression threshold, compress first, then append.

    The structure:
    [system prompt] + [pinned facts summary] + [working summary] +
    [recent verbatim exchanges] + [shared context] + [new prompt]

    Args:
        model_state: Per-model state with pinned_facts, working_summary, etc.
        messages: The current messages array (may need compression).
        new_prompt: The new user prompt to append.
        system_prompt: Tool-specific system prompt (for reconstruction).
        shared_context_text: Additional shared context (code files, etc.).

    Returns:
        Updated messages array with new prompt appended.
    """
    # Check if compression needed before adding the new prompt
    estimated_new_tokens = len(new_prompt) // 4  # rough estimate
    current_tokens = _estimate_messages_tokens(messages)

    if should_compress(current_tokens + estimated_new_tokens, model_state):
        messages = _compress_messages(messages, model_state, system_prompt, shared_context_text)

    # Append the new prompt
    messages.append({"role": "user", "content": new_prompt})
    return messages


def _estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimate for a messages array (~4 chars per token)."""
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return total_chars // 4


def _compress_messages(
    messages: list[dict[str, Any]],
    model_state: ModelState,
    system_prompt: str,
    shared_context_text: str,
) -> list[dict[str, Any]]:
    """
    Compress messages by replacing oldest exchanges with structured summary.
    Keeps system prompt and recent exchanges verbatim.
    """
    if len(messages) <= 3:
        return messages  # Nothing to compress

    # Build compressed message from pinned facts + working summary
    compressed_parts = []

    if model_state.pinned_facts:
        facts = "\n".join(f"- [{f.category.value}] {f.content} ({f.status.value})" for f in model_state.pinned_facts)
        compressed_parts.append(f"## Established Facts\n{facts}")

    if model_state.working_summary:
        compressed_parts.append(f"## Session Summary\n{model_state.working_summary}")

    if shared_context_text:
        compressed_parts.append(f"## Shared Context\n{shared_context_text}")

    # Keep system prompt + compressed context + last 3 exchanges
    new_messages = []

    # System prompt (first message)
    if messages and messages[0]["role"] == "system":
        new_messages.append(messages[0])
    elif system_prompt:
        new_messages.append({"role": "system", "content": system_prompt})

    # Compressed context as a user message
    if compressed_parts:
        new_messages.append(
            {
                "role": "user",
                "content": (
                    "[COMPRESSED SESSION CONTEXT — older exchanges summarized below]\n\n"
                    + "\n\n".join(compressed_parts)
                    + "\n\n[END COMPRESSED CONTEXT]"
                ),
            }
        )
        new_messages.append(
            {
                "role": "assistant",
                "content": "Understood. I have the compressed session context with established facts and summary. Ready to continue.",
            }
        )

    # Keep last N exchanges (user+assistant pairs)
    recent_count = 6  # 3 pairs of user+assistant
    non_system = [m for m in messages if m["role"] != "system"]
    if len(non_system) > recent_count:
        new_messages.extend(non_system[-recent_count:])
    else:
        new_messages.extend(non_system)

    logger.info(f"Compressed messages for {model_state.alias}: " f"{len(messages)} → {len(new_messages)} messages")
    return new_messages


# =============================================================================
# Compression Trigger (T033)
# =============================================================================


def should_compress(total_tokens: int, model_state: ModelState) -> bool:
    """
    Check if compression should be triggered.

    Returns True when total tokens exceed the model's compression threshold
    (default 0.7 * max_context).
    """
    return total_tokens > model_state.compression_threshold


# =============================================================================
# Template-Based Summary Extraction (T031)
# =============================================================================


def compress_exchange_template(exchange_content: str) -> str:
    """
    Deterministic summary extraction — no LLM call.
    Extracts code blocks, file paths, error messages, decisions, questions.

    Args:
        exchange_content: Raw text of the exchange to compress.

    Returns:
        Compressed summary string.
    """
    parts = []

    # Extract code blocks
    code_blocks = re.findall(r"```[\w]*\n(.*?)```", exchange_content, re.DOTALL)
    if code_blocks:
        parts.append(f"Code references: {len(code_blocks)} blocks")

    # Extract file paths
    file_paths = re.findall(
        r"(?:^|\s)(/[\w./\-]+\.[\w]+|[\w./\-]+\.(?:py|js|ts|java|go|rs|cpp|c|h|md|yml|yaml|json|toml))",
        exchange_content,
    )
    if file_paths:
        unique_paths = list(dict.fromkeys(file_paths))[:10]
        parts.append(f"Files referenced: {', '.join(unique_paths)}")

    # Extract error messages
    errors = re.findall(
        r"(?:Error|Exception|error|exception|ERROR|FAIL|fail)[:]\s*(.+?)(?:\n|$)",
        exchange_content,
    )
    if errors:
        parts.append(f"Errors noted: {'; '.join(e.strip() for e in errors[:5])}")

    # Extract decisions (lines starting with "Decision:", "Agreed:", etc.)
    decisions = re.findall(
        r"(?:Decision|Agreed|Conclusion|Recommendation|DECISION)[:]\s*(.+?)(?:\n|$)",
        exchange_content,
        re.IGNORECASE,
    )
    if decisions:
        parts.append(f"Decisions: {'; '.join(d.strip() for d in decisions[:5])}")

    # Extract questions
    questions = re.findall(r"([^.!]*\?)", exchange_content)
    if questions:
        parts.append(f"Open questions: {'; '.join(q.strip() for q in questions[:3])}")

    if not parts:
        # Fallback: first 200 chars
        parts.append(exchange_content[:200].strip() + "...")

    return " | ".join(parts)


# =============================================================================
# LLM-Assisted Summarization (T032)
# =============================================================================


async def compress_exchange_llm(
    exchange_content: str,
    current_summary: str,
    pinned_facts: list[PinnedFact],
    provider_call_fn=None,
    model_id: str = None,
) -> str:
    """
    LLM-assisted structured summarization.

    Calls the strongest available model with current structured state + exchange,
    outputs field-level updates. Constrained to structured fields to prevent drift.

    Args:
        exchange_content: Raw text of the exchange to compress.
        current_summary: Existing working summary.
        pinned_facts: Current pinned facts (for reference, not modification).
        provider_call_fn: Async callable(messages, model_id) → response.
        model_id: Model to use for summarization.

    Returns:
        Updated working summary string.
    """
    if not provider_call_fn:
        # Fallback to template
        return compress_exchange_template(exchange_content)

    facts_text = "\n".join(f"- [{f.category.value}] {f.content}" for f in pinned_facts) if pinned_facts else "None"

    prompt = (
        "You are compressing a conversation exchange into a structured summary update.\n\n"
        f"## Current Summary\n{current_summary or 'Empty — this is the first compression.'}\n\n"
        f"## Pinned Facts (DO NOT contradict these)\n{facts_text}\n\n"
        f"## Exchange to Compress\n{exchange_content}\n\n"
        "## Instructions\n"
        "Update the summary with new information from this exchange. Output ONLY:\n"
        "- Key findings or conclusions from this exchange\n"
        "- Any hypothesis status changes (confirmed/rejected/revised)\n"
        "- New decisions or open questions\n"
        "- DO NOT contradict pinned facts\n"
        "- Keep the summary concise (under 500 words)\n"
        "- Preserve all critical technical details (function names, error codes, etc.)\n"
    )

    try:

        messages = [
            {"role": "system", "content": "You are a precise technical summarizer."},
            {"role": "user", "content": prompt},
        ]
        response = await provider_call_fn(messages, model_id)
        return response.get("content", compress_exchange_template(exchange_content))
    except Exception as e:
        logger.warning(f"LLM summarization failed, falling back to template: {e}")
        return compress_exchange_template(exchange_content)


# =============================================================================
# Checkpoint Creation (T034)
# =============================================================================


def create_checkpoint(
    model_state: ModelState,
    name: str,
) -> Checkpoint:
    """
    Create a named snapshot of current model state.

    Args:
        model_state: Current ModelState to snapshot.
        name: Human-readable checkpoint name.

    Returns:
        The created Checkpoint (also appended to model_state.checkpoints).
    """
    checkpoint = Checkpoint(
        name=name,
        pinned_facts_snapshot=list(model_state.pinned_facts),
        working_summary_snapshot=model_state.working_summary,
        exchange_count=model_state.total_exchange_count,
    )
    model_state.checkpoints.append(checkpoint)
    logger.info(
        f"Checkpoint '{name}' created for {model_state.alias} " f"(exchange #{model_state.total_exchange_count})"
    )
    return checkpoint
