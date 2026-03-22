# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Session data types for multi-model debate state management.

All types are pydantic BaseModels for validation and serialization.
See data-model.md for entity documentation.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class SessionStatus(str, Enum):
    """Debate session lifecycle states."""

    ACTIVE = "active"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    EXPIRED = "expired"


class PinnedFactCategory(str, Enum):
    """Categories for immutable pinned facts."""

    HYPOTHESIS = "hypothesis"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    FINDING = "finding"


class PinnedFactStatus(str, Enum):
    """Status of a pinned fact — transitions: ACTIVE → CONFIRMED or REJECTED."""

    ACTIVE = "active"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


# =============================================================================
# Core Data Types
# =============================================================================


class PinnedFact(BaseModel):
    """An immutable piece of information established during a session."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    source: str  # e.g., "gpt-4o/round1"
    category: PinnedFactCategory
    status: PinnedFactStatus = PinnedFactStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContextRequest(BaseModel):
    """A structured request from a model for additional information."""

    artifact_type: str  # "file", "function", "class", "test", "config", "log"
    path: str
    rationale: str
    priority: str = "medium"  # "high", "medium", "low"
    requested_by: str  # Model alias


class Exchange(BaseModel):
    """A single request-response pair with a model."""

    round: int  # 1, 2, or follow-up number
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    token_count: int = 0
    context_requests: list[ContextRequest] = Field(default_factory=list)


class Checkpoint(BaseModel):
    """A named snapshot of model state at a specific point."""

    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pinned_facts_snapshot: list[PinnedFact] = Field(default_factory=list)
    working_summary_snapshot: str = ""
    exchange_count: int = 0


class Attachment(BaseModel):
    """A file or artifact included in debate context."""

    path: str
    content: str
    token_count: int = 0
    source: str = "original"  # "original" or "gathered"


# =============================================================================
# Model State (per-model within a session)
# =============================================================================


class ModelState(BaseModel):
    """Per-model memory within a debate session."""

    alias: str
    provider_name: str
    model_id: str
    max_context: int  # Provider-specific token limit

    # Stratified memory
    pinned_facts: list[PinnedFact] = Field(default_factory=list)
    working_summary: str = ""
    recent_exchanges: list[Exchange] = Field(default_factory=list)
    checkpoints: list[Checkpoint] = Field(default_factory=list)

    # Token tracking
    total_exchange_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    compression_threshold: float = 0.0  # Set to 0.7 * max_context on creation

    model_config = {"arbitrary_types_allowed": True}


# =============================================================================
# Shared Context (common to all models in a session)
# =============================================================================


class SharedContext(BaseModel):
    """Information common to all models in a session."""

    original_prompt: str = ""
    code_files: list[Attachment] = Field(default_factory=list)
    round1_responses: dict[str, str] = Field(default_factory=dict)  # alias → content
    gathered_artifacts: list[Attachment] = Field(default_factory=list)
    task_specific_prompt: str = ""  # From systemprompts/


# =============================================================================
# Debate Configuration
# =============================================================================


class DebateConfig(BaseModel):
    """Configuration for a specific debate session."""

    max_round: int = 2
    enable_context_requests: bool = True
    synthesis_mode: str = "synthesize"  # "synthesize" or "select_best"
    synthesis_model: Optional[str] = None  # None = auto-select non-participant
    summary_strategy: str = "llm"  # "llm" or "template"
    per_model_timeout_ms: int = 30000
    escalation_mode: str = "adaptive"  # "adaptive", "always_full", "never"
    escalation_confidence_threshold: Optional[float] = None  # Per-call override
    escalation_complexity_threshold: Optional[str] = None  # Per-call override


# =============================================================================
# Escalation Signal
# =============================================================================


class EscalationSignal(BaseModel):
    """Structured confidence/escalation output from single-model reviews."""

    confidence: float = 0.8  # 0.0-1.0
    complexity: str = "medium"  # "low", "medium", "high"
    anomalies_detected: bool = False
    escalation_recommended: bool = False
    escalation_reason: Optional[str] = None
    risk_areas: list[str] = Field(default_factory=list)


# =============================================================================
# Model Worker (async coroutine reference)
# =============================================================================


class ModelWorker(BaseModel):
    """
    Reference to an async worker coroutine for one model in a session.

    The actual asyncio.Task and asyncio.Event are stored outside pydantic
    (they aren't serializable). This model holds the metadata.
    """

    alias: str
    current_phase: Optional[str] = None  # "round1", "round2", "follow_up", "idle"
    provider_name: str
    model_id: str

    model_config = {"arbitrary_types_allowed": True}


# =============================================================================
# Debate Session (top-level container)
# =============================================================================


class DebateSession(BaseModel):
    """A coordinated multi-model analysis instance. Transient (in-memory)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = ""  # "debug", "codereview", "planner", etc.
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Per-model state
    models: dict[str, ModelState] = Field(default_factory=dict)
    workers: dict[str, ModelWorker] = Field(default_factory=dict)

    # Shared state
    shared_context: SharedContext = Field(default_factory=SharedContext)
    debate_config: DebateConfig = Field(default_factory=DebateConfig)

    # Session metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_active_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    round: int = 0
    status: SessionStatus = SessionStatus.ACTIVE

    model_config = {"arbitrary_types_allowed": True}

    def touch(self):
        """Update last_active_at to prevent GC."""
        self.last_active_at = datetime.now(timezone.utc)


# =============================================================================
# Runtime state held outside pydantic (non-serializable async primitives)
# =============================================================================


class WorkerRuntime:
    """
    Holds the actual asyncio.Task, asyncio.Event, and messages[] for a worker.
    Stored in SessionManager, not in the pydantic DebateSession model.
    """

    def __init__(self, alias: str):
        self.alias = alias
        self.task: Optional[asyncio.Task] = None
        self.wakeup_event: asyncio.Event = asyncio.Event()
        self.messages: list[dict[str, Any]] = []
        self.follow_up_prompt: Optional[str] = None
        self.follow_up_result: Optional[Any] = None
        self.shutdown_requested: bool = False

    def request_follow_up(self, prompt: str):
        """Signal the worker to process a follow-up."""
        self.follow_up_prompt = prompt
        self.wakeup_event.set()

    def request_shutdown(self):
        """Signal the worker to terminate."""
        self.shutdown_requested = True
        self.wakeup_event.set()
