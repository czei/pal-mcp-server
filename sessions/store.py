# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
In-memory session store with per-session write locking.

Concurrent reads are safe (dict reads). Writes are serialized per session
via asyncio.Lock to prevent state corruption from concurrent teammate access.
"""

import asyncio
import logging
from typing import Optional

from sessions.types import DebateSession

logger = logging.getLogger(__name__)


class InMemorySessionStore:
    """Dict-based session storage with per-session locking."""

    def __init__(self):
        self._sessions: dict[str, DebateSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, session_id: str) -> Optional[DebateSession]:
        """Get a session by ID. Concurrent-safe (read only)."""
        return self._sessions.get(session_id)

    async def set(self, session: DebateSession) -> None:
        """Store or update a session. Acquires per-session lock."""
        lock = self._get_or_create_lock(session.id)
        async with lock:
            self._sessions[session.id] = session

    async def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if found and deleted."""
        lock = self._get_or_create_lock(session_id)
        async with lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                # Clean up the lock too
                self._locks.pop(session_id, None)
                return True
            return False

    async def list_sessions(self, active_only: bool = True) -> list[DebateSession]:
        """List sessions. Optionally filter to non-expired only."""
        from sessions.types import SessionStatus

        sessions = list(self._sessions.values())
        if active_only:
            sessions = [s for s in sessions if s.status != SessionStatus.EXPIRED]
        return sessions

    def get_lock(self, session_id: str) -> asyncio.Lock:
        """Get the lock for a session (for external write coordination)."""
        return self._get_or_create_lock(session_id)

    def _get_or_create_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create a per-session lock."""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    @property
    def session_count(self) -> int:
        """Number of stored sessions."""
        return len(self._sessions)
