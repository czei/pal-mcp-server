# Data Model: Multi-Model Agent Teams

**Phase 1 output for**: `/specs/001-multi-model-agent-teams/plan.md`
**Date**: 2026-03-22

## Entities

### DebateSession

A coordinated multi-model analysis instance. Transient (in-memory only).

| Field | Type | Description |
|-------|------|-------------|
| id | str (UUID) | Unique session identifier |
| task_type | str | Tool that initiated: "debug", "codereview", "planner", etc. |
| models | dict[str, ModelState] | Alias → per-model state (e.g., "analyst" → GPT state) |
| workers | dict[str, ModelWorker] | Alias → async worker coroutine reference |
| shared_context | SharedContext | Information common to all models |
| debate_config | DebateConfig | Configuration for this debate |
| round_barrier | asyncio.Barrier | Synchronization point for round completion |
| created_at | datetime | Session creation timestamp |
| last_active_at | datetime | Last interaction timestamp (for GC) |
| round | int | Current debate round (1 = independent, 2 = adversarial) |
| trace_id | str (UUID) | Unique trace ID for end-to-end correlation across rounds |
| status | SessionStatus | ACTIVE, SYNTHESIZING, COMPLETED, EXPIRED |

**Relationships**: Contains 1+ ModelState, 1+ ModelWorker (1:1 with ModelState), exactly 1 SharedContext, exactly 1 DebateConfig
**Validation**: id must be valid UUID; models must contain at least 1 entry; status transitions enforced (see state machine below)
**Lifecycle**: Created by debate orchestrator → active during debate → completed after synthesis → expired by GC after idle timeout

---

### ModelWorker

An async coroutine (`asyncio.Task`) that handles all interactions with one model
within a session. Maintains a growing `messages[]` array as the native multi-turn
conversation context — sent with every API call so the LLM sees coherent history.

| Field | Type | Description |
|-------|------|-------------|
| alias | str | Matches the alias in ModelState |
| task | asyncio.Task | The running async coroutine |
| wakeup_event | asyncio.Event | Signals follow-up requests (native async, no cross-thread issues) |
| current_phase | str or None | "round1", "round2", "follow_up", "idle", None |
| provider | ModelProvider | The provider instance this worker calls |
| messages | list[dict] | Growing messages array — the primary context. Sent with every API call. |
| model_state | ModelState | Metadata: pinned_facts, token counts, compression state |

**Relationships**: Belongs to exactly 1 DebateSession; holds exactly 1 ModelState
**Lifecycle**: asyncio.Task created on session start → runs Round 1 → awaits
barrier → runs Round 2 → awaits barrier → idles awaiting wakeup_event →
cancelled on session destroy/GC. Idle workers consume no OS resources.

**Worker coroutine** (async def):
```python
async def worker_loop(alias, provider, barrier, wakeup_event, messages):
    # Round 1
    messages.append({"role": "system", "content": tool_system_prompt})
    messages.append({"role": "user", "content": round1_prompt})
    response = await asyncio.to_thread(provider.generate_content, messages)
    messages.append({"role": "assistant", "content": response.content})
    await barrier.wait()  # sync: all workers finish Round 1

    # Round 2 (if max_rounds >= 2)
    messages.append({"role": "user", "content": round2_adversarial_prompt})
    response = await asyncio.to_thread(provider.generate_content, messages)
    messages.append({"role": "assistant", "content": response.content})
    await barrier.wait()  # sync: all workers finish Round 2

    # Idle — wait for follow-ups or shutdown
    while True:
        await wakeup_event.wait()
        wakeup_event.clear()
        if shutdown_requested:
            break
        # Follow-up
        messages.append({"role": "user", "content": follow_up_prompt})
        if should_compress(messages, model_state.compression_threshold):
            messages = compress_oldest(messages, model_state)
        response = await asyncio.to_thread(provider.generate_content, messages)
        messages.append({"role": "assistant", "content": response.content})
        signal_completion()
```

**Context window management**: The messages array grows with each exchange. When
token count approaches 70% of the model's context window, oldest messages are
compressed into a structured summary (pinned facts + working summary) that
replaces them. Recent exchanges stay verbatim. Compression is provider-aware
(Gemini compresses much later than GPT). See sessions/memory.py.

---

### ModelState

Per-model memory within a debate session. Each model maintains independent state.

