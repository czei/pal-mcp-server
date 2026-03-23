# Tasks: Multi-Model Agent Teams

**Input**: Design documents from `/specs/001-multi-model-agent-teams/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Fork initialization, package structure, configuration, safety mechanisms

- [x] T001 Create new package directories with __init__.py: debate/, sessions/, evaluation/, resilience/
- [x] T002 Add debate-specific configuration variables to config.py: DEBATE_FEATURE_ENABLED (master kill switch), DEBATE_DEFAULT_ENABLED, DEBATE_DEFAULT_MODELS, DEBATE_MAX_ROUNDS, DEBATE_PER_MODEL_TIMEOUT_MS, DEBATE_SUMMARY_STRATEGY, DEBATE_SYNTHESIS_MODEL, SESSION_GC_IDLE_MINUTES, SESSION_MAX_CONCURRENT, SESSION_MAX_RECENT_EXCHANGES, EVALUATION_LOG_DIR, EVALUATION_RETENTION_DAYS, RATE_LIMIT_RPM_OPENAI, RATE_LIMIT_RPM_GOOGLE, RATE_LIMIT_RPM_OPENROUTER, CIRCUIT_BREAKER_FAILURE_THRESHOLD, CIRCUIT_BREAKER_RESET_TIMEOUT_MS, ESCALATION_CONFIDENCE_THRESHOLD, ESCALATION_COMPLEXITY_THRESHOLD, ESCALATION_AUTO_RISK_AREAS — use env var names matching actual PAL/Zen conventions (GEMINI_API_KEY not GOOGLE_AI_API_KEY)
- [x] T003 Implement config validation in config.py: type checking (numeric thresholds, booleans, comma-separated lists), range validation (confidence 0.0–1.0, timeouts > 0), cross-field checks (DEBATE_DEFAULT_ENABLED=true requires ≥2 models in DEBATE_DEFAULT_MODELS that are available), model availability cross-check against configured providers, fail-fast with clear errors on invalid required config, graceful defaults with warnings for optional config
- [x] T004 [P] Create error type classes in debate/errors.py: ProviderUnavailableError, ProviderRateLimitError (with retry_after_ms), ProviderTimeoutError, ProviderContentFilterError, SessionNotFoundError, AliasNotFoundError, ConfigurationError — all extending existing ToolExecutionError from tools/shared/exceptions.py
- [x] T005 [P] Add Apache 2.0 attribution: verify NOTICE file, add license headers to new files, add credit to README.md per FR-019

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T006 Create session data types in sessions/types.py: DebateSession (with trace_id, round_barrier, workers dict), ModelState, ModelWorker (with thread ref, wakeup_event, current_task), SharedContext, Attachment, PinnedFact (with PinnedFactCategory, PinnedFactStatus enums), Exchange, ContextRequest, Checkpoint, DebateConfig, SessionStatus enum with state transitions, EscalationSignal — all as pydantic BaseModels per data-model.md
- [x] T007 [P] Create InMemorySessionStore in sessions/store.py: dict-based storage keyed by session_id, get/set/delete/list operations, per-session asyncio.Lock for write serialization (FR-022), concurrent reads safe without lock
- [x] T008 [P] Create token bucket rate limiter in resilience/rate_limiter.py: per-provider bucket with configurable RPM, async acquire() that queues when empty with max wait, immediate ProviderRateLimitError when max wait exceeded
- [x] T009 [P] Create circuit breaker in resilience/circuit_breaker.py: per-provider failure tracking, configurable failure_threshold and reset_timeout_ms, states CLOSED/OPEN/HALF_OPEN, probe on half-open, ProviderUnavailableError when circuit open
- [x] T010 Create SessionManager in sessions/manager.py: create_session() returning UUID + spawning async worker coroutines (asyncio.Task per model), get_session(), destroy_session() that cancels worker tasks and preserves eval data, background GC timer with configurable idle timeout (default 60min). Configure custom ThreadPoolExecutor(max_workers=SESSION_MAX_CONCURRENT * 3 + 10) for blocking provider.generate_content() calls only (not for worker lifetime). Wire GC startup/shutdown into server lifecycle.
- [x] T011 Create DebateCapableRequest mixin in tools/shared/base_models.py: debate_mode (bool, default false), debate_models (list of {alias, model, temperature?}), session_id (str, optional), debate_max_rounds (int, default 2), synthesis_mode (str, "synthesize"/"select_best", default "synthesize"), enable_context_requests (bool, default true), escalation_mode (str, "adaptive"/"always_full"/"never", default "adaptive"), escalation_confidence_threshold (float, optional per-call override), escalation_complexity_threshold (str, optional per-call override). Applicable tools inherit this mixin alongside ToolRequest. Do NOT add these fields to ToolRequest itself — they must only appear on applicable tools per FR-026.
- [x] T012 Verify tool schema generation: immediately after T011, confirm that debate fields appear ONLY on applicable tools (debug, codereview, planner, thinkdeep, analyze, secaudit, docgen, refactor, tracer, testgen, precommit, consensus) and NOT on excluded tools (chat, clink, apilookup, listmodels, version, challenge). Run schema snapshot comparison. Fix SchemaBuilder/WorkflowSchemaBuilder if needed.
- [x] T013 Add debate output types to tools/models.py: DebateResult (session_id, trace_id, responses, context_requests, synthesis, warnings, participation, round2_participation), ModelDebateResponse, SynthesisResult. Add optional debate_metadata field to ToolOutput for debate responses.
- [x] T014 Implement async worker coroutine in debate/orchestrator.py: worker_loop() is an async def that maintains a growing messages[] array as the native multi-turn conversation context. Each API call sends the full messages array so the LLM sees coherent history. Blocking provider.generate_content() offloaded via asyncio.to_thread(). Worker coordinates with orchestrator via asyncio.Barrier (round sync) and asyncio.Event (follow-up wakeup) — all native async, no cross-thread issues. Worker is an asyncio.Task: created on session start, cancelled on destroy/GC. Idle workers consume no OS resources. See data-model.md ModelWorker entity and research.md R-011.
- [x] T015 Implement DebateOrchestrator coordinator in debate/orchestrator.py: create_debate() spawns persistent workers (one per model) and creates session, run_round1() signals all workers via barrier and waits for completion, run_round2() distributes Round 1 responses then signals workers via barrier. Handles partial failures per round (FR-011: min 2 for Round 2; FR-024: Round 2 proceeds with available critiques + Round 1 fallback for failed models).
- [x] T016 Design and implement Round 2 adversarial prompt template in debate/prompts.py: build_round2_prompt() composes original tool system prompt (unchanged) with user prompt containing Round 1 responses labeled by alias (not model name — avoids bias), framed as "claims by other analysts to critically evaluate" (FR-023). Handles variable participant count (2/3 partial failures). Explicitly suppresses CONTEXT_REQUESTS and ESCALATION_SIGNAL carryover from Round 1. See research.md R-012.
- [x] T017 Implement synthesis in debate/synthesis.py with two modes: (a) synthesize() — merge all perspectives into unified analysis with agreement_points, disagreement_points, recommendations (default mode); (b) select_best() — prompt synthesis model to score each response 1-10 against task objective, return highest-scoring as primary output with all scores and rationale. select_synthesis_model() chooses model NOT in Round 1 roster when possible (avoids bias), falls back to highest-capability, overrideable via DEBATE_SYNTHESIS_MODEL config or per-call synthesis_model param. Mode selected by DebateConfig.synthesis_mode.
- [x] T018 Modify tools/simple/base.py: in execute() method (line ~444, before provider.generate_content()), check debate_mode — if true AND DEBATE_FEATURE_ENABLED, route through DebateOrchestrator; if false, existing path completely unchanged. Insertion point MUST be after prompt preparation to preserve existing prompt engineering. Add debate_metadata to response serialization path in _parse_response().
- [x] T019 Modify tools/workflow/workflow_mixin.py: in _call_expert_analysis() (line ~1437), check debate_mode — if true, route through DebateOrchestrator with accumulated workflow state (consolidated_findings, work_history). Also handle tools where requires_expert_analysis() is False — ensure debate mode can still be triggered via the main execute_workflow() path.
- [x] T020 Implement DEBATE_FEATURE_ENABLED master kill switch: when false, debate fields excluded from all schemas (DebateCapableRequest mixin not applied), debate code paths never entered, fork behaves as vanilla PAL/Zen. Wire into server.py tool registration and schema generation.
- [x] T021 Register debate infrastructure in server.py: initialize SessionManager with thread pool, wire rate limiters and circuit breakers per configured provider, start GC background timer, register shutdown hooks for clean worker termination, ensure new tools will be discoverable
- [x] T022 Define session/continuation_id coexistence in tools/shared/base_tool.py: debate tool calls create/append to continuation_id thread (for Claude-side memory) AND create debate session (for model-side memory). follow_up tool uses session_id for model context AND continuation_id for Claude-side context. Both IDs returned in responses. Destroying session does NOT destroy continuation thread.

**Checkpoint**: Foundation ready — all base classes modified, session/worker infrastructure operational, resilience layer active, schemas verified, kill switch tested. User story implementation can now begin.

---

## Phase 3: User Story 1 & 2 — Multi-Model Debugging & Design Review (Priority: P1) MVP

**Goal**: Enable multi-model debate on any existing tool via debate_mode=true. Three async worker coroutines analyze the same problem independently (Round 1), each maintaining its own messages[] context, then argue about each other's findings (Round 2). A synthesis presents agreement, disagreement, and consolidated recommendations.

**Independent Test**: Call `debug(debate_mode=true, prompt="...", debate_models=[...])` and verify three models respond independently via persistent workers, then critique each other using the Round 2 prompt template, and a synthesis is produced by a non-participant model.

### Implementation for User Stories 1 & 2

- [x] T023 [US1] Implement full debate flow in debate/orchestrator.py: run_debate() creates session with async worker coroutines → signals Round 1 via barrier → waits for all workers → collects responses → populates SharedContext.round1_responses → signals Round 2 via barrier → waits → runs synthesis → returns DebateResult with session_id, trace_id, participation, round2_participation, all responses, and synthesis. NOTE: In MVP (no Phase 5), Round 2 fires immediately after Round 1 with no context enrichment pause — enable_context_requests is effectively ignored until Phase 5 implements the pause-gather-resume flow.
- [x] T024 [US1] Add participation reporting to debate result: format Round 1 as "3/3" or "2/3 — Google: timeout" and Round 2 separately (may differ), include in DebateResult.participation, DebateResult.round2_participation, and DebateResult.warnings
- [x] T025 [US1] Add trace_id (UUID) generation to debate orchestrator, propagate through all rounds, include in all evaluation log entries for end-to-end correlation; add per-round timing (round1_ms, round2_ms, synthesis_ms) to DebateResult
- [x] T026 [US1] Wire debug tool to debate orchestrator — verify debate_mode=true produces multi-model debug output with 3 independent analyses + adversarial critique + synthesis
- [x] T027 [P] [US2] Verify codereview tool works with debate_mode=true: call codereview with debate_mode and 2+ models, confirm Round 1 produces independent reviews, Round 2 produces adversarial critique, synthesis identifies agreement/disagreement on code quality issues
- [x] T028 [P] [US2] Verify planner tool works with debate_mode=true: call planner with debate_mode and 2+ models, confirm models propose independent plans in Round 1 and critique each other's plans in Round 2
- [x] T029 [US1] Implement retry semantics for debate path in debate/orchestrator.py: per-worker retry with backoff on transient failures (timeout, rate limit), respecting circuit breaker state, max retries configurable — mirrors existing SimpleTool retry logic

**Checkpoint**: Core multi-model debate operational via persistent workers. Any applicable tool with debate_mode=true runs parallel analysis + adversarial debate + synthesis. US1 and US2 fully functional.

---

## Phase 4: User Story 3 — Stateful Follow-Up Conversations (Priority: P2)

**Goal**: After an initial debate, persistent workers retain context across follow-up exchanges via stratified per-model state (pinned facts, working summary, recent verbatim, checkpoints). Workers are woken via events for follow-ups.

**Independent Test**: Run a debate, get session_id, call follow_up with a question that references the debate topic, verify the model's response references its prior analysis without re-feeding it.

### Implementation for User Story 3

- [x] T030 [US3] Implement stratified memory layer in sessions/memory.py: build_context_for_model() constructs the message array from ModelState (held locally in worker) — [system prompt] + [pinned facts] + [working summary] + [recent verbatim exchanges] + [shared context] + [new prompt], respecting token budget
- [x] T031 [US3] Implement template-based summary extraction in sessions/memory.py: compress_exchange_template() deterministically extracts code blocks, file paths, error messages, decisions, questions from an Exchange via regex/parsing — fallback strategy, no LLM call
- [x] T032 [US3] Implement LLM-assisted structured summarization in sessions/memory.py: compress_exchange_llm() calls strongest available model with current structured state + exchange, outputs field-level updates (hypothesis status changes, new decisions, open questions) — constrained to structured fields, must not contradict pinned facts
- [x] T033 [US3] Implement provider-aware compression trigger in sessions/memory.py: should_compress() checks if total context tokens for a model exceed compression_threshold (default 0.7 * max_context from ModelCapabilities), triggers compression of oldest verbatim exchange into working_summary, uses configured summary_strategy ("llm" or "template")
- [x] T034 [US3] Implement checkpoint creation in sessions/memory.py: create_checkpoint() snapshots current pinned_facts and working_summary into a named Checkpoint on ModelState
- [x] T035 [US3] Create follow_up tool in tools/follow_up.py: accepts session_id, alias, prompt, optional attachments and checkpoint_name; looks up session via SessionManager, signals the specific worker coroutine via wakeup_event with the follow-up prompt, worker appends to its local messages[] array, triggers compression if approaching context limit, calls provider via asyncio.to_thread(), appends response to messages[], returns response with session_exchanges_total, summary_included flag, both session_id and continuation_id. Also creates/appends to continuation_id thread for Claude-side memory (T022 coexistence).
- [x] T036 [US3] Register follow_up tool in server.py with name "follow_up", description, and input schema per contracts/mcp-tools.md

**Checkpoint**: Stateful follow-ups operational via persistent workers. Workers accumulate understanding across exchanges with automatic compression when approaching context limits.

---

## Phase 5: User Story 4 — Agent-Driven Context Enrichment (Priority: P2)

**Goal**: Models return structured context_requests alongside their Round 1 analysis. The orchestrator returns these to the caller. The caller gathers files and provides them for Round 2 (FR-008 — fork does not read files from disk).

**Independent Test**: Submit a prompt with intentionally incomplete context. Verify Round 1 responses include context_requests in DebateResult. Provide gathered artifacts via accept_gathered_artifacts(). Trigger Round 2. Verify analysis improves.

### Implementation for User Story 4

- [x] T037 [US4] Implement context request parsing in debate/context_requests.py: parse_context_requests() extracts structured requests from model response text — primary: look for ```json blocks or CONTEXT_REQUESTS markers, parse JSON into ContextRequest objects; fallback: regex for file paths in "I would need" / "additional context" sections
- [x] T038 [US4] Implement cross-model request deduplication in debate/context_requests.py: deduplicate_requests() merges requests across all models by path, keeps highest priority, aggregates rationales, returns unique list sorted by priority
- [x] T039 [US4] Add context request instruction to Round 1 prompts in debate/prompts.py: append structured output instruction to the end of each Round 1 prompt — "After your analysis, if you need additional files or context, output a JSON block labeled CONTEXT_REQUESTS: [{type, path, rationale, priority}]". Only append when DebateConfig.enable_context_requests=true (FR-029).
- [x] T040 [US4] Wire context enrichment into debate flow: guard entire context enrichment path on DebateConfig.enable_context_requests (FR-029). When true: after Round 1, parse context_requests from all worker responses, deduplicate, return in DebateResult.context_requests (debate pauses — caller gathers artifacts). Add accept_gathered_artifacts(session_id, artifacts) to orchestrator that populates SharedContext.gathered_artifacts, then caller triggers Round 2. When false: skip context request parsing entirely, proceed directly to Round 2 with Round 1 responses only (enables ablation Config C).

