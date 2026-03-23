# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Cross-model response synthesis for multi-model debate.

Two modes:
- synthesize: Merge perspectives into unified analysis with agreement/disagreement.
- select_best: Score each response 1-10 and return the highest-scoring one.

See research.md R-012, data-model.md SynthesisResult.
"""

import json
import logging
import re
from typing import Any, Optional

import config as cfg
from debate.prompts import build_select_best_prompt, build_synthesis_prompt
from tools.models import SelectionScore, SynthesisResult

logger = logging.getLogger(__name__)


def select_synthesis_model(
    debate_roster: list[str],
    override: Optional[str] = None,
    available_models: Optional[list[dict[str, Any]]] = None,
) -> Optional[str]:
    """
    Select the model to use for synthesis.

    Priority:
    1. Per-call override (synthesis_model param)
    2. Global override (DEBATE_SYNTHESIS_MODEL config)
    3. Model NOT in the debate roster (avoids bias)
    4. Highest-capability available model (fallback)

    Args:
        debate_roster: Model IDs that participated in the debate.
        override: Per-call synthesis_model override.
        available_models: List of {model_id, capability_rank} for selection.

    Returns:
        Model ID to use for synthesis, or None if caller should use default.
    """
    # 1. Per-call override
    if override:
        return override

    # 2. Global override
    if cfg.DEBATE_SYNTHESIS_MODEL:
        return cfg.DEBATE_SYNTHESIS_MODEL

    # 3. Non-participant preference
    if available_models:
        non_participants = [m for m in available_models if m["model_id"] not in debate_roster]
        if non_participants:
            # Pick highest capability among non-participants
            non_participants.sort(key=lambda m: m.get("capability_rank", 0), reverse=True)
            return non_participants[0]["model_id"]

        # 4. Fallback to highest-capability available
        sorted_models = sorted(
            available_models,
            key=lambda m: m.get("capability_rank", 0),
            reverse=True,
        )
        return sorted_models[0]["model_id"]

    return None


async def synthesize(
    original_prompt: str,
    round1_responses: dict[str, str],
    round2_responses: dict[str, str],
    provider_call_fn,
    synthesis_model: Optional[str] = None,
) -> SynthesisResult:
    """
    Merge all perspectives into unified analysis.

    Args:
        original_prompt: The original analysis request.
        round1_responses: Alias → Round 1 content.
        round2_responses: Alias → Round 2 content.
        provider_call_fn: Async callable(prompt, model) → response content.
        synthesis_model: Model to use for synthesis.

    Returns:
        SynthesisResult with agreement/disagreement/recommendations.
    """
    prompt = build_synthesis_prompt(original_prompt, round1_responses, round2_responses)

    response_text = await provider_call_fn(prompt, synthesis_model)

    # Parse structured output
    agreement = _extract_section(response_text, "AGREEMENT POINTS")
    disagreement = _extract_section(response_text, "DISAGREEMENT POINTS")
    recommendations = _extract_section(response_text, "RECOMMENDATIONS")

    return SynthesisResult(
        mode="synthesize",
        synthesis=response_text,
        agreement_points=agreement,
        disagreement_points=disagreement,
        recommendations=recommendations,
        synthesizer_model=synthesis_model or "unknown",
    )


async def select_best(
    original_prompt: str,
    responses: dict[str, str],
    provider_call_fn,
    synthesis_model: Optional[str] = None,
) -> SynthesisResult:
    """
    Score each response and select the best one.

    Args:
        original_prompt: The original analysis request.
        responses: Alias → response content.
        provider_call_fn: Async callable(prompt, model) → response content.
        synthesis_model: Model to use for scoring.

    Returns:
        SynthesisResult with scores and selected winner.
    """
    prompt = build_select_best_prompt(original_prompt, responses)
    response_text = await provider_call_fn(prompt, synthesis_model)

    # Parse scores
    scores = _parse_scores(response_text)
    selected_alias = _extract_field(response_text, "SELECTED")
    selection_rationale = _extract_field(response_text, "SELECTION_RATIONALE")

    # If parsing failed, use the full response as the selected one
    if not selected_alias and scores:
        best = max(scores.values(), key=lambda s: s.score)
        selected_alias = best.alias

    # Get the winning response text
    winning_text = responses.get(selected_alias, response_text)

    return SynthesisResult(
        mode="select_best",
        synthesis=winning_text,
        scores=dict(scores.items()) if scores else None,
        selected_alias=selected_alias,
        selection_rationale=selection_rationale,
        synthesizer_model=synthesis_model or "unknown",
    )


# =============================================================================
# Parsing helpers
# =============================================================================


def _extract_section(text: str, heading: str) -> list[str]:
    """Extract bullet points from a section identified by heading."""
    pattern = rf"\*?\*?{re.escape(heading)}\*?\*?:?\s*\n(.*?)(?=\n\*?\*?[A-Z]|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not match:
        return []

    section = match.group(1)
    # Extract bullet points (-, *, numbered)
    points = re.findall(r"^[\s]*[-*\d.]+\s+(.+)$", section, re.MULTILINE)
    return [p.strip() for p in points if p.strip()]


def _parse_scores(text: str) -> dict[str, SelectionScore]:
    """Parse SCORES JSON block from select_best response."""
    # Look for SCORES: [...] block
    pattern = r"SCORES:\s*\[([^\]]+)\]"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        # Try ```json block
        pattern = r"```json\s*\nSCORES:\s*\[([^\]]+)\]"
        match = re.search(pattern, text, re.DOTALL)

    if not match:
        return {}

    try:
        scores_json = json.loads(f"[{match.group(1)}]")
        return {
            s["alias"]: SelectionScore(
                alias=s["alias"],
                score=float(s.get("score", 5)),
                rationale=s.get("rationale", ""),
            )
            for s in scores_json
            if "alias" in s
        }
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("Failed to parse SCORES block from synthesis response")
        return {}


def _extract_field(text: str, field: str) -> Optional[str]:
    """Extract a single field value like SELECTED: 'alpha'."""
    pattern = rf'{field}:\s*"?([^"\n]+)"?'
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip().strip('"').strip("'")
    return None
