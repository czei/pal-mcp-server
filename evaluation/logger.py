# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
JSONL structured event logger for multi-model debate evaluation.

Appends one JSON line per model interaction to logs/evaluation.jsonl.
Thread-safe writes via asyncio.Lock.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import config as cfg

logger = logging.getLogger(__name__)


class EvaluationLogger:
    """Thread-safe JSONL event logger."""

    def __init__(self, log_dir: str = None):
        self._log_dir = log_dir or cfg.EVALUATION_LOG_DIR
        self._log_file = os.path.join(self._log_dir, "evaluation.jsonl")
        self._lock = asyncio.Lock()

        # Ensure log directory exists
        os.makedirs(self._log_dir, exist_ok=True)

    async def log_event(self, record: dict[str, Any]) -> None:
        """
        Append an evaluation record as a JSON line.

        Args:
            record: Dict with evaluation fields (see data-model.md EvaluationRecord).
        """
        # Ensure timestamp
        if "timestamp" not in record:
            record["timestamp"] = datetime.now(timezone.utc).isoformat()

        async with self._lock:
            try:
                with open(self._log_file, "a") as f:
                    f.write(json.dumps(record, default=str) + "\n")
            except Exception as e:
                logger.error(f"Failed to write evaluation log: {e}")

    def read_all(self) -> list[dict[str, Any]]:
        """Read all records from the log file. Synchronous for queries."""
        records = []
        if not os.path.exists(self._log_file):
            return records

        try:
            with open(self._log_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"Failed to read evaluation log: {e}")

        return records
