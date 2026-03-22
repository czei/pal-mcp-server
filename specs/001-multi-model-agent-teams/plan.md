# Implementation Plan: Multi-Model Agent Teams

**Branch**: `001-multi-model-agent-teams` | **Date**: 2026-03-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-multi-model-agent-teams/spec.md`

## Summary

Fork the PAL/Zen MCP server to add adversarial multi-model debate as the default
operating mode for all decision-making tools. The fork inherits ~16,500 lines of
existing prompt engineering, provider abstractions (7+ providers, 111+ models),
and MCP infrastructure. New capabilities added: session management with stratified
memory, two-round debate orchestration (independent analysis → adversarial critique),
structured context requests between rounds, evaluation logging (JSONL), and
stateful follow-up conversations. The fork runs as a separate MCP server alongside
or replacing the original PAL/Zen.

## Technical Context

**Language/Version**: Python 3.12 — inherited from PAL/Zen upstream (minimum 3.11 required for asyncio.Barrier)
**Primary Dependencies**: mcp (MCP SDK), pydantic, google-generativeai, openai,
anthropic, httpx, tiktoken — all inherited from PAL/Zen `requirements.txt`
**Storage**: In-memory sessions (transient); JSONL files on disk for evaluation
logs (persistent)
**Testing**: pytest (unit tests in `tests/`), communication_simulator_test.py
(end-to-end), `code_quality_checks.sh` (ruff, black, isort)
**Target Platform**: macOS/Linux — local child process via stdio, Claude Code MCP
**Project Type**: MCP server (stdio transport, tool-based API)
**Performance Goals**: Complete two-round debate (Round 1 + context gathering +
Round 2) within 25 seconds wall-clock time under normal conditions (SC-003)
**Constraints**: Must not break existing tool behavior when running in single-model
mode; must handle partial provider failures gracefully; session memory bounded by
per-model context window limits (128K–1M tokens)
**Scale/Scope**: 3+ concurrent LLM providers, up to 20 concurrent sessions,
3-hour session TTL, ~4 new modules + modifications to existing tool base classes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Cognitive Diversity Through Model Variety | PASS | Core feature — multi-model debate is the primary deliverable |
| II | Adaptive Review Intensity | PASS | Adaptive escalation with confidence signals is User Story 5 (P3); FR-021 requires structured escalation from per-stage reviews; architecture supports full debate, adaptive review, and light checks |
| III | Fork and Extend, Don't Rebuild | PASS | Fork inherits all existing tools, prompts, and providers; adds session/evaluation/debate modules only |
| IV | Asymmetric Architecture | PASS | Non-Claude models remain text-only advisors; fork does not read files from disk; calling agent gathers context |
| V | Evaluation From Day One | PASS | JSONL evaluation logging is a core deliverable (FR-009, FR-010, User Story 6) |
| VI | Provider Abstraction | PASS | Inherits existing `ModelProvider` ABC; extends with per-provider rate limiting and circuit breakers |
| VII | Quality Gates | PASS | All existing quality infrastructure inherited; new code must pass same gates |

**Pre-Phase 0 Gate: PASSED** — No violations. Proceeding to research.

## Project Structure

### Documentation (this feature)

```text
specs/001-multi-model-agent-teams/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── mcp-tools.md     # MCP tool schemas (the fork's external interface)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
# Inherited structure (existing PAL/Zen — preserved as-is)
server.py                           # MCP server entry point (modified: debate mode routing)
config.py                           # Configuration (modified: debate/session settings)
providers/
├── base.py                         # ModelProvider ABC (unchanged)
├── registry.py                     # ModelProviderRegistry (unchanged)
├── gemini.py                       # Gemini provider (unchanged)
├── openai.py                       # OpenAI provider (unchanged)
├── shared/
│   ├── model_capabilities.py       # ModelCapabilities (unchanged)
│   └── model_response.py           # ModelResponse (unchanged)
└── ...                             # All other providers (unchanged)
tools/
├── shared/
│   ├── base_tool.py                # BaseTool ABC (modified: debate mode routing, escalation)
│   └── base_models.py              # DebateCapableRequest mixin added (ToolRequest unchanged)
├── simple/base.py                  # SimpleTool (modified: debate orchestration)
├── workflow/
│   ├── base.py                     # WorkflowTool (modified: debate orchestration)
│   └── workflow_mixin.py           # BaseWorkflowMixin (modified: debate orchestration)
├── consensus.py                    # ConsensusTool (reference: already multi-model)
├── chat.py, debug.py, ...          # All existing tools (unchanged tool logic)
└── models.py                       # Tool models (modified: debate output types)
systemprompts/                      # All existing prompts (unchanged)
utils/
├── conversation_memory.py          # Existing conversation threading (unchanged)
└── ...                             # Other utils (unchanged)

