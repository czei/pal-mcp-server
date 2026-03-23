# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Shared debate routing logic for tool integration.

Extracted to avoid duplication between SimpleTool._run_debate() and
WorkflowMixin._run_workflow_debate(). Both call route_through_debate().

Fixes code review issues #1 (message flattening), #4 (DRY), #5 (provider
resolution), #6 (SessionManager leak).
"""

import logging
from typing import Any, Optional

from tools.models import ToolOutput

logger = logging.getLogger(__name__)


# =============================================================================
# Debate Presets
# =============================================================================

DEBATE_PRESETS = {
    # Config B: 3 models, pick the best one, no adversarial debate
    "ensemble": {"max_round": 1, "synthesis_mode": "select_best", "enable_context_requests": False},
    "pick_best": {"max_round": 1, "synthesis_mode": "select_best", "enable_context_requests": False},
    "select": {"max_round": 1, "synthesis_mode": "select_best", "enable_context_requests": False},

    # Config C: full adversarial debate, no context enrichment
    "debate": {"max_round": 2, "synthesis_mode": "synthesize", "enable_context_requests": False},
    "adversarial": {"max_round": 2, "synthesis_mode": "synthesize", "enable_context_requests": False},

    # Config D: full debate + models can request files/web between rounds
    "full": {"max_round": 2, "synthesis_mode": "synthesize", "enable_context_requests": True},
    "full_debate": {"max_round": 2, "synthesis_mode": "synthesize", "enable_context_requests": True},
    "research": {"max_round": 2, "synthesis_mode": "synthesize", "enable_context_requests": True},

    # Round 1 only with synthesis (not selection)
    "quick": {"max_round": 1, "synthesis_mode": "synthesize", "enable_context_requests": False},
    "parallel": {"max_round": 1, "synthesis_mode": "synthesize", "enable_context_requests": False},
}


def _resolve_preset(preset_name: str) -> dict:
    """Resolve a preset name to config overrides. Case-insensitive."""
    key = preset_name.lower().strip().replace("-", "_").replace(" ", "_")
    result = DEBATE_PRESETS.get(key, {})
    if result:
        logger.info(f"Debate preset '{preset_name}' → {result}")
    else:
        logger.warning(f"Unknown debate preset '{preset_name}' — using defaults")
    return result


def build_model_configs(request, default_models: list[str]) -> Optional[list[dict[str, Any]]]:
    """
    Build model configs from request params or defaults.
    Resolves real provider names (fixes issue #5).

    Returns None if no models available.
    """
    debate_models = getattr(request, "debate_models", None)

    if debate_models:
        raw_configs = [
            {
                "alias": dm.alias if hasattr(dm, "alias") else dm.get("alias", f"model_{i}"),
                "model": dm.model if hasattr(dm, "model") else dm.get("model", ""),
            }
            for i, dm in enumerate(debate_models)
        ]
    elif default_models:
        raw_configs = [{"alias": f"analyst_{i}", "model": model_id} for i, model_id in enumerate(default_models)]
    else:
        return None

    # Resolve real provider names and max_context (fixes issue #5)
    resolved = []
    for mc in raw_configs:
        provider_name, max_context = _resolve_provider_info(mc["model"])
        resolved.append(
            {
                "alias": mc["alias"],
                "model": mc["model"],
                "provider_name": provider_name,
                "max_context": max_context,
            }
        )

    return resolved


def _resolve_provider_info(model_id: str) -> tuple[str, int]:
    """Resolve actual provider name and max_context from model ID."""
    try:
        from providers import ModelProviderRegistry

        provider_obj = ModelProviderRegistry.get_provider_for_model(model_id)
        if provider_obj:
            provider_name = provider_obj.get_provider_type().value
            # Try to get max_context from capabilities
            try:
                caps = provider_obj.get_capabilities(model_id)
                max_context = caps.context_window if caps else 200000
            except Exception:
                max_context = 200000
            return provider_name, max_context
    except Exception as e:
        logger.debug(f"Could not resolve provider for {model_id}: {e}")

    return "unknown", 200000


def build_provider_call_fn():
    """
    Build the synchronous provider call function.

    IMPORTANT: This preserves conversation turns by serializing messages
    with explicit role markers. Provider APIs that only support prompt+system_prompt
    receive a formatted multi-turn transcript, not a flattened blob.
    (Fixes critical issue #1)
    """

    def _provider_call(messages: list[dict], model_id: str) -> dict:
        """Synchronous provider call — wrapped in asyncio.to_thread by orchestrator."""
        from providers import ModelProviderRegistry

        provider_obj = ModelProviderRegistry.get_provider_for_model(model_id)
        model_name = model_id  # Provider resolves aliases internally
        if not provider_obj:
            return {
                "content": f"[Error: provider not found for {model_id}]",
                "tokens": {"input": 0, "output": 0},
            }

        # Separate system prompt from conversation turns
        sys_prompt = ""
        conversation_parts = []
        for msg in messages:
            if msg["role"] == "system":
                sys_prompt = msg["content"]
            elif msg["role"] == "user":
                conversation_parts.append(f"USER:\n{msg['content']}")
            elif msg["role"] == "assistant":
                conversation_parts.append(f"ASSISTANT:\n{msg['content']}")

        # Preserve multi-turn structure with explicit role markers
        # This ensures the model sees its prior responses as conversation history
        full_prompt = "\n\n---\n\n".join(conversation_parts)

        response = provider_obj.generate_content(
            prompt=full_prompt,
            model_name=model_name,
            system_prompt=sys_prompt,
        )
        return {
            "content": response.content if response else "",
            "tokens": {
                "input": (response.usage.get("input_tokens", 0) if response and response.usage else 0),
                "output": (response.usage.get("output_tokens", 0) if response and response.usage else 0),
            },
        }

    return _provider_call


async def route_through_debate(
    tool_name: str,
    request,
    prompt: str,
    system_prompt: str,
    session_manager,
) -> Optional[str]:
    """
    Shared debate routing for both SimpleTool and WorkflowMixin.

    Args:
        tool_name: Name of the calling tool.
        request: The tool request object (has debate params via mixin).
        prompt: Prepared user prompt.
        system_prompt: Prepared system prompt.
        session_manager: The shared SessionManager (must not be None).

    Returns:
        JSON string of ToolOutput with debate_metadata, or None to fall
        through to single-model path (only when no models configured).

    Raises:
        RuntimeError: If session_manager is None (debate infra not initialized).
    """
    import config as _cfg
    from debate.orchestrator import DebateOrchestrator
    from sessions.types import DebateConfig

    # Fail fast if debate infrastructure not initialized (fixes issue #6)
    if session_manager is None:
        raise RuntimeError(
            "Debate infrastructure not initialized — " "DEBATE_FEATURE_ENABLED may be false or server startup failed"
        )

    # Resolve debate_preset to concrete parameters
    preset = getattr(request, "debate_preset", None)
    preset_overrides = _resolve_preset(preset) if preset else {}

    # Build debate config from request params, with preset overrides, with config.py defaults
    debate_config = DebateConfig(
        max_round=preset_overrides.get("max_round", getattr(request, "debate_max_rounds", _cfg.DEBATE_MAX_ROUNDS)) or _cfg.DEBATE_MAX_ROUNDS,
        synthesis_mode=preset_overrides.get("synthesis_mode", getattr(request, "synthesis_mode", "synthesize")) or "synthesize",
        enable_context_requests=preset_overrides.get("enable_context_requests", getattr(request, "enable_context_requests", True)),
        synthesis_model=getattr(request, "synthesis_model", None),
        escalation_mode=preset_overrides.get("escalation_mode", getattr(request, "escalation_mode", "adaptive")) or "adaptive",
        escalation_confidence_threshold=getattr(request, "escalation_confidence_threshold", None),
        escalation_complexity_threshold=getattr(request, "escalation_complexity_threshold", None),
        per_model_timeout_ms=_cfg.DEBATE_PER_MODEL_TIMEOUT_MS,
        summary_strategy=_cfg.DEBATE_SUMMARY_STRATEGY,
    )

    # Build model configs with resolved provider names
    model_configs = build_model_configs(request, _cfg.DEBATE_DEFAULT_MODELS)
    if not model_configs:
        logger.warning(f"{tool_name}: debate_mode=True but no models configured, " f"falling back to single-model")
        return None  # Caller handles fallthrough

    orchestrator = DebateOrchestrator(session_manager=session_manager)

    debate_result = await orchestrator.run_debate(
        task_type=tool_name,
        system_prompt=system_prompt,
        user_prompt=prompt,
        model_configs=model_configs,
        debate_config=debate_config,
        provider_call_fn=build_provider_call_fn(),
    )

    # Build human-readable debate summary header
    header_parts = []
    header_parts.append("## Multi-Model Debate Results\n")

    # Models and participation
    model_list = ", ".join(
        f"**{r.alias}** ({r.model})" for r in debate_result.responses
    )
    header_parts.append(f"**Models**: {model_list}")
    header_parts.append(f"**Round 1**: {debate_result.participation}")
    if debate_result.round2_participation:
        header_parts.append(f"**Round 2**: {debate_result.round2_participation}")

    # Synthesis info
    if debate_result.synthesis:
        synth_mode = debate_result.synthesis.mode
        synth_model = debate_result.synthesis.synthesizer_model
        header_parts.append(f"**Synthesis**: {synth_mode} (by {synth_model})")

    # Timing
    t = debate_result.timing
    total_ms = t.get("round1_ms", 0) + t.get("round2_ms", 0) + t.get("synthesis_ms", 0)
    header_parts.append(
        f"**Timing**: R1 {t.get('round1_ms', 0)}ms + R2 {t.get('round2_ms', 0)}ms "
        f"+ Synthesis {t.get('synthesis_ms', 0)}ms = **{total_ms}ms total**"
    )
    header_parts.append(f"**Session**: `{debate_result.session_id}` (trace: `{debate_result.trace_id[:8]}...`)")
    header_parts.append("")  # blank line before synthesis

    # Warnings
    if debate_result.warnings:
        warn_lines = [f"- {w.alias} ({w.model}): {w.message}" for w in debate_result.warnings]
        header_parts.append("**Warnings**:\n" + "\n".join(warn_lines))

    # Context requests — FULL detail for ablation analysis
    header_parts.append("")
    if debate_result.context_requests:
        header_parts.append(f"**Context Requests** ({len(debate_result.context_requests)} items):")
        header_parts.append("*(Models requested this additional information during Round 1)*")
        for cr in debate_result.context_requests:
            cr_type = cr.get("artifact_type", "file")
            cr_path = cr.get("path", "?")
            cr_who = cr.get("requested_by", "?")
            cr_rationale = cr.get("rationale", "")
            cr_priority = cr.get("priority", "medium")
            header_parts.append(
                f"  - **[{cr_type}]** `{cr_path}` — priority: {cr_priority}, "
                f"requested by: {cr_who}"
            )
            if cr_rationale:
                header_parts.append(f"    *Rationale: {cr_rationale}*")
        header_parts.append("")
        header_parts.append(
            "**Context Fulfillment**: Not fulfilled (MVP — Round 2 proceeded without "
            "gathered artifacts. Set `enable_context_requests=true` with Phase 5 "
            "context enrichment to fulfill requests between rounds.)"
        )
    else:
        header_parts.append(
            "**Context Requests**: None — no models requested additional information. "
            "*(This may mean the prompt provided sufficient context, or the models "
            "didn't use the request mechanism.)*"
        )

    header_parts.append("")

    # Synthesis content
    synthesis_text = ""
    if debate_result.synthesis:
        synthesis_text = debate_result.synthesis.synthesis

    header = "\n".join(header_parts)

    # Config summary
    config_line = (
        f"**Config**: max_rounds={debate_config.max_round}, "
        f"synthesis_mode={debate_config.synthesis_mode}, "
        f"enable_context_requests={debate_config.enable_context_requests}, "
        f"timeout={debate_config.per_model_timeout_ms}ms"
    )

    # Per-model Round 1 — FULL content, not truncated
    round1_section = "\n## Round 1: Independent Analysis\n"
    for r in debate_result.responses:
        status_icon = "✅" if r.status == "success" else "⚠️" if r.status == "partial" else "❌"
        round1_section += f"\n### {status_icon} {r.alias} ({r.model}) — {r.tokens.get('output', 0)} tokens, {r.latency_ms}ms\n\n"
        if r.round1_content:
            round1_section += r.round1_content + "\n"
        else:
            round1_section += f"*No response ({r.status})*\n"

    # Per-model Round 2 — FULL content
    round2_section = ""
    has_round2 = any(r.round2_content for r in debate_result.responses)
    if has_round2:
        round2_section = "\n## Round 2: Adversarial Critique\n"
        for r in debate_result.responses:
            if r.round2_content:
                round2_section += f"\n### {r.alias} ({r.model}) — Critique\n\n"
                round2_section += r.round2_content + "\n"

    # Synthesis — explain what it is
    synthesis_section = "\n## Synthesis\n"
    synthesis_section += (
        "*(A separate model reads all Round 1 + Round 2 responses and produces "
        "a unified summary. Ideally a model that didn't participate in the debate "
        "to avoid bias.)*\n\n"
    )
    if debate_result.synthesis:
        synth = debate_result.synthesis
        synthesis_section += f"**Synthesizer**: {synth.synthesizer_model} (mode: {synth.mode})\n\n"
        synthesis_section += synthesis_text or "No synthesis text."
        if synth.agreement_points:
            synthesis_section += "\n\n**Agreement Points**:\n" + "\n".join(f"- {p}" for p in synth.agreement_points)
        if synth.disagreement_points:
            synthesis_section += "\n\n**Disagreement Points**:\n" + "\n".join(f"- {p}" for p in synth.disagreement_points)
        if synth.recommendations:
            synthesis_section += "\n\n**Recommendations**:\n" + "\n".join(f"- {p}" for p in synth.recommendations)
    else:
        synthesis_section += "No synthesis produced — insufficient responses or synthesis model unavailable."

    # Assemble the FULL markdown — NOT wrapped in JSON
    full_content = (
        header
        + config_line + "\n\n"
        + "---"
        + round1_section
        + "\n---"
        + round2_section
        + "\n---"
        + synthesis_section
    )

    # Return as PLAIN MARKDOWN TEXT — not ToolOutput JSON.
    # This ensures Claude renders it directly instead of summarizing JSON.
    return full_content
