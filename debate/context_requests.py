# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Context request parsing and deduplication for multi-model debate.

Parses structured CONTEXT_REQUESTS from model Round 1 responses,
deduplicates across models, and returns a unified list for the caller
to gather artifacts.

See research.md R-005.
"""

import json
import logging
import re

from sessions.types import ContextRequest

logger = logging.getLogger(__name__)


# =============================================================================
# Parsing (T037)
# =============================================================================


def parse_context_requests(
    response_text: str,
    requested_by: str,
) -> list[ContextRequest]:
    """
    Extract structured context requests from a model's response.

    Primary: Look for JSON blocks with CONTEXT_REQUESTS marker.
    Fallback: Regex for file paths in "I would need" / "additional context" sections.

    Args:
        response_text: The model's full response text.
        requested_by: Alias of the model that produced this response.

    Returns:
        List of parsed ContextRequest objects.
    """
    requests = []

    # Primary: JSON block extraction
    requests = _parse_json_context_requests(response_text, requested_by)
    if requests:
        return requests

    # Fallback: Regex for file path mentions
    requests = _parse_regex_context_requests(response_text, requested_by)
    return requests


def _parse_json_context_requests(text: str, requested_by: str) -> list[ContextRequest]:
    """Parse CONTEXT_REQUESTS from JSON blocks."""
    # Pattern 1: CONTEXT_REQUESTS: [...]
    pattern = r"CONTEXT_REQUESTS:\s*\[([^\]]*)\]"
    match = re.search(pattern, text, re.DOTALL)

    if not match:
        # Pattern 2: ```json\nCONTEXT_REQUESTS: [...]
        pattern = r"```(?:json)?\s*\n\s*CONTEXT_REQUESTS:\s*\[([^\]]*)\]"
        match = re.search(pattern, text, re.DOTALL)

    if not match:
        # Pattern 3: Any JSON array with type/path fields
        pattern = r"```(?:json)?\s*\n\s*(\[(?:[^\]]*\"type\"[^\]]*\"path\"[^\]]*)\])"
        match = re.search(pattern, text, re.DOTALL)

    if not match:
        return []

    try:
        json_text = f"[{match.group(1)}]"
        # Clean up common JSON issues
        json_text = re.sub(r",\s*\]", "]", json_text)  # trailing comma
        items = json.loads(json_text)

        return [
            ContextRequest(
                artifact_type=item.get("type", "file"),
                path=item.get("path", ""),
                rationale=item.get("rationale", ""),
                priority=item.get("priority", "medium"),
                requested_by=requested_by,
            )
            for item in items
            if item.get("path")
        ]
    except (json.JSONDecodeError, TypeError) as e:
        logger.debug(f"Failed to parse CONTEXT_REQUESTS JSON: {e}")
        return []


def _parse_regex_context_requests(text: str, requested_by: str) -> list[ContextRequest]:
    """Fallback: extract file paths from 'I would need' sections."""
    requests = []

    # Look for sections mentioning needed context
    need_patterns = [
        r"(?:I would need|would be helpful|additional context|need to see|wish I had)\s+(?:access to\s+)?[`\"']?([/\w.\-]+\.\w+)[`\"']?",
        r"(?:Missing|Not provided|Not included):\s*[`\"']?([/\w.\-]+\.\w+)[`\"']?",
    ]

    seen_paths = set()
    for pattern in need_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            path = match.group(1)
            if path not in seen_paths and len(path) > 3:
                seen_paths.add(path)
                requests.append(
                    ContextRequest(
                        artifact_type="file",
                        path=path,
                        rationale="Mentioned as needed in analysis",
                        priority="medium",
                        requested_by=requested_by,
                    )
                )

    return requests


# =============================================================================
# Deduplication (T038)
# =============================================================================


def deduplicate_requests(
    all_requests: list[ContextRequest],
) -> list[ContextRequest]:
    """
    Merge context requests across models by path.
    Keeps highest priority, aggregates rationales.

    Args:
        all_requests: All context requests from all models.

    Returns:
        Deduplicated list sorted by priority (high → medium → low).
    """
    by_path: dict[str, ContextRequest] = {}
    priority_order = {"high": 0, "medium": 1, "low": 2}

    for req in all_requests:
        if req.path in by_path:
            existing = by_path[req.path]
            # Keep highest priority
            if priority_order.get(req.priority, 1) < priority_order.get(existing.priority, 1):
                existing.priority = req.priority
            # Aggregate rationales
            if req.rationale and req.rationale not in existing.rationale:
                existing.rationale += f"; {req.requested_by}: {req.rationale}"
            # Track who requested
            if req.requested_by not in existing.requested_by:
                existing.requested_by += f", {req.requested_by}"
        else:
            by_path[req.path] = ContextRequest(
                artifact_type=req.artifact_type,
                path=req.path,
                rationale=f"{req.requested_by}: {req.rationale}",
                priority=req.priority,
                requested_by=req.requested_by,
            )

    # Sort by priority
    result = sorted(
        by_path.values(),
        key=lambda r: priority_order.get(r.priority, 1),
    )

    logger.info(f"Deduplicated {len(all_requests)} context requests → {len(result)} unique")
    return result