**Checkpoint**: Context enrichment operational. Models request files they need, orchestrator deduplicates, calling agent gathers and provides, Round 2 is enriched.

---

## Phase 6: User Story 5 — Adaptive Review Intensity (Priority: P3)

**Goal**: Single-model reviews output structured escalation signals (confidence, complexity, anomaly flags). When thresholds are exceeded, the system auto-promotes to full multi-model debate.

**Independent Test**: Submit a complex code change for single-model review. Verify the response includes an escalation signal. Submit a change with known issues that trigger low confidence. Verify the system auto-escalates to full debate.

### Implementation for User Story 5

- [x] T041 [US5] Add escalation signal prompt instructions to single-model code review tools: modify systemprompts/codereview_prompt.py (and precommit_prompt.py, refactor_prompt.py) to instruct the model to output a structured ESCALATION_SIGNAL block with confidence (0-1), complexity (low/medium/high), anomalies_detected (bool), escalation_reason (str)
- [x] T042 [US5] Implement escalation signal parsing in debate/orchestrator.py: parse_escalation_signal() extracts EscalationSignal from single-model response text using JSON block extraction with fallback defaults (confidence=0.8, complexity="medium", anomalies=false)
- [x] T043 [US5] Implement auto-escalation logic in debate/orchestrator.py: evaluate_escalation() checks signal against configured thresholds — if confidence < ESCALATION_CONFIDENCE_THRESHOLD OR complexity >= ESCALATION_COMPLEXITY_THRESHOLD OR anomalies_detected OR risk_areas intersects ESCALATION_AUTO_RISK_AREAS → return escalation_recommended=true
- [x] T044 [US5] Wire auto-escalation into tool execution flow in tools/shared/base_tool.py: read escalation_mode from request (default "adaptive"). If "always_full": skip single-model, go directly to full debate. If "never": single-model only, return result with escalation signal but no promotion. If "adaptive": after single-model review returns, parse escalation signal, evaluate against per-call thresholds (escalation_confidence_threshold, escalation_complexity_threshold) falling back to global defaults — if escalation recommended, automatically re-run with debate_mode=true (FR-030). This enables ablation Config E.
- [x] T045 [US5] Add escalation signal to single-model response format in tools/models.py: include EscalationSignal in ToolOutput when debate_mode=false for applicable tools (codereview, precommit, refactor, secaudit, analyze)

