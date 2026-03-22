# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Session lifecycle management for multi-model debate.

Creates sessions with async worker coroutines, manages garbage collection,
and provides the shared ThreadPoolExecutor for blocking provider calls.
"""

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Optional

import config as cfg
from sessions.store import InMemorySessionStore
from sessions.types import (
    DebateConfig,
    DebateSession,
    ModelState,
    ModelWorker,
    SessionStatus,
    SharedContext,
    WorkerRuntime,
)

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages debate session lifecycle, workers, and garbage collection."""

    def __init__(self):
        self.store = InMemorySessionStore()
        self._worker_runtimes: dict[str, dict[str, WorkerRuntime]] = {}
        # session_id → {alias → WorkerRuntime}

        # Shared thread pool for blocking provider.generate_content() calls
        max_workers = cfg.SESSION_MAX_CONCURRENT * 3 + 10
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        logger.info(
            f"SessionManager initialized (max_sessions={cfg.SESSION_MAX_CONCURRENT}, "
            f"thread_pool_workers={max_workers})"
        )

        # GC task reference
        self._gc_task: Optional[asyncio.Task] = None

    @property
    def executor(self) -> ThreadPoolExecutor:
        """Shared thread pool for asyncio.to_thread() calls."""
        return self._executor

    # =========================================================================
    # Session Lifecycle
    # =========================================================================

    async def create_session(
        self,
        task_type: str,
        model_configs: list[dict[str, Any]],
        debate_config: Optional[DebateConfig] = None,
    ) -> DebateSession:
        """
        Create a new debate session with worker coroutine placeholders.

        Workers are not started here — the DebateOrchestrator starts them
        when the debate begins (needs the actual prompts first).

        Args:
            task_type: Tool that initiated ("debug", "codereview", etc.)
            model_configs: List of {alias, model, provider_name, max_context}
            debate_config: Optional per-session config overrides.

        Returns:
            The created DebateSession.
        """
        if self.store.session_count >= cfg.SESSION_MAX_CONCURRENT:
            logger.warning(
                f"Max concurrent sessions ({cfg.SESSION_MAX_CONCURRENT}) reached"
            )
            # Could raise, but let's be permissive and let GC handle pressure

        session = DebateSession(
            task_type=task_type,
            debate_config=debate_config or DebateConfig(),
        )

        # Initialize per-model state and worker metadata
        runtimes: dict[str, WorkerRuntime] = {}
        for mc in model_configs:
            alias = mc["alias"]
            max_context = mc.get("max_context", 200000)

            session.models[alias] = ModelState(
                alias=alias,
                provider_name=mc.get("provider_name", "unknown"),
                model_id=mc["model"],
                max_context=max_context,
                compression_threshold=0.7 * max_context,
            )
            session.workers[alias] = ModelWorker(
                alias=alias,
                provider_name=mc.get("provider_name", "unknown"),
                model_id=mc["model"],
            )
            runtimes[alias] = WorkerRuntime(alias)

        self._worker_runtimes[session.id] = runtimes
        await self.store.set(session)

        logger.info(
            f"Created session {session.id} (task={task_type}, "
            f"models={[mc['alias'] for mc in model_configs]}, "
            f"trace={session.trace_id})"
        )
        return session

    async def get_session(self, session_id: str) -> Optional[DebateSession]:
        """Get a session by ID. Returns None if not found or expired."""
        return await self.store.get(session_id)

    def get_worker_runtime(
        self, session_id: str, alias: str
    ) -> Optional[WorkerRuntime]:
        """Get the runtime state for a specific worker."""
        session_runtimes = self._worker_runtimes.get(session_id, {})
        return session_runtimes.get(alias)

    def get_all_worker_runtimes(
        self, session_id: str
    ) -> dict[str, WorkerRuntime]:
        """Get all worker runtimes for a session."""
        return self._worker_runtimes.get(session_id, {})

    async def destroy_session(self, session_id: str) -> bool:
        """
        Destroy a session — cancel workers, remove from store.
        Evaluation data is preserved (it's in JSONL on disk, not in session).

        Returns True if session was found and destroyed.
        """
        # Cancel all worker tasks
        runtimes = self._worker_runtimes.pop(session_id, {})
        for alias, runtime in runtimes.items():
            runtime.request_shutdown()
            if runtime.task and not runtime.task.done():
                runtime.task.cancel()
                try:
                    await asyncio.wait_for(
                        asyncio.shield(runtime.task), timeout=2.0
                    )
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

        deleted = await self.store.delete(session_id)
        if deleted:
            logger.info(f"Destroyed session {session_id}")
        return deleted

    async def update_session(self, session: DebateSession) -> None:
        """Update session in store (after state changes)."""
        session.touch()
        await self.store.set(session)

    # =========================================================================
    # Garbage Collection
    # =========================================================================

    async def start_gc(self) -> None:
        """Start background GC timer."""
        if self._gc_task is None or self._gc_task.done():
            self._gc_task = asyncio.create_task(self._gc_loop())
            logger.info(
                f"Session GC started (interval={cfg.SESSION_GC_IDLE_MINUTES}min)"
            )

    async def stop_gc(self) -> None:
        """Stop background GC timer."""
        if self._gc_task and not self._gc_task.done():
            self._gc_task.cancel()
            try:
                await self._gc_task
            except asyncio.CancelledError:
                pass
            logger.info("Session GC stopped")

    async def _gc_loop(self) -> None:
        """Background loop that expires idle sessions."""
        while True:
            await asyncio.sleep(60)  # Check every minute
            await self._gc_expired_sessions()

    async def _gc_expired_sessions(self) -> None:
        """Find and expire sessions that have been idle too long."""
        now = datetime.now(timezone.utc)
        timeout_seconds = cfg.SESSION_GC_IDLE_MINUTES * 60
        sessions = await self.store.list_sessions(active_only=True)

        for session in sessions:
            elapsed = (now - session.last_active_at).total_seconds()
            if elapsed > timeout_seconds:
                logger.info(
                    f"GC expiring session {session.id} "
                    f"(idle {elapsed:.0f}s > {timeout_seconds}s)"
                )
                session.status = SessionStatus.EXPIRED
                await self.destroy_session(session.id)

    # =========================================================================
    # Shutdown
    # =========================================================================

    async def shutdown(self) -> None:
        """Clean shutdown — stop GC, destroy all sessions, shutdown executor."""
        await self.stop_gc()

        # Destroy all active sessions
        sessions = await self.store.list_sessions(active_only=False)
        for session in sessions:
            await self.destroy_session(session.id)

        # Shutdown thread pool
        self._executor.shutdown(wait=False)
        logger.info("SessionManager shut down")
