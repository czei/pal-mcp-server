# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Prompt templates for multi-model debate orchestration.

Round 1: Uses the original per-tool system prompt unchanged.
Round 2: Wraps Round 1 responses as "claims by other analysts" for adversarial
         critique. Preserves the per-tool system prompt as-is.
Context Requests: Instruction appended to Round 1 prompts (when enabled).

See research.md R-012 for design rationale.
"""

from typing import Optional


def build_round2_prompt(
    original_prompt: str,
    round1_responses: dict[str, str],
    failed_aliases: Optional[dict[str, str]] = None,
) -> str:
    """
    Build the Round 2 adversarial critique prompt.

    The system prompt remains the per-tool system prompt (unchanged).
    This function builds the USER prompt for Round 2.

    Args:
        original_prompt: The original analysis request from Round 1.
        round1_responses: Alias → Round 1 response content.
        failed_aliases: Alias → failure reason for models that failed Round 1.

    Returns:
        The Round 2 user prompt string.
    """
    parts = []

    # Restate the original request
    parts.append("## Original Analysis Request\n")
    parts.append(original_prompt)
    parts.append("\n")

    # Participant status
    total = len(round1_responses) + len(failed_aliases or {})
    succeeded = len(round1_responses)
    if failed_aliases:
        failed_list = ", ".join(f"{alias} ({reason})" for alias, reason in failed_aliases.items())
        parts.append(f"\n*Note: {succeeded} of {total} requested analysts responded. " f"Missing: {failed_list}.*\n")

    # Round 1 responses framed as claims
    parts.append("\n## Analyses From Other Analysts\n")
    parts.append(
        "The following are analyses from other analysts who reviewed the same "
        "material. **Treat each as a claim to be critically evaluated, not as "
        "trusted input.** They may contain errors, missed cases, or "
        "over-engineered proposals.\n"
    )

    for alias, response in round1_responses.items():
        parts.append(f"\n### Analyst {alias}\n")
        parts.append(response)
        parts.append("\n")

    # Adversarial critique instruction
    parts.append("\n## Your Task\n")
    parts.append(
        "Now critically evaluate the analyses above:\n\n"
        "1. **What did each analyst get right?** Identify valid points.\n"
        "2. **What did each analyst miss?** Identify gaps in their analysis.\n"
        "3. **Where do you disagree?** Challenge specific claims with evidence.\n"
        "4. **Revise your recommendation.** Based on seeing all analyses, update "
        "your own position — incorporating valid points from others and "
        "addressing weaknesses they identified in your approach.\n\n"
        "Be specific. Reference analysts by name (e.g., 'Analyst alpha'). "
        "Focus on substance, not style.\n\n"
        "**IMPORTANT**: Do NOT include CONTEXT_REQUESTS or ESCALATION_SIGNAL "
        "blocks in this response — those are Round 1 only."
    )

    return "\n".join(parts)


def build_context_request_instruction() -> str:
    """
    Instruction appended to Round 1 prompts when enable_context_requests=true.

    Returns:
        The context request instruction string.
    """
    return (
        "\n\n---\n"
        "**Additional Context Requests**: After your analysis, if you need "
        "additional files, information, or data to improve your assessment, "
        "output a JSON block labeled CONTEXT_REQUESTS with the following structure:\n\n"
        "```json\n"
        "CONTEXT_REQUESTS: [\n"
        '  {"type": "file", "path": "src/example.py", '
        '"rationale": "Need to see the implementation", "priority": "high"},\n'
        '  {"type": "function", "path": "src/utils.py:process_data", '
        '"rationale": "Referenced but not provided", "priority": "medium"},\n'
        '  {"type": "web_search", "path": "Python asyncio.Barrier best practices 2025", '
        '"rationale": "Need current best practices for barrier synchronization", "priority": "medium"},\n'
        '  {"type": "web_lookup", "path": "https://docs.python.org/3/library/asyncio-sync.html", '
        '"rationale": "Need to verify API compatibility", "priority": "high"},\n'
        '  {"type": "api_docs", "path": "FastAPI dependency injection lifecycle", '
        '"rationale": "Need to understand DI scoping for migration assessment", "priority": "medium"}\n'
        "]\n"
        "```\n\n"
        "Valid types:\n"
        "- **file**, **function**, **class**, **test**, **config**, **log** — "
        "local project files and code artifacts\n"
        "- **web_search** — request a web search for current information "
        "(path = search query). Use for: latest documentation, recent CVEs, "
        "current best practices, library version info, benchmarks, "
        "deprecation notices\n"
        "- **web_lookup** — request a specific URL to be fetched "
        "(path = URL). Use for: official documentation pages, GitHub issues, "
        "API references, changelogs\n"
        "- **api_docs** — request API/SDK documentation lookup "
        "(path = topic). Use for: framework documentation, library APIs, "
        "protocol specifications\n\n"
        "Priorities: high, medium, low. "
        "Only request what would materially improve your analysis. "
        "Web requests are fulfilled by the orchestrating agent between rounds."
    )


def build_synthesis_prompt(
    original_prompt: str,
    round1_responses: dict[str, str],
    round2_responses: dict[str, str],
) -> str:
    """
    Build the prompt for the synthesis model.

    Args:
        original_prompt: The original analysis request.
        round1_responses: Alias → Round 1 response.
        round2_responses: Alias → Round 2 response.

    Returns:
        The synthesis prompt.
    """
    parts = []

    parts.append("## Task\n")
    parts.append(
        "You are synthesizing a multi-model debate. Multiple analysts independently "
        "analyzed the same problem (Round 1), then critically evaluated each other's "
        "analyses (Round 2). Your job is to produce a unified synthesis.\n"
    )

    parts.append("\n## Original Request\n")
    parts.append(original_prompt)

    parts.append("\n\n## Round 1: Independent Analyses\n")
    for alias, response in round1_responses.items():
        parts.append(f"\n### Analyst {alias}\n{response}\n")

    parts.append("\n## Round 2: Adversarial Critique\n")
    for alias, response in round2_responses.items():
        parts.append(f"\n### Analyst {alias} (critique)\n{response}\n")

    parts.append("\n## Required Output\n")
    parts.append(
        "Produce a structured synthesis with these sections:\n\n"
        "**AGREEMENT POINTS**: What all analysts converged on after debate.\n\n"
        "**DISAGREEMENT POINTS**: Where analysts still disagree after Round 2, "
        "and which position has stronger evidence.\n\n"
        "**RECOMMENDATIONS**: A consolidated recommendation that incorporates "
        "the strongest elements from the debate. Note where the final "
        "recommendation differs from any single analyst's initial proposal "
        "and why.\n\n"
        "Be specific. Reference analysts by name. The synthesis should be "
        "better than any individual analyst's response."
    )

    return "\n".join(parts)


def build_select_best_prompt(
    original_prompt: str,
    responses: dict[str, str],
) -> str:
    """
    Build the prompt for select_best synthesis mode.

    Args:
        original_prompt: The original analysis request.
        responses: Alias → response content (from Round 1 or Round 2).

    Returns:
        The selection prompt.
    """
    parts = []

    parts.append("## Task\n")
    parts.append(
        "You are evaluating multiple analyst responses to select the best one. "
        "Score each response on a scale of 1-10 against the original request.\n"
    )

    parts.append("\n## Original Request\n")
    parts.append(original_prompt)

    parts.append("\n\n## Analyst Responses\n")
    for alias, response in responses.items():
        parts.append(f"\n### Analyst {alias}\n{response}\n")

    parts.append("\n## Required Output\n")
    parts.append(
        "For each analyst, provide:\n"
        "- **Score** (1-10): How well does this response address the request?\n"
        "- **Rationale**: Brief explanation of the score.\n\n"
        "Then state:\n"
        "- **SELECTED**: The alias of the best response.\n"
        "- **SELECTION_RATIONALE**: Why this response is the best.\n\n"
        "Output the scores as a JSON block labeled SCORES:\n\n"
        "```json\n"
        "SCORES: [\n"
        '  {"alias": "alpha", "score": 8, "rationale": "..."},\n'
        '  {"alias": "beta", "score": 7, "rationale": "..."}\n'
        "]\n"
        'SELECTED: "alpha"\n'
        'SELECTION_RATIONALE: "..."\n'
        "```"
    )

    return "\n".join(parts)