**Checkpoint**: Adaptive review operational. Single-model reviews self-assess and auto-escalate to full debate when needed.

---

## Phase 7: User Story 6 — Evaluation and Model Performance Tracking (Priority: P3)

**Goal**: Every model interaction produces a structured JSONL log entry. The compare_models tool queries and aggregates this data.

**Independent Test**: Run several multi-model debates across different task types. Call compare_models and verify it returns meaningful aggregations by model and task type.

### Implementation for User Story 6

- [x] T046 [P] [US6] Implement JSONL event logger in evaluation/logger.py: EvaluationLogger class with log_event() that appends EvaluationRecord as JSON line to logs/evaluation.jsonl, with file rotation at configurable size, thread-safe writes
- [x] T047 [P] [US6] Implement metrics collection in evaluation/metrics.py: build_evaluation_record() constructs EvaluationRecord from model response data (timestamp, event type, session_id, trace_id, alias, model, provider, task_type, round, input/output tokens, latency_ms, status, is_follow_up, exchange_number, context_requests_count, error_message)
- [x] T048 [US6] Implement aggregation queries in evaluation/reporter.py: EvaluationReporter class with query() method that reads JSONL, filters by task_type/model/since date, groups by model/task_type/both, computes avg_latency_ms, total_tokens, avg_tokens_per_response, success_rate, follow_up_rate, avg_follow_up_depth
- [x] T049 [US6] Create compare_models tool in tools/compare_models.py: accepts optional task_type, model, since, group_by per contracts/mcp-tools.md; calls EvaluationReporter.query(); returns structured comparison data with period metadata
- [x] T050 [US6] Wire evaluation logging into debate orchestrator and worker coroutines: after each provider call in Round 1/Round 2, call EvaluationLogger.log_event() with full metrics including trace_id; after synthesis, log synthesis event; after follow_up, log follow_up event; ensure eval data persists even when sessions are destroyed (FR-015)
- [x] T051 [US6] Register compare_models tool in server.py with name "compare_models", description, and input schema per contracts/mcp-tools.md

