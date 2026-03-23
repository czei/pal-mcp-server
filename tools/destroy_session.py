# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""destroy_session tool: Explicitly destroy a debate session."""

import json
import logging
from typing import Any

from tools.models import ToolOutput

logger = logging.getLogger(__name__)


class DestroySessionTool:
    """MCP tool for destroying debate sessions."""

    def __init__(self):
        self._session_manager = None

    def get_name(self) -> str:
        return "destroy_session"

    def get_description(self) -> str:
        return "Explicitly destroy a debate session. Cancels worker tasks. " "Evaluation data is preserved."

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to destroy.",
                },
            },
            "required": ["session_id"],
            "additionalProperties": False,
        }

    def requires_model(self) -> bool:
        return False

    async def execute(self, arguments: dict) -> list:
        from mcp.types import TextContent

        if not self._session_manager:
            error = ToolOutput(status="error", content="Debate infrastructure not initialized.")
            return [TextContent(type="text", text=error.model_dump_json())]

        session_id = arguments["session_id"]
        destroyed = await self._session_manager.destroy_session(session_id)

        result = {
            "destroyed": destroyed,
            "evaluation_data_preserved": True,
            "session_id": session_id,
        }

        if not destroyed:
            result["reason"] = "session not found"

        output = ToolOutput(
            status="success",
            content=json.dumps(result),
            content_type="json",
            metadata=result,
        )
        return [TextContent(type="text", text=output.model_dump_json())]