| Field | Type | Description |
|-------|------|-------------|
| alias | str | Human-readable name (e.g., "analyst", "reviewer") |
| provider_name | str | Provider identifier (e.g., "google", "openai") |
| model_id | str | Specific model (e.g., "gemini-2.5-pro", "gpt-4o") |
| max_context | int | Provider-specific context limit in tokens |
| pinned_facts | list[PinnedFact] | Immutable facts — never compressed |
| working_summary | str | Compressed narrative of older exchanges |
| recent_exchanges | list[Exchange] | Last N verbatim exchanges (sliding window) |
| checkpoints | list[Checkpoint] | Named snapshots after synthesis points |
| total_exchange_count | int | Total exchanges including compressed ones |
| total_input_tokens | int | Cumulative input tokens sent to this model |
| total_output_tokens | int | Cumulative output tokens received |
| compression_threshold | float | Token count at which compression triggers (default: 0.7 * max_context) |

**Relationships**: Belongs to exactly 1 DebateSession; contains 0+ PinnedFacts, 0+ Exchanges, 0+ Checkpoints
**Validation**: alias must be unique within session; max_context sourced from ModelCapabilities; compression_threshold <= max_context

---

### SharedContext

Information common to all models in a debate session.

| Field | Type | Description |
|-------|------|-------------|
| original_prompt | str | The user/tool prompt that initiated the debate |
| code_files | list[Attachment] | Files included in the original request |
| round1_responses | dict[str, str] | Alias → full verbatim Round 1 response |
| gathered_artifacts | list[Attachment] | Files gathered from context_requests between rounds |
| task_specific_prompt | str | Tool-specific system prompt (from systemprompts/) |

**Relationships**: Belongs to exactly 1 DebateSession
**Validation**: original_prompt must not be empty; round1_responses populated after Round 1 completes

---

### Attachment

A file or artifact included in debate context.

| Field | Type | Description |
|-------|------|-------------|
| path | str | File path (as provided by caller) |
| content | str | File content (text) |
| token_count | int | Estimated token count of content |
| source | str | "original" (from request) or "gathered" (from context_requests) |

**Validation**: path must not be empty; content may be truncated if token_count exceeds budget

---

### PinnedFact

An immutable piece of information established during a session.

| Field | Type | Description |
|-------|------|-------------|
| id | str (UUID) | Unique identifier |
| content | str | The fact itself |
| source | str | Which model/round established this (e.g., "gpt-4o/round1") |
| category | PinnedFactCategory | HYPOTHESIS, DECISION, CONSTRAINT, FINDING |
| status | PinnedFactStatus | ACTIVE, CONFIRMED, REJECTED |
| created_at | datetime | When this fact was pinned |

**Relationships**: Belongs to exactly 1 ModelState
**Validation**: content must not be empty; status transitions: ACTIVE → CONFIRMED or ACTIVE → REJECTED (no reversal)

**State Transitions**:
```
ACTIVE ──→ CONFIRMED  (validated by debate or user)
ACTIVE ──→ REJECTED   (disproven by debate or user)
```

---

### Exchange

A single request-response pair with a model.

| Field | Type | Description |
|-------|------|-------------|
| round | int | Debate round (1, 2, or follow-up number) |
| role | str | "user" (prompt sent to model) or "assistant" (model response) |
| content | str | Full verbatim content |
| timestamp | datetime | When this exchange occurred |
| token_count | int | Estimated tokens in this exchange |
| context_requests | list[ContextRequest] | Structured requests for additional files (Round 1 only) |

**Relationships**: Belongs to exactly 1 ModelState (in recent_exchanges list)
**Validation**: round >= 1; role must be "user" or "assistant"

---

### ContextRequest

A structured request from a model for additional information.

| Field | Type | Description |
|-------|------|-------------|
| artifact_type | str | "file", "function", "class", "test", "config", "log" |
| path | str | Requested file/artifact path |
| rationale | str | Why the model wants this (for orchestrator decision-making) |
| priority | str | "high", "medium", "low" |
| requested_by | str | Model alias that requested this |

**Relationships**: Belongs to exactly 1 Exchange
**Validation**: path must not be empty; priority must be one of the three values

---

### Checkpoint

A named snapshot of model state at a specific point.

| Field | Type | Description |
|-------|------|-------------|
| name | str | Human-readable checkpoint name (e.g., "post-round2", "pre-implementation") |
| created_at | datetime | Snapshot timestamp |
| pinned_facts_snapshot | list[PinnedFact] | Copy of pinned facts at checkpoint time |
| working_summary_snapshot | str | Copy of working summary at checkpoint time |
| exchange_count | int | Number of exchanges at checkpoint time |