**Checkpoint**: Evaluation infrastructure operational. Every interaction logged with trace IDs, queryable via compare_models.

---

## Phase 8: User Story 7 — Session Handoff Between Agent Team Members (Priority: P3)

**Goal**: Any MCP caller (lead or teammate) can access any session by ID. Persistent workers serve any caller. Session inventory and cleanup tools available.

**Independent Test**: Create a session, call follow_up from a simulated second caller using the same session_id, verify context is preserved and worker responds with full history.

### Implementation for User Story 7

- [x] T052 [US7] Create list_sessions tool in tools/list_sessions.py: accepts optional active_only flag (default true), calls SessionManager.list_sessions(), returns session inventory with per-model stats including worker status per contracts/mcp-tools.md
- [x] T053 [P] [US7] Create destroy_session tool in tools/destroy_session.py: accepts session_id, calls SessionManager.destroy_session() which cancels all worker asyncio.Tasks, awaits clean cancellation, preserves eval data (FR-015), returns {destroyed, evaluation_data_preserved, session_id}
- [x] T054 [US7] Register list_sessions and destroy_session tools in server.py with names, descriptions, and input schemas per contracts/mcp-tools.md
- [x] T055 [US7] Verify concurrent session access: simulate two callers sending follow_up to the same session_id concurrently, verify per-session lock serializes writes to worker without deadlock, verify both responses reflect correct session state

