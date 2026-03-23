# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""list_sessions tool: Show active debate sessions."""

import json
import logging
from typing import Any

from tools.models import ToolOutput

logger = logging.getLogger(__name__)


class ListSessionsTool:
    """MCP tool for listing debate sessions."""

    def __init__(self):
        self._session_manager = None

    def get_name(self) -> str:
        return "list_sessions"

    def get_description(self) -> str:
        return "List active multi-model debate sessions with per-model stats."

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "active_only": {
                    "type": "boolean",
                    "description": "Only return non-expired sessions. Default: true.",
                    "default": True,
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def requires_model(self) -> bool:
        return False

    async def execute(self, arguments: dict) -> list:
        from mcp.types import TextContent

        if not self._session_manager:
            error = ToolOutput(status="error", content="Debate infrastructure not initialized.")
            return [TextContent(type="text", text=error.model_dump_json())]

        active_only = arguments.get("active_only", True)
        sessions = await self._session_manager.store.list_sessions(active_only=active_only)

        session_list = []
        for s in sessions:
            models_info = []
            for alias, ms in s.models.items():
                models_info.append(
                    {
                        "alias": alias,
                        "model": ms.model_id,
                        "provider": ms.provider_name,
                        "exchange_count": ms.total_exchange_count,
                        "total_tokens": ms.total_input_tokens + ms.total_output_tokens,
                    }
                )
            session_list.append(
                {
                    "session_id": s.id,
                    "task_type": s.task_type,
                    "status": s.status.value,
                    "created_at": s.created_at.isoformat(),
                    "last_active_at": s.last_active_at.isoformat(),
                    "models": models_info,
                }
            )

        result = {"sessions": session_list}
        output = ToolOutput(
            status="success",
            content=json.dumps(result, indent=2),
            content_type="json",
            metadata=result,
        )
        return [TextContent(type="text", text=output.model_dump_json())]
