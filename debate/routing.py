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
    "consensus": {"max_round": 2, "synthesis_mode": "synthesize", "enable_context_requests": False},
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


def _determine_config_letter(dc) -> str:
    """Map DebateConfig to ablation config letter A-E."""
    if dc.max_round == 1 and dc.synthesis_mode == "select_best":
        return "B"
    elif dc.max_round == 2 and not dc.enable_context_requests:
        return "C"
    elif dc.max_round == 2 and dc.enable_context_requests:
        return "D"
    elif dc.max_round == 1:
        return "B" if dc.synthesis_mode == "select_best" else "C"
    elif dc.escalation_mode == "adaptive":
        return "E"
    return "C"  # default


def _extract_summary_line(content: str) -> str:
    """Extract a one-line summary from model response content."""
    if not content:
        return "*No content*"

    # Skip markdown headers and blank lines to find first substantive text
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("```"):
            continue
        if line.startswith("---"):
            continue
        if line.startswith("{"):  # JSON
            continue
        # Found a substantive line — truncate to ~150 chars
        if len(line) > 150:
            return line[:147] + "..."
        return line

    return content[:150].strip() + "..." if len(content) > 150 else content.strip()


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
        max_round=preset_overrides.get("max_round", getattr(request, "debate_max_rounds", _cfg.DEBATE_MAX_ROUNDS))
        or _cfg.DEBATE_MAX_ROUNDS,
        synthesis_mode=preset_overrides.get("synthesis_mode", getattr(request, "synthesis_mode", "synthesize"))
        or "synthesize",
        enable_context_requests=preset_overrides.get(
            "enable_context_requests", getattr(request, "enable_context_requests", True)
        ),
        synthesis_model=getattr(request, "synthesis_model", None),
        escalation_mode=preset_overrides.get("escalation_mode", getattr(request, "escalation_mode", "adaptive"))
        or "adaptive",
        escalation_confidence_threshold=getattr(request, "escalation_confidence_threshold", None),
        escalation_complexity_threshold=getattr(request, "escalation_complexity_threshold", None),
        per_model_timeout_ms=_cfg.DEBATE_PER_MODEL_TIMEOUT_MS,
        summary_strategy=_cfg.DEBATE_SUMMARY_STRATEGY,
    )

    # Build model configs — use per-tool overrides if configured, else global default
    tool_key = tool_name.lower()
    default_models = _cfg.DEBATE_TOOL_MODELS.get(tool_key, _cfg.DEBATE_DEFAULT_MODELS)
    model_configs = build_model_configs(request, default_models)
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

    # Determine config letter for display
    config_letter = _determine_config_letter(debate_config)

    config_descriptions = {
        "A": "Single model, no debate (baseline)",
        "B": "3 models parallel, best one selected (ensemble)",
        "C": "2-round adversarial debate (independent → critique)",
        "D": "2-round debate + context enrichment (models request files/web between rounds)",
        "E": "Adaptive intensity (full debate for design, auto-escalation for implementation)",
    }

    # Timing
    t = debate_result.timing
    total_ms = t.get("round1_ms", 0) + t.get("round2_ms", 0) + t.get("synthesis_ms", 0)
    total_secs = total_ms / 1000

    # Model names for compact display
    model_names = ", ".join(r.alias for r in debate_result.responses)

    # Count rounds that actually ran
    has_round2 = any(r.round2_content for r in debate_result.responses)
    rounds_ran = 2 if has_round2 else 1

    # =========================================================================
    # SECTION 1: Compact process banner (always visible, ~5 lines)
    # =========================================================================
    banner = []
    banner.append(f"## Debate Result — Config {config_letter}: {config_descriptions.get(config_letter, 'Custom')}")
    banner.append("")
    banner.append(
        f"> **{rounds_ran} round{'s' if rounds_ran > 1 else ''}** | "
        f"**Models**: {model_names} | "
        f"**{total_secs:.1f}s** total "
        f"(R1 {t.get('round1_ms', 0) / 1000:.1f}s"
        + (f" + R2 {t.get('round2_ms', 0) / 1000:.1f}s" if has_round2 else "")
        + (f" + Synthesis {t.get('synthesis_ms', 0) / 1000:.1f}s" if debate_result.synthesis else "")
        + ")"
    )

    # Participation — only note if something went wrong
    r1_part = debate_result.participation
    r2_part = debate_result.round2_participation
    num_models = len(debate_result.responses)
    if r1_part != f"{num_models}/{num_models}":
        banner.append(f"> **R1 Participation**: {r1_part}")
    if has_round2 and r2_part and r2_part != f"{num_models}/{num_models}":
        banner.append(f"> **R2 Participation**: {r2_part}")

    # Warnings — surface them immediately
    if debate_result.warnings:
        for w in debate_result.warnings:
            banner.append(f"> ⚠️ {w.alias} ({w.model}): {w.message}")

    banner.append("")

    # =========================================================================
    # SECTION 2: Synthesis (the answer — what the user cares about most)
    # =========================================================================
    synthesis_section = ""
    if debate_result.synthesis:
        synth = debate_result.synthesis
        synthesis_section += "## Synthesized Answer\n"
        synthesis_section += f"*Synthesizer: {synth.synthesizer_model} (mode: {synth.mode})*\n\n"
        synthesis_section += (synth.synthesis or "No synthesis text.") + "\n"
        if synth.agreement_points:
            synthesis_section += (
                "\n**Where models agreed:**\n" + "\n".join(f"- {p}" for p in synth.agreement_points) + "\n"
            )
        if synth.disagreement_points:
            synthesis_section += (
                "\n**Where models disagreed:**\n" + "\n".join(f"- {p}" for p in synth.disagreement_points) + "\n"
            )
        if synth.recommendations:
            synthesis_section += "\n**Recommendations:**\n" + "\n".join(f"- {p}" for p in synth.recommendations) + "\n"
    else:
        synthesis_section += (
            "## Synthesis\n\nNo synthesis produced — insufficient responses or synthesis model unavailable.\n"
        )

    # =========================================================================
    # SECTION 3: Round summaries (one-liners per model, quick scan)
    # =========================================================================
    summary_parts = []
    summary_parts.append("\n---\n")
    summary_parts.append("## Round Summaries\n")

    summary_parts.append("**Round 1 — Independent Analysis:**")
    for r in debate_result.responses:
        if r.round1_content:
            first_line = _extract_summary_line(r.round1_content)
            status_icon = "✅" if r.status in ("success", "partial") else "❌"
            summary_parts.append(f"- {status_icon} **{r.alias}** ({r.model}): {first_line}")
        else:
            summary_parts.append(f"- ❌ **{r.alias}** ({r.model}): *No response*")
    summary_parts.append("")

    if has_round2:
        summary_parts.append("**Round 2 — Adversarial Critique:**")
        for r in debate_result.responses:
            if r.round2_content:
                first_line = _extract_summary_line(r.round2_content)
                summary_parts.append(f"- **{r.alias}**: {first_line}")
        summary_parts.append("")
    elif debate_config.max_round >= 2:
        summary_parts.append("**Round 2**: Skipped (insufficient Round 1 responses)\n")

    # Context requests — compact
    if debate_result.context_requests:
        summary_parts.append(f"**Context Requests** ({len(debate_result.context_requests)}):")
        for cr in debate_result.context_requests:
            cr_type = cr.get("artifact_type", "file")
            cr_path = cr.get("path", "?")
            cr_who = cr.get("requested_by", "?")
            summary_parts.append(f"  - [{cr_type}] `{cr_path}` (by {cr_who})")
        summary_parts.append("")

    # =========================================================================
    # SECTION 4: Full round details (for deep-dive / ctrl-o expansion)
    # =========================================================================
    details_parts = []
    details_parts.append("\n---\n")
    details_parts.append("## Full Round Details\n")

    # Round 1 full content
    details_parts.append("### Round 1: Independent Analysis\n")
    for r in debate_result.responses:
        status_icon = "✅" if r.status == "success" else "⚠️" if r.status == "partial" else "❌"
        details_parts.append(
            f"#### {status_icon} {r.alias} ({r.model}) — " f"{r.tokens.get('output', 0)} tokens, {r.latency_ms}ms\n"
        )
        if r.round1_content:
            details_parts.append(r.round1_content + "\n")
        else:
            details_parts.append(f"*No response ({r.status})*\n")

    # Round 2 full content
    if has_round2:
        details_parts.append("\n### Round 2: Adversarial Critique\n")
        for r in debate_result.responses:
            if r.round2_content:
                details_parts.append(f"#### {r.alias} ({r.model}) — Critique\n")
                details_parts.append(r.round2_content + "\n")

    # Config details (technical metadata at the very end)
    details_parts.append("\n---\n")
    details_parts.append(
        f"<details><summary>Config &amp; Session Details</summary>\n\n"
        f"- **Config {config_letter}**: max_rounds={debate_config.max_round}, "
        f"synthesis_mode={debate_config.synthesis_mode}, "
        f"enable_context_requests={debate_config.enable_context_requests}, "
        f"timeout={debate_config.per_model_timeout_ms}ms\n"
        f"- **Models**: {', '.join(f'{r.alias} ({r.model})' for r in debate_result.responses)}\n"
        f"- **Session**: `{debate_result.session_id}` (trace: `{debate_result.trace_id[:8]}...`)\n"
        f"- **Timing**: R1 {t.get('round1_ms', 0)}ms + R2 {t.get('round2_ms', 0)}ms "
        f"+ Synthesis {t.get('synthesis_ms', 0)}ms = {total_ms}ms\n"
        f"\n</details>\n"
    )

    # =========================================================================
    # Assemble: Banner → Synthesis → Round Summaries → Full Details
    # =========================================================================
    full_content = "\n".join(banner) + synthesis_section + "\n".join(summary_parts) + "\n".join(details_parts)

    # Return as PLAIN MARKDOWN TEXT — not ToolOutput JSON.
    # This ensures Claude renders it directly instead of summarizing JSON.
    return full_content