**Checkpoint**: Session handoff operational. Any team member can discover, follow up on, or destroy sessions. Workers serve any caller transparently.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates, regression checks, compatibility verification

- [x] T056 Run ./code_quality_checks.sh — fix all ruff, black, isort issues across new files in debate/, sessions/, evaluation/, resilience/, and modified files
- [x] T057 Verify all 19 existing tools work in single-model mode (debate_mode=false or omitted) with no regressions — run python communication_simulator_test.py --quick
- [x] T058 Verify DEBATE_FEATURE_ENABLED=false makes fork behave as vanilla PAL/Zen: no debate fields in any schema, no debate code paths entered, all existing tests pass identically
- [x] T059 [P] Run existing unit test suite: python -m pytest tests/ -v -m "not integration" — fix any failures caused by base class modifications
- [x] T060 [P] Per-tool compatibility test: verify each major tool (debug, codereview, planner, thinkdeep, analyze, consensus) works correctly in BOTH single-model and debate mode — check schema correctness, continuation behavior, retry logic, response format, metadata
- [x] T061 [P] Update quickstart.md in specs/001-multi-model-agent-teams/quickstart.md with final configuration, verified setup steps, and tested usage examples
- [x] T062 Run full end-to-end flow: debate(debug, debate_mode=true) → context_requests returned → artifacts provided → Round 2 → follow_up(session_id, alias) → compare_models(group_by=model) → list_sessions() → destroy_session(session_id) — verify complete lifecycle with persistent workers
- [x] T063 Verify clean shutdown: kill the MCP server process, verify all worker asyncio.Tasks are cancelled cleanly, no orphaned tasks or threads, session GC fires, eval data flushed to disk

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1+US2 (Phase 3)**: Depends on Foundational — core debate functionality
- **US3 (Phase 4)**: Depends on Phase 3 (needs working sessions/workers from debate)
- **US4 (Phase 5)**: Depends on Phase 3 (needs working Round 1/Round 2 flow)
- **US5 (Phase 6)**: Depends on Phase 3 (needs debate infrastructure to escalate into)
- **US6 (Phase 7)**: Depends on Phase 3 (needs debate interactions to log)
- **US7 (Phase 8)**: Depends on Phase 4 (needs follow_up working for handoff test)
- **Polish (Phase 9)**: Depends on all desired user stories being complete

