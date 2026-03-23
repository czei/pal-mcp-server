# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Evaluation aggregation queries for the compare_models tool.

Reads JSONL evaluation logs and computes aggregated metrics
grouped by model, task_type, or both.
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from evaluation.logger import EvaluationLogger

logger = logging.getLogger(__name__)


class EvaluationReporter:
    """Aggregation queries over evaluation JSONL data."""

    def __init__(self, eval_logger: EvaluationLogger):
        self._logger = eval_logger

    def query(
        self,
        task_type: Optional[str] = None,
        model: Optional[str] = None,
        since: Optional[str] = None,
        group_by: str = "model",
    ) -> dict[str, Any]:
        """
        Query and aggregate evaluation data.

        Args:
            task_type: Filter by task type (e.g., "debug"). None for all.
            model: Filter by model. None for all.
            since: ISO 8601 date string. Only include records after this.
            group_by: "model", "task_type", or "model_and_task_type".

        Returns:
            Dict with comparisons list and period metadata.
        """
        records = self._logger.read_all()

        # Apply filters
        filtered = self._apply_filters(records, task_type, model, since)

        # Group and aggregate
        groups = self._group_records(filtered, group_by)
        comparisons = [self._compute_metrics(key, group_records) for key, group_records in groups.items()]

        # Sort by query_count descending
        comparisons.sort(key=lambda c: c.get("query_count", 0), reverse=True)

        # Period metadata
        timestamps = [r.get("timestamp", "") for r in filtered if r.get("timestamp")]
        period = {
            "from": min(timestamps) if timestamps else None,
            "to": max(timestamps) if timestamps else None,
            "total_records": len(filtered),
        }

        return {"comparisons": comparisons, "period": period}

    @staticmethod
    def _apply_filters(
        records: list[dict],
        task_type: Optional[str],
        model: Optional[str],
        since: Optional[str],
    ) -> list[dict]:
        """Apply task_type, model, and date filters."""
        filtered = records

        if task_type:
            filtered = [r for r in filtered if r.get("task_type") == task_type]

        if model:
            filtered = [r for r in filtered if r.get("model") == model]

        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                filtered = [
                    r
                    for r in filtered
                    if r.get("timestamp") and datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) >= since_dt
                ]
            except (ValueError, TypeError):
                logger.warning(f"Invalid 'since' date: {since}")

        return filtered

    @staticmethod
    def _group_records(records: list[dict], group_by: str) -> dict[str, list[dict]]:
        """Group records by the specified key."""
        groups = defaultdict(list)

        for r in records:
            if group_by == "model":
                key = r.get("model", "unknown")
            elif group_by == "task_type":
                key = r.get("task_type", "unknown")
            elif group_by == "model_and_task_type":
                key = f"{r.get('model', 'unknown')}:{r.get('task_type', 'unknown')}"
            else:
                key = r.get("model", "unknown")

            groups[key].append(r)

        return dict(groups)

    @staticmethod
    def _compute_metrics(key: str, records: list[dict]) -> dict[str, Any]:
        """Compute aggregated metrics for a group."""
        total = len(records)
        if total == 0:
            return {"key": key, "query_count": 0}

        latencies = [r.get("latency_ms", 0) for r in records]
        input_tokens = sum(r.get("input_tokens", 0) for r in records)
        output_tokens = sum(r.get("output_tokens", 0) for r in records)
        total_tokens = input_tokens + output_tokens
        successes = sum(1 for r in records if r.get("status") == "success")
        follow_ups = sum(1 for r in records if r.get("is_follow_up"))

        # Unique sessions for follow-up depth
        sessions = defaultdict(int)
        for r in records:
            sid = r.get("session_id", "")
            if sid:
                sessions[sid] = max(sessions[sid], r.get("exchange_number", 0))

        avg_follow_up_depth = sum(sessions.values()) / len(sessions) if sessions else 0

        # Split key for model_and_task_type
        parts = key.split(":", 1)
        result = {
            "model": parts[0] if len(parts) >= 1 else key,
            "task_type": parts[1] if len(parts) > 1 else None,
            "query_count": total,
            "avg_latency_ms": int(sum(latencies) / total) if total else 0,
            "total_tokens": total_tokens,
            "avg_tokens_per_response": int(total_tokens / total) if total else 0,
            "success_rate": round(successes / total, 3) if total else 0,
            "follow_up_rate": round(follow_ups / total, 3) if total else 0,
            "avg_follow_up_depth": round(avg_follow_up_depth, 1),
        }

        return result