**Relationships**: Belongs to exactly 1 ModelState
**Validation**: name must be unique within a model's checkpoints

---

### DebateConfig

Configuration for a specific debate session.

| Field | Type | Description |
|-------|------|-------------|
| max_round | int | Maximum debate round (default: 2). Set to 1 for Round 1 only (Config B). |
| enable_context_requests | bool | Whether to parse context_requests from Round 1 (default: true). False disables context acquisition (Config C vs D). |
| synthesis_mode | str | "synthesize" (default: merge perspectives) or "select_best" (score and pick winner). Config B uses "select_best". |
| synthesis_model | str or None | Model to use for synthesis (default: non-participant, then strongest available) |
| summary_strategy | str | "llm" or "template" (default: "llm") |
| per_model_timeout_ms | int | Timeout per model per round (default: 30000) |
| escalation_mode | str | "adaptive" (default), "always_full", or "never". Per-call override. Config E uses "adaptive". |
| escalation_confidence_threshold | float or None | Per-call override (0.0–1.0). None = use global default. |
| escalation_complexity_threshold | str or None | Per-call override ("low"/"medium"/"high"). None = use global default. |

**Relationships**: Belongs to exactly 1 DebateSession
**Validation**: max_round >= 1; per_model_timeout_ms > 0; synthesis_mode must be "synthesize" or "select_best"; escalation_mode must be "adaptive", "always_full", or "never"; escalation_confidence_threshold 0.0–1.0 if set

**Ablation config mapping:**
- **A**: `debate_mode=false` (no DebateConfig created)
- **B**: `max_round=1, synthesis_mode="select_best"`
- **C**: `max_round=2, enable_context_requests=false`
- **D**: `max_round=2, enable_context_requests=true` (default)
- **E**: Config D for design + `escalation_mode="adaptive"` for implementation

---

### EvaluationRecord

A structured log entry for one model interaction. Persisted to JSONL on disk.

| Field | Type | Description |
|-------|------|-------------|
| timestamp | str (ISO 8601) | When the interaction occurred |
| event | str | Event type: "model_response", "debate_round", "synthesis", "follow_up" |
| session_id | str | Session that produced this record |
| trace_id | str (UUID) | End-to-end trace ID for correlating across rounds |
| alias | str | Model alias within the session |
| model | str | Model identifier (e.g., "gpt-4o") |
| provider | str | Provider name (e.g., "openai") |
| task_type | str | Tool/task that initiated (e.g., "debug", "codereview") |
| round | int | Debate round number |
| input_tokens | int | Tokens sent to model |
| output_tokens | int | Tokens received from model |
| latency_ms | int | Response time in milliseconds |
| status | str | "success", "timeout", "error", "rate_limited" |
| is_follow_up | bool | Whether this was a follow-up to an existing session |
| exchange_number | int | Exchange count within this session |
| context_requests_count | int | Number of context_requests returned |
| error_message | str or None | Error details if status != "success" |

**Relationships**: References a DebateSession by session_id (but persists independently)
**Validation**: timestamp must be ISO 8601; status must be one of the four values
**Storage**: Appended to `logs/evaluation.jsonl` — never deleted by session GC

---

### EscalationSignal

Structured confidence/escalation output from single-model reviews (FR-021).
Enables adaptive review intensity — the system auto-promotes to full multi-model
debate when the signal indicates the review needs more diverse perspectives.

| Field | Type | Description |
|-------|------|-------------|
| confidence | float (0.0–1.0) | Reviewer's confidence in the completeness of its analysis |
| complexity | str | "low", "medium", "high" — assessed complexity of the reviewed code |
| anomalies_detected | bool | Whether the reviewer found issues it cannot fully resolve alone |
| escalation_recommended | bool | Whether the reviewer recommends promoting to full debate |
| escalation_reason | str or None | Human-readable explanation of why escalation is recommended |
| risk_areas | list[str] | Tags for risk areas detected (e.g., "concurrency", "auth", "parsing") |

**Relationships**: Returned as part of single-model tool responses; not persisted
separately (captured within EvaluationRecord metadata)
**Validation**: confidence must be 0.0–1.0; complexity must be one of the three values;
if escalation_recommended is true, escalation_reason must not be empty

**Escalation triggers** (configurable thresholds):
- `confidence < ESCALATION_CONFIDENCE_THRESHOLD` (default: 0.6)
- `complexity >= ESCALATION_COMPLEXITY_THRESHOLD` (default: "high")
- `anomalies_detected == true`
- `risk_areas` intersects `ESCALATION_AUTO_RISK_AREAS` (default: concurrency, auth, persistence, parsing)

