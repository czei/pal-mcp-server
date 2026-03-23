# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Adaptive review escalation: parsing escalation signals from single-model
reviews and evaluating whether to auto-promote to full multi-model debate.

See spec FR-021, FR-030, and research.md R-010.
"""

import json
import logging
import re
from typing import Optional

import config as cfg
from sessions.types import EscalationSignal

logger = logging.getLogger(__name__)


# =============================================================================
# Signal Parsing (T042)
# =============================================================================


def parse_escalation_signal(response_text: str) -> EscalationSignal:
    """
    Extract EscalationSignal from a single-model review response.

    Primary: Look for ESCALATION_SIGNAL JSON block.
    Fallback: Return defaults (confidence=0.8, complexity=medium, no anomalies).

    Args:
        response_text: The model's full response text.

    Returns:
        Parsed EscalationSignal.
    """
    # Try JSON block extraction
    signal = _parse_json_escalation(response_text)
    if signal:
        return signal

    # Fallback defaults — assume the review is confident
    return EscalationSignal(
        confidence=0.8,
        complexity="medium",
        anomalies_detected=False,
        escalation_recommended=False,
    )


def _parse_json_escalation(text: str) -> Optional[EscalationSignal]:
    """Parse ESCALATION_SIGNAL from JSON block."""
    # Pattern 1: ESCALATION_SIGNAL: {...}
    pattern = r"ESCALATION_SIGNAL:\s*(\{[^}]+\})"
    match = re.search(pattern, text, re.DOTALL)

    if not match:
        # Pattern 2: ```json\nESCALATION_SIGNAL: {...}
        pattern = r"```(?:json)?\s*\n\s*ESCALATION_SIGNAL:\s*(\{[^}]+\})"
        match = re.search(pattern, text, re.DOTALL)

    if not match:
        return None

    try:
        data = json.loads(match.group(1))
        return EscalationSignal(
            confidence=float(data.get("confidence", 0.8)),
            complexity=data.get("complexity", "medium"),
            anomalies_detected=bool(data.get("anomalies_detected", False)),
            escalation_recommended=bool(data.get("escalation_recommended", False)),
            escalation_reason=data.get("escalation_reason"),
            risk_areas=data.get("risk_areas", []),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.debug(f"Failed to parse ESCALATION_SIGNAL: {e}")
        return None


# =============================================================================
# Escalation Evaluation (T043)
# =============================================================================


def evaluate_escalation(
    signal: EscalationSignal,
    confidence_threshold: Optional[float] = None,
    complexity_threshold: Optional[str] = None,
) -> bool:
    """
    Evaluate whether an escalation signal triggers auto-promotion to debate.

    Checks against configurable thresholds (per-call overrides or global defaults).

    Args:
        signal: The parsed escalation signal.
        confidence_threshold: Per-call override (or None for global default).
        complexity_threshold: Per-call override (or None for global default).

    Returns:
        True if escalation should be triggered.
    """
    conf_threshold = confidence_threshold or cfg.ESCALATION_CONFIDENCE_THRESHOLD
    comp_threshold = complexity_threshold or cfg.ESCALATION_COMPLEXITY_THRESHOLD

    complexity_order = {"low": 0, "medium": 1, "high": 2}

    # Check confidence
    if signal.confidence < conf_threshold:
        logger.info(f"Escalation triggered: confidence {signal.confidence} < {conf_threshold}")
        return True

    # Check complexity
    signal_level = complexity_order.get(signal.complexity, 1)
    threshold_level = complexity_order.get(comp_threshold, 2)
    if signal_level >= threshold_level:
        logger.info(f"Escalation triggered: complexity '{signal.complexity}' >= '{comp_threshold}'")
        return True

    # Check anomalies
    if signal.anomalies_detected:
        logger.info("Escalation triggered: anomalies detected")
        return True

    # Check risk areas
    if signal.risk_areas:
        overlap = set(signal.risk_areas) & set(cfg.ESCALATION_AUTO_RISK_AREAS)
        if overlap:
            logger.info(f"Escalation triggered: risk areas {overlap}")
            return True

    # Check explicit recommendation
    if signal.escalation_recommended:
        logger.info(f"Escalation triggered: model recommended (reason: {signal.escalation_reason})")
        return True

    return False


# =============================================================================
# Prompt Instructions (T041)
# =============================================================================

ESCALATION_SIGNAL_INSTRUCTION = """

---
**Review Self-Assessment**: After your review, output a structured self-assessment block:

```json
ESCALATION_SIGNAL: {
  "confidence": 0.85,
  "complexity": "medium",
  "anomalies_detected": false,
  "escalation_recommended": false,
  "escalation_reason": null,
  "risk_areas": []
}
```

Fields:
- **confidence** (0.0-1.0): How confident are you in the completeness of your review?
- **complexity** ("low"/"medium"/"high"): Assessed complexity of the code under review.
- **anomalies_detected** (true/false): Did you find issues you cannot fully resolve alone?
- **escalation_recommended** (true/false): Do you recommend a multi-model review?
- **escalation_reason** (string or null): If recommending escalation, explain why.
- **risk_areas** (list): Tags for risk areas found (e.g., "concurrency", "auth", "parsing").
"""
