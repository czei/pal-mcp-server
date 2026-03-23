# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
compare_models tool: Query evaluation logs for model performance analysis.
"""

import json
import logging
from typing import Any

from evaluation.logger import EvaluationLogger
from evaluation.reporter import EvaluationReporter
from tools.models import ToolOutput

logger = logging.getLogger(__name__)


class CompareModelsTool:
    """MCP tool for querying evaluation data."""

    def __init__(self):
        self._session_manager = None
        self._eval_logger = None

    def get_name(self) -> str:
        return "compare_models"

    def get_description(self) -> str:
        return (
            "Query evaluation logs for model performance analysis. " "Aggregates metrics by model, task type, or both."
        )

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "description": "Filter by task type (e.g., 'debug'). Omit for all.",
                },
                "model": {
                    "type": "string",
                    "description": "Filter by model. Omit for all.",
                },
                "since": {
                    "type": "string",
                    "description": "ISO 8601 date. Only include records after this.",
                },
                "group_by": {
                    "type": "string",
                    "enum": ["model", "task_type", "model_and_task_type"],
                    "description": "How to aggregate. Default: 'model'.",
                    "default": "model",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def requires_model(self) -> bool:
        return False

    async def execute(self, arguments: dict) -> list:
        from mcp.types import TextContent

        if not self._eval_logger:
            self._eval_logger = EvaluationLogger()

        reporter = EvaluationReporter(self._eval_logger)

        result = reporter.query(
            task_type=arguments.get("task_type"),
            model=arguments.get("model"),
            since=arguments.get("since"),
            group_by=arguments.get("group_by", "model"),
        )

        output = ToolOutput(
            status="success",
            content=json.dumps(result, indent=2),
            content_type="json",
            metadata=result,
        )
        return [TextContent(type="text", text=output.model_dump_json())]