---

### SessionStatus (Enum)

```
ACTIVE         → Session is open and accepting interactions
SYNTHESIZING   → Round 2 complete, synthesis in progress
COMPLETED      → Debate finished, session available for follow-ups
EXPIRED        → Session garbage collected after idle timeout
```

**State Transitions**:
```
ACTIVE ──→ SYNTHESIZING  (all Round 2 responses received)
SYNTHESIZING ──→ COMPLETED  (synthesis generated)
COMPLETED ──→ ACTIVE  (follow-up received — re-activates)
ACTIVE ──→ EXPIRED  (idle timeout exceeded)
COMPLETED ──→ EXPIRED  (idle timeout exceeded)
```

---

### DebateResult

Output of a completed debate (returned to the calling tool).

| Field | Type | Description |
|-------|------|-------------|
| session_id | str | Session identifier for follow-ups |
| responses | list[ModelDebateResponse] | Per-model responses (Round 1 + Round 2 if applicable) |
| context_requests | list[ContextRequest] | Deduplicated context requests from all models |
| synthesis | SynthesisResult or None | Cross-model synthesis (if debate completed) |
| warnings | list[DebateWarning] | Warnings about partial failures |
| participation | str | "3/3", "2/3 — Google: timeout", etc. |
| round2_participation | str | "3/3", "2/3 — Gemini: timeout", etc. (may differ from Round 1) |
| trace_id | str (UUID) | End-to-end trace ID for this debate |

---

### ModelDebateResponse

One model's contribution to the debate.

| Field | Type | Description |
|-------|------|-------------|
| alias | str | Model alias |
| model | str | Model identifier |
| provider | str | Provider name |
| round1_content | str | Independent analysis (Round 1) |
| round2_content | str or None | Adversarial critique (Round 2, if debate ran) |
| latency_ms | int | Total response time across rounds |
| tokens | dict | {"input": int, "output": int} total across rounds |
| status | str | "success", "partial" (Round 1 only), "failed" |

---

### SynthesisResult

Output of cross-model response synthesis. Structure varies by synthesis_mode.

| Field | Type | Description |
|-------|------|-------------|
| mode | str | "synthesize" or "select_best" |
| synthesis | str | Unified analysis text (synthesize mode) or winning response text (select_best mode) |
| agreement_points | list[str] | Points where all models agreed (synthesize mode only) |
| disagreement_points | list[str] | Points where models disagreed (synthesize mode only) |
| recommendations | list[str] | Consolidated recommendations (synthesize mode only) |
| scores | dict[str, SelectionScore] or None | Alias → score (select_best mode only) |
| selected_alias | str or None | Winning model alias (select_best mode only) |
| selection_rationale | str or None | Why this response scored highest (select_best mode only) |
| synthesizer_model | str | Model used for synthesis/selection |

### SelectionScore

Per-model score in select_best mode.

| Field | Type | Description |
|-------|------|-------------|
| alias | str | Model alias |
| score | float | 1-10 score against task objective |
| rationale | str | Brief explanation of score |

---

---

## Error Types

Defined in `debate/errors.py`, extending `ToolExecutionError`:

| Error Class | Trigger | Key Fields |
|-------------|---------|------------|
| `ProviderUnavailableError` | API key missing, network down, circuit open | provider, reason |
| `ProviderRateLimitError` | Rate limit exceeded | provider, retry_after_ms |
| `ProviderTimeoutError` | Exceeded per_model_timeout_ms | provider, timeout_ms |
| `ProviderContentFilterError` | Model refused prompt | provider, filter_reason |
| `SessionNotFoundError` | Invalid or expired session_id | session_id |
| `AliasNotFoundError` | Alias not in session | session_id, alias |
| `ConfigurationError` | Invalid config at startup | field, reason |

---

## Entity Relationship Diagram

```
DebateSession (1) ──→ (1) SharedContext
                 ──→ (1) DebateConfig
                 ──→ (1+) ModelWorker ──→ (1) ModelState ──→ (0+) PinnedFact
                                                         ──→ (0+) Exchange ──→ (0+) ContextRequest
                                                         ──→ (0+) Checkpoint

DebateSession ──produces──→ (0+) EvaluationRecord (persisted to disk)
DebateSession ──produces──→ (1) DebateResult ──→ (1+) ModelDebateResponse
                                              ──→ (0-1) SynthesisResult
```