# New modules (additions for multi-model debate)
debate/
├── __init__.py
├── orchestrator.py                 # DebateOrchestrator — Round 1/2 coordination
├── context_requests.py             # Parse & deduplicate model context requests
└── synthesis.py                    # Cross-model response synthesis

sessions/
├── __init__.py
├── types.py                        # DebateSession, ModelState, SharedContext,
│                                   # PinnedFact, Exchange, Checkpoint
├── manager.py                      # SessionManager — create/get/destroy/gc
├── memory.py                       # Stratified memory — compression, sliding window
└── store.py                        # InMemorySessionStore (dict-based)

evaluation/
├── __init__.py
├── logger.py                       # JSONL structured event logging
├── metrics.py                      # Token counting, latency, quality signals
└── reporter.py                     # Aggregation queries for compare_models

resilience/
├── __init__.py
├── rate_limiter.py                 # Per-provider token bucket rate limiter
└── circuit_breaker.py              # Provider health tracking + auto-disable

tools/
├── follow_up.py                    # NEW: Stateful follow-up tool
├── compare_models.py               # NEW: Evaluation query tool
├── list_sessions.py                # NEW: Session inventory tool
└── destroy_session.py              # NEW: Session cleanup tool

tests/
├── test_debate_orchestrator.py     # Debate orchestration unit tests
├── test_session_manager.py         # Session lifecycle unit tests
├── test_session_memory.py          # Stratified memory + compression tests
├── test_evaluation_logger.py       # JSONL logging unit tests
├── test_evaluation_reporter.py     # Aggregation query unit tests
├── test_rate_limiter.py            # Rate limiting unit tests
├── test_circuit_breaker.py         # Circuit breaker unit tests
├── test_context_requests.py        # Context request parsing unit tests
└── test_synthesis.py               # Synthesis unit tests
```

**Structure Decision**: Extends the existing single-project PAL/Zen layout. New
code lives in four new top-level packages (`debate/`, `sessions/`, `evaluation/`,
`resilience/`) plus four new tools in the existing `tools/` directory. This
follows the fork-and-extend principle — inherited code stays in place, new
capabilities are additive. No restructuring of existing directories.

## Complexity Tracking

| Area | Why Non-Trivial | Mitigation |
|------|-----------------|------------|
| Session memory + compression | Stratified memory with per-provider compression thresholds, LLM-assisted summarization with drift prevention, and pinned fact immutability | Deterministic template fallback; structured field updates only; comprehensive unit tests for compression pipeline |
| Async migration | Existing provider calls are synchronous; debate orchestrator requires parallel fan-out via asyncio.gather() | Wrap existing synchronous providers with async adapters; test both sync (single-model) and async (debate) paths |
| Concurrent session access | Multiple teammates may follow-up on the same session simultaneously | Serialize writes per session (asyncio.Lock per session_id); concurrent reads are safe |
| Cross-model transcript security | Round 1 responses shared in Round 2 could contain adversarial content | Frame all shared responses as claims to evaluate, not trusted input; synthesis cross-references against source code |

## Architectural Gaps Identified (Post-Review)

The following gaps were identified during multi-model review (GPT-5.4, Gemini 2.5
Pro, Claude Opus 4.6 — unanimous findings at 8/10 confidence):

### Concurrency Model

The shared in-memory session store requires explicit concurrency control:
- **Per-session asyncio.Lock** for write operations (follow_up, state mutations)
- **Read-safe**: get_session, list_sessions are concurrent-safe (dict reads)
- **Session GC**: runs on a background timer, acquires lock before expiring sessions
- **Default idle timeout**: 60 minutes (configurable via `SESSION_GC_IDLE_MINUTES`)

### Async / Worker Architecture

**Requires Python 3.11+** (`asyncio.Barrier` introduced in 3.11; project uses 3.12).

The server is already async (`asyncio.run(main())`, async `handle_call_tool()`).
Existing providers use synchronous `generate_content()` which blocks the event
loop — acceptable for single-model (one call at a time) but not for debate.

**Approach: Async worker coroutines with native messages array context**
(see research.md R-011)
- Workers are **`asyncio.Task` coroutines**, not OS threads
- Each worker holds a growing `messages[]` array as its primary context — the
  native multi-turn format every provider API supports. The LLM sees a coherent
  conversation because the full history is sent with every call.
- Blocking `provider.generate_content()` offloaded via `asyncio.to_thread()` to
  a shared `ThreadPoolExecutor` — borrows a thread only for API call duration
- Orchestrator coordinates via `asyncio.Barrier` (round sync) and
  `asyncio.Event` (follow-up wakeup per worker) — native async, no cross-thread issues
- Single-model path: unchanged (synchronous, no overhead)
- Thread pool: `ThreadPoolExecutor(max_workers=SESSION_MAX_CONCURRENT * 3 + 10)`
  — handles burst concurrency across sessions; threads are SHORT-LIVED (API call only)
- Worker lifecycle: `asyncio.Task` created on session creation, cancelled on destroy/GC
- Idle workers cost nothing — suspended coroutines awaiting events
- Context compression: only triggers when messages[] approaches 70% of model's
  context window; typical 2-round debates never need compression

### Observability Beyond JSONL

JSONL evaluation logs (FR-009) cover model performance metrics. Additional
observability needed:
- **Trace ID**: unique per debate, propagated through Round 1 → context gathering
  → Round 2 → synthesis for end-to-end correlation
- **Per-round timing**: separate latency tracking for Round 1, context gathering,
  Round 2, and synthesis phases
- **Failure causality**: when a provider fails, log whether it was timeout, rate
  limit, circuit breaker, or content filter — not just "error"

### Security: Cross-Model Transcript Sharing

When Round 1 responses are shared with all models in Round 2:
- **Risk**: a model's Round 1 response could contain prompt injection attempts
  that influence other models' Round 2 analysis
- **Mitigation**: Round 2 prompts MUST frame all Round 1 responses as "claims by
  other analysts to critically evaluate" — not as trusted instructions
- **Mitigation**: synthesis step cross-references all claims against provided
  source code and flags unsupported assertions

### Tool-by-Tool Compatibility

Modifying `BaseTool` to support debate mode affects all 19 existing tools. Risk:
tool-specific assumptions about single-model response format may break.
- **Required**: explicit compatibility test for each major tool (debug, codereview,
  planner, consensus, thinkdeep, analyze) verifying both single-model and debate
  mode produce valid output
- **Approach**: existing simulator tests extended with debate-mode variants

### Round 2 Prompt Composition

The existing `systemprompts/` contain sophisticated per-tool prompt engineering.
Round 2 must compose with these, not replace them:
- **System prompt**: Same per-tool system prompt as Round 1 (unchanged)
- **User prompt**: Template in `debate/prompts.py` that wraps Round 1 responses
  as "claims by other analysts" with alias labels (not model names — avoids bias)
- **Suppression**: Round 2 instructs models NOT to output CONTEXT_REQUESTS or
  ESCALATION_SIGNAL blocks
- **Variable participants**: Template handles 2/3 partial failures gracefully
- See research.md R-012 for full design

### Synthesis Model Selection

The model that synthesizes the debate affects the outcome:
- **Default**: Use a model NOT in the Round 1 roster when possible (avoids bias)
- **Fallback**: Highest-capability available model if all participated
- **Configurable**: `DEBATE_SYNTHESIS_MODEL` env var for explicit override
- **Single-response case**: If only 1 model responded (no debate), skip synthesis
  — return the single response directly with a warning

### Config Validation

T002 adds ~18 env vars. Validation required at startup:
- Type checking (numeric thresholds, boolean flags, comma-separated model lists)
- Range validation (confidence thresholds 0.0–1.0, timeout > 0)
- Cross-field validation (`DEBATE_DEFAULT_ENABLED=true` requires ≥2 models)
- Model availability check (`DEBATE_DEFAULT_MODELS` references configured models)
- Graceful defaults with warnings (not crashes) for missing optional config

### Schema Injection Strategy

Debate fields (`debate_mode`, `debate_models`, `session_id`, `debate_max_rounds`)
must appear only on applicable tools, not globally:
- **Applicable**: debug, codereview, planner, thinkdeep, analyze, secaudit,
  docgen, refactor, tracer, testgen, precommit, consensus (12 tools)
- **Excluded**: chat, clink, apilookup, listmodels, version, challenge (7 tools)
- **Approach**: Do NOT add to `ToolRequest` globally. Instead, create a
  `DebateCapableRequest` mixin that applicable tools inherit alongside
  `ToolRequest`. Schema builders pick up debate fields only for those tools.
- **Risk mitigation**: Schema verification immediately after implementation

### Error Types

Contracts define 7 error types. These must be created as classes:
- `ProviderUnavailableError` — API key missing, network down, circuit open
- `ProviderRateLimitError` — rate limit hit, includes retry_after_ms
- `ProviderTimeoutError` — exceeded per_model_timeout_ms
- `ProviderContentFilterError` — model refused prompt
- `SessionNotFoundError` — invalid or expired session_id
- `ConfigurationError` — invalid configuration
- Location: `debate/errors.py`, extending existing `ToolExecutionError`

### Response Serialization

When `debate_mode=true`, tool output includes `debate_metadata`. The existing
serialization path must accommodate this:
- `SimpleTool._parse_response()` — must wrap debate results into `ToolOutput`
- `workflow_mixin.store_conversation_turn()` — must store debate metadata in
  conversation memory for continuation_id threading
- `ToolOutput` in `tools/models.py` — needs optional `debate_metadata` field

### Session / Continuation ID Coexistence

Two parallel state systems:
- `continuation_id` (existing): Claude-side conversation memory in
  `utils/conversation_memory.py` — flat turn log (user/assistant pairs)
- `session_id` (new): Model-side debate state in `sessions/` — stratified
  per-model memory with compression

They are **separate systems** that reference each other:
- A debate tool call creates both: a new debate session (session_id) AND
  appends to the continuation_id thread (if one exists)
- `follow_up` uses session_id for model context AND continuation_id for
  Claude-side context
- Destroying a session does NOT destroy the continuation thread (and vice versa)

### Feature Flag / Rollback

`DEBATE_DEFAULT_ENABLED=false` controls the default but doesn't prevent schema
changes. Additional safety:
- `DEBATE_FEATURE_ENABLED=true` — master switch. When `false`, debate code
  paths are completely disabled, debate fields are excluded from schemas,
  and all tools behave exactly as upstream PAL/Zen
- This enables safe deployment: push the code, set flag to false, verify no
  regressions, then enable