### User Story Dependencies

```
Phase 1: Setup
    ↓
Phase 2: Foundational (BLOCKS ALL) — includes schema verification!
    ↓
Phase 3: US1+US2 (P1) ← MVP
    ↓ ↓ ↓
    │ │ └── Phase 5: US4 (P2) — context enrichment
    │ └──── Phase 6: US5 (P3) — adaptive escalation
    │ └──── Phase 7: US6 (P3) — evaluation logging
    ↓
Phase 4: US3 (P2) — stateful follow-ups
    ↓
Phase 8: US7 (P3) — session handoff
    ↓
Phase 9: Polish
```

### Parallel Opportunities

After Phase 2 (Foundational), the following can proceed in parallel:
- US4, US5, US6 are independent of each other (all depend only on Phase 3)
- Within Phase 1: T004 and T005 are parallel (different files)
- Within Phase 2: T007, T008, T009 are parallel (different files)
- Within Phase 3: T027 and T028 are parallel (different tools)
- Within Phase 7: T046 and T047 are parallel (different files)
- Within Phase 8: T052 and T053 are parallel (different tools)
- Within Phase 9: T059, T060, T061 are parallel

### Within Each Phase

- Types/models before services
- Services before tools
- Core logic before wiring/registration
- Schema verification immediately after schema-affecting changes
- Complete phase before moving to next priority

---

## Implementation Strategy

### MVP First (Phase 1 + 2 + 3 Only)

1. Complete Phase 1: Setup (5 tasks)
2. Complete Phase 2: Foundational (17 tasks — CRITICAL, blocks all stories)
3. Complete Phase 3: US1+US2 — Multi-Model Debate (7 tasks)
4. **STOP and VALIDATE**: Test debate on debug, codereview, planner tools
5. Deploy/demo if ready — this is a usable product

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1+US2 → Test independently → **MVP!** (core debate works)
3. Add US3 → Test independently → Follow-ups work
4. Add US4 → Test independently → Context enrichment works
5. Add US5+US6+US7 → Test independently → Full feature set
6. Polish → Quality validated → Ship

### Phase 2 Future Scope (not in this task list)

- Multi-team workstream scoping (tagging sessions by workstream)
- Tool-capable agents (non-Claude models using tools)
- Agent-to-agent messaging within debate sessions
- Auto-routing based on evaluation data (model-task affinity scores)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Tests not generated (not requested in spec) — add via /speckit.tasks with TDD flag if needed
- DEBATE_FEATURE_ENABLED=false is the rollback plan — disables all debate code paths
