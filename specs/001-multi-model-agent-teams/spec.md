# Feature Specification: Multi-Model Agent Teams

**Feature Branch**: `001-multi-model-agent-teams`
**Created**: 2026-03-22
**Status**: Draft
**Input**: Fork PAL/Zen MCP server to enable adversarial multi-model debate across LLM providers (OpenAI, Google, Anthropic) for software engineering tasks — debugging, code review, architecture design, and planning — where multiple LLMs analyze the same problem independently, then argue about each other's findings to produce higher-quality outcomes than any single model.

## Clarifications

### Session 2026-03-22

- Q: How should the fork coexist with the original PAL/Zen during development? → A: Side-by-side — fork runs as a separate MCP server with its own distinct name; original PAL/Zen remains unmodified and fully operational. Both are configured simultaneously in Claude Code settings.
- Q: Should the fork's tools use new names or the same names as PAL/Zen? → A: Same tool names under a new server namespace (e.g., `mcp__debate__debug` mirrors `mcp__pal__debug`). Drop-in replacement pattern — swapping is just changing the namespace prefix in workflow instructions.
- Q: What is the upstream relationship with PAL/Zen? → A: GitHub fork with periodic manual merges. Full credit and attribution to original author (Fahad Gilani / Beehive Innovations) per Apache 2.0 requirements. Upstream improvements incorporated on our schedule, not automatically.
- Q: Minimum models for a valid debate? → A: Minimum 2 for debate (Round 2 proceeds), 1 for single-model analysis (no Round 2, with warning). The fork is fully self-contained — no fallback to original PAL/Zen. Users do not need the original installed. Single-model mode is built into the fork natively for conformance checks, graceful degradation, and standalone use.
- Q: Who gathers files requested by models between debate rounds? → A: The calling agent (Claude). The fork returns structured context_requests to the caller, the caller reads the files and passes them into Round 2. The fork does not read files from disk itself — it remains a text-advisory system that sends/receives prompts to LLM APIs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Multi-Model Debugging (Priority: P1)

A developer encounters a complex bug (e.g., a race condition, intermittent failure, or multi-component interaction issue). Instead of a single AI model investigating, the system sends the same bug report and relevant code to three different LLMs in parallel. Each model analyzes independently (Round 1), then sees the other models' findings and argues about which hypotheses are correct (Round 2). The developer receives a synthesized analysis that includes findings from all models, highlights where they agreed and disagreed, and presents a refined fix that no single model proposed alone.

**Why this priority**: Debugging complex issues is the highest-value use case. Different LLMs have different training data and blind spots — one model may notice a threading issue while another catches a resource leak. The adversarial debate in Round 2 refines proposals (e.g., simplifying an over-engineered fix) and surfaces requirements missed in Round 1.

**Independent Test**: Can be tested by submitting a known multi-cause bug to the system and verifying that the debate produces more root causes and a more refined fix than any individual model's Round 1 response.

**Acceptance Scenarios**:

1. **Given** a bug report with relevant source code, **When** the developer requests a multi-model debug analysis, **Then** three models analyze independently in parallel and return their findings within 20 seconds
2. **Given** Round 1 responses from three models, **When** the system initiates Round 2, **Then** each model sees all other Round 1 responses, provides critique, and revises its recommendations
3. **Given** completed Round 1 and Round 2, **When** the developer views the synthesis, **Then** agreement points, disagreement points, and a consolidated recommendation are clearly presented
4. **Given** one model identifies a finding unique to its analysis, **When** other models see it in Round 2, **Then** they validate, challenge, or build upon it — and the final synthesis reflects the outcome of that debate

---

### User Story 2 - Multi-Model Code Design Review (Priority: P1)

Before writing code for a new feature, the developer asks the system to debate the architecture. Three LLMs each propose an implementation approach independently, then critique each other's designs. The developer receives a synthesis showing trade-offs, a recommended hybrid approach, and requirements that only emerged during the debate (e.g., graceful degradation scenarios no single model considered).

**Why this priority**: Design errors caught before coding save orders of magnitude more rework than errors caught during implementation. Multi-model debate at the design stage is the highest-leverage investment in code quality.

**Independent Test**: Can be tested by requesting an architecture design for a known problem, verifying the debate produces trade-off analysis and requirements beyond what any single model proposed.

**Acceptance Scenarios**:

1. **Given** a feature description with relevant existing code, **When** the developer requests a multi-model design review, **Then** three models propose independent architectures in parallel
2. **Given** three different architecture proposals, **When** Round 2 debate occurs, **Then** models identify weaknesses in each other's proposals and propose refinements
3. **Given** debate completion, **When** the synthesis is generated, **Then** it includes a recommended approach that incorporates the strongest elements from multiple proposals and addresses weaknesses raised during debate

---

### User Story 3 - Stateful Follow-Up Conversations (Priority: P2)

After an initial multi-model debate, the developer begins implementing the recommended approach. A new design question arises during implementation. The developer sends a follow-up to the same debate session. Each model receives its prior analysis (via compressed session state) along with the new question, so it can build on its accumulated understanding rather than starting from scratch.

**Why this priority**: Without session state, every follow-up question requires re-summarizing the entire prior debate, which is lossy and expensive. Persistent sessions let models accumulate understanding across multiple exchanges, producing higher-quality follow-up responses.

**Independent Test**: Can be tested by running an initial debate, then sending a follow-up question and verifying that model responses reference and build upon their prior analysis without it being re-fed manually.

**Acceptance Scenarios**:

1. **Given** a completed multi-model debate session, **When** the developer sends a follow-up question to the session, **Then** each model receives its compressed prior context and responds in the context of its earlier analysis
2. **Given** a follow-up exchange that pushes a model's context usage beyond the compression threshold, **When** the system compresses older exchanges, **Then** key facts, decisions, and hypotheses are preserved in a structured summary while verbatim exchanges slide out
3. **Given** models with different context limits, **When** compression occurs, **Then** each model's compression threshold respects its provider-specific context window size

---

### User Story 4 - Agent-Driven Context Enrichment (Priority: P2)

During Round 1 analysis, each model identifies files or artifacts it wishes it had access to but were not included in the original prompt. These requests are returned as structured output alongside the analysis. Between Round 1 and Round 2, the system gathers the requested context and includes it in Round 2, enriching the debate with information the models themselves identified as relevant.

**Why this priority**: The orchestrating agent cannot anticipate what every model will need. Letting models request context as a structured side-channel eliminates blind spots without blocking the analysis or adding interactive complexity.

**Independent Test**: Can be tested by submitting a problem with intentionally incomplete context, verifying that models request the missing files, and confirming Round 2 analysis improves after those files are provided.

**Acceptance Scenarios**:

1. **Given** a prompt with relevant but incomplete code context, **When** models complete Round 1, **Then** each model returns both its analysis and a structured list of additional files/artifacts it would find useful
2. **Given** context requests from multiple models, **When** the system gathers artifacts between rounds, **Then** requests are deduplicated and the orchestrator decides which are worth including
3. **Given** gathered artifacts added to Round 2, **When** models receive the enriched context, **Then** their Round 2 analysis incorporates findings from the newly available information

---

### User Story 5 - Adaptive Review Intensity (Priority: P3)

The system supports configurable review intensity per task. Design stages default to full multi-model debate. Per-stage code reviews default to a single-model review that includes a structured confidence/escalation signal — when the reviewer flags low confidence, high complexity, or anomalies it cannot resolve alone, the system automatically escalates to full multi-model debate. Mechanical edits (renames, docs, wiring) use light single-model checks. A final full multi-model review occurs on the complete change set before commit.

**Why this priority**: Conformance does not equal correctness. Code that faithfully implements a design can still contain race conditions, off-by-one errors, API misuse, and edge cases that no amount of upstream design debate could predict. Implementation is a discovery process — different models catch different bug classes. Adaptive escalation catches implementation bugs early while preserving speed for straightforward stages.

**Independent Test**: Can be tested by executing a full feature workflow (design → implement → review) and verifying that: (a) design stages use full debate, (b) per-stage reviews produce escalation signals, (c) low-confidence reviews auto-promote to full debate, (d) the final review uses full debate.

**Acceptance Scenarios**:

1. **Given** a design-stage task (architecture, debugging root cause, planning), **When** the system determines review intensity, **Then** full multi-model debate (Round 1 + Round 2) is used
2. **Given** a per-stage code review, **When** the single-model reviewer completes its analysis, **Then** it returns both the review AND a structured escalation signal (confidence score, complexity assessment, anomaly flags)
3. **Given** a per-stage review where the reviewer's confidence is below threshold OR complexity exceeds threshold OR an anomaly is flagged, **When** the escalation signal is evaluated, **Then** the system automatically promotes to full multi-model debate on that stage
4. **Given** a per-stage review of a mechanical edit (rename, docs update, simple wiring), **When** the reviewer's confidence is high and no anomalies detected, **Then** the light single-model review is accepted without escalation
5. **Given** a complete change set ready for final review, **When** the final review is triggered, **Then** full multi-model debate is used as the last quality gate

---

### User Story 6 - Evaluation and Model Performance Tracking (Priority: P3)

Every model interaction is logged with structured metrics (model, latency, tokens, task type, quality signals). Over time, the developer can query which models produce the best results for which task types — enabling data-driven model selection and continuous quality improvement.

**Why this priority**: Without evaluation data, model selection is guesswork. Systematic tracking reveals patterns (e.g., one model consistently catches security issues, another excels at architecture analysis) that improve debate outcomes over time.

**Independent Test**: Can be tested by running a series of multi-model interactions across different task types, then querying the evaluation data and verifying it produces meaningful aggregations by model and task type.

**Acceptance Scenarios**:

1. **Given** a completed multi-model interaction, **When** the system logs the event, **Then** a structured record is persisted including model, provider, task type, token counts, latency, and quality signals
2. **Given** accumulated evaluation data from multiple sessions, **When** the developer queries model performance, **Then** results are aggregated by model, task type, or both, with metrics including average latency, success rate, and follow-up depth
3. **Given** evaluation data spanning multiple weeks, **When** patterns are analyzed, **Then** model-task affinities (which model excels at which task type) can be identified from the data

---

### User Story 7 - Session Handoff Between Agent Team Members (Priority: P3)

The lead agent creates a multi-model debate session and passes the session ID to a Claude teammate via message. The teammate can then send follow-up questions to specific models in that session, because the session state lives in a shared process accessible to all team members. This enables the lead to handle strategy while teammates handle execution, each consulting the same advisory models.

**Why this priority**: In agent team workflows, different teammates work on different aspects of the same problem. Shared session access means the analysis context doesn't need to be re-created for each teammate — they can build on the same debate.

**Independent Test**: Can be tested by creating a session from a lead agent, passing the session ID to a simulated teammate, and verifying the teammate can successfully follow up on the session with full context preservation.

**Acceptance Scenarios**:

1. **Given** a multi-model session created by the lead agent, **When** the session ID is communicated to a teammate, **Then** the teammate can call follow-up on that session and receive contextually aware responses
2. **Given** multiple teammates interacting with the same session, **When** evaluation data is queried, **Then** all interactions are tracked in a single unified log regardless of which teammate initiated them

---

### Edge Cases

- What happens when one LLM provider is unavailable during a debate? The system returns successful responses from available providers plus warnings about failures — partial results are still valuable.
- What happens when all three models agree on something incorrect? The synthesis should note unanimous agreement but not treat it as infallible — the orchestrator may still validate claims against source code.
- What happens when context requests from models reference files that don't exist? The system filters out invalid requests and proceeds with available artifacts.
- What happens when a follow-up is sent to a session that has expired (idle timeout)? The system returns a clear error indicating the session was garbage collected, with the evaluation data still preserved.
- What happens when a model's response exceeds the expected format (no structured context_requests, malformed output)? The system uses the response content as-is for the analysis portion and treats the context request as empty.
- What happens when compression produces a summary that contradicts pinned facts? The compression pipeline is constrained to update structured fields only and must not contradict pinned facts — any contradiction is a system error to be logged and investigated.
- What happens when multiple teammates send concurrent follow-ups to the same session? The session manager serializes writes to prevent state corruption — concurrent reads are safe, but follow-up exchanges are queued and processed sequentially per session.
- What happens when a model's Round 1 response is shared with other models in Round 2 and contains adversarial or misleading content? Round 2 prompts frame all Round 1 responses as claims to be critically evaluated, not trusted facts. The synthesis step cross-references claims against each other and against provided source code.
- What happens when a per-stage code review flags an implementation bug that technically conforms to the design? The reviewer's escalation signal promotes the review to full multi-model debate, where multiple models analyze the implementation bug with the same rigor as a design review.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST send the same analysis prompt to multiple LLM providers in parallel and collect all responses
- **FR-002**: System MUST support at least three LLM providers (Anthropic, OpenAI, Google) with the ability to add more
- **FR-003**: System MUST implement a two-round debate pattern: Round 1 (independent parallel analysis) followed by Round 2 (adversarial critique where each model sees all Round 1 responses)
- **FR-004**: System MUST synthesize multi-model responses into structured output identifying agreement points, disagreement points, and consolidated recommendations
- **FR-005**: System MUST support stateful follow-up conversations where models receive compressed prior context alongside new prompts
- **FR-006**: System MUST implement stratified memory per model: pinned facts (immutable), working summary (compressed), recent verbatim exchanges (sliding window), and named checkpoints
- **FR-007**: System MUST manage context window limits per provider, compressing older exchanges when approaching provider-specific thresholds
- **FR-008**: System MUST return structured context requests from model Round 1 responses to the calling agent, enabling agent-driven information acquisition between debate rounds. The fork does not read files from disk — the calling agent gathers requested artifacts and provides them when initiating Round 2
- **FR-009**: System MUST log every model interaction with structured metrics including model, provider, task type, token counts, latency, and status
- **FR-010**: System MUST support querying evaluation logs with aggregation by model, task type, or both
- **FR-011**: System MUST handle partial failures gracefully — minimum 2 model responses to proceed with Round 2 debate; 1 response returns single-model analysis with a warning; output always indicates how many models participated (e.g., "3/3" vs "2/3 — Google: timeout")
- **FR-012**: System MUST implement rate limiting per provider to prevent exceeding API quotas
- **FR-013**: System MUST implement circuit breakers that stop retrying consistently failing providers
- **FR-014**: System MUST support session garbage collection after a configurable idle timeout
- **FR-015**: System MUST preserve evaluation log data even when sessions are destroyed or expire
- **FR-016**: System MUST inherit and preserve existing tool-specific prompt engineering (debug, codereview, planner, etc.) as the structured framing for each debate
- **FR-018**: System MUST register tools using the same names as the original PAL/Zen tools (debug, codereview, planner, etc.) so that the server namespace is the only differentiator — enabling drop-in replacement by changing the namespace prefix in workflow configuration
- **FR-019**: System MUST maintain clear attribution to the original PAL/Zen project and author per Apache 2.0 license requirements, including NOTICE file preservation, license headers, and visible credit in project documentation
- **FR-020**: System MUST be fully self-contained — no dependency on an original PAL/Zen installation. Single-model operation (for conformance checks and graceful degradation) MUST be built into the fork natively, not delegated to an external PAL/Zen server
- **FR-017**: System MUST support configurable summary strategy (deterministic template extraction or LLM-assisted compression) with safeguards against summary drift
- **FR-021**: Per-stage code reviews MUST include a structured escalation signal (confidence score, complexity assessment, anomaly flags) in their output. When the reviewer reports low confidence, high complexity, or anomalies beyond conformance, the system MUST automatically promote the review to full multi-model debate
- **FR-022**: Session manager MUST serialize concurrent write operations (follow-ups, state mutations) to the same session to prevent state corruption from concurrent teammate access
- **FR-023**: Round 2 prompts MUST frame all Round 1 responses as claims to be critically evaluated, not trusted input — mitigating prompt injection risk from cross-model transcript sharing
- **FR-024**: System MUST handle partial failures in Round 2 gracefully — if one model fails its adversarial critique, synthesis proceeds with available Round 2 responses plus the failed model's Round 1 response only. Output indicates Round 2 participation (e.g., "Round 2: 2/3 — Gemini: timeout")
- **FR-025**: The debate orchestrator MUST use persistent async worker coroutines (one asyncio.Task per model per session) that maintain a growing messages[] array as context across rounds and follow-ups, coordinated via asyncio.Barrier for round synchronization and asyncio.Event for follow-up wakeup
- **FR-026**: Debate mode fields (debate_mode, debate_models, session_id, debate_max_rounds) MUST only appear in the input schema of applicable tools (debug, codereview, planner, thinkdeep, analyze, secaudit, docgen, refactor, tracer, testgen, precommit, consensus) — NOT on chat, clink, apilookup, listmodels, version, or challenge
- **FR-027**: System MUST provide a master feature flag (DEBATE_FEATURE_ENABLED) that, when disabled, completely removes debate code paths and schema fields — allowing the fork to run as a vanilla PAL/Zen server for regression testing
- **FR-028**: System MUST support a per-call `synthesis_mode` parameter with values `"synthesize"` (default — merge all perspectives into unified analysis) and `"select_best"` (score each model's response against the task objective on a 1-10 scale, return the highest-scoring response as the primary output with scores for all). This enables ablation Config B (ensemble selection without debate).
- **FR-029**: System MUST support a per-call `enable_context_requests` parameter (boolean, default true) that controls whether Round 1 prompts include the context request instruction and whether context_requests are parsed from responses. When false, Round 1 responses are used as-is without context enrichment. This enables isolating the value of context acquisition (ablation Config C vs D).
- **FR-030**: System MUST support per-call escalation overrides: `escalation_mode` with values `"adaptive"` (default — use threshold-based auto-escalation), `"always_full"` (always use full multi-model debate, no single-model step), and `"never"` (never escalate, single-model only). When `"adaptive"`, optional per-call `escalation_confidence_threshold` and `escalation_complexity_threshold` override global defaults. This enables ablation Config E (tiered vs full debate).

### Key Entities

- **Debate Session**: A coordinated multi-model analysis instance, containing per-model state, shared context, and metadata. Identified by a unique session ID. Transient (in-memory, not persisted across restarts).
- **Model State**: Per-model memory within a session — pinned facts, working summary, recent exchanges, checkpoints, and token usage tracking. Each model maintains independent state even within the same session.
- **Shared Context**: Information common to all models in a session — the original prompt, code files, Round 1 responses (for Round 2), and gathered artifacts from context requests.
- **Context Request**: A structured request from a model for additional information, returned alongside its analysis. Includes artifact type, path, rationale, and priority.
- **Pinned Fact**: An immutable piece of information established during a session — a confirmed hypothesis, a decision, a constraint. Never compressed, always included in context construction.
- **Evaluation Record**: A structured log entry capturing one model interaction — model, provider, task type, tokens, latency, quality signals. Persisted to disk and queryable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Multi-model debate produces findings that no single participating model identified alone in at least 60% of substantive analysis tasks (debugging, design review, architecture decisions)
- **SC-002**: Round 2 adversarial debate changes or refines the recommended approach compared to Round 1 synthesis in at least 40% of debates
- **SC-003**: A complete two-round debate (Round 1 + context gathering + Round 2) completes within 25 seconds wall-clock time under normal conditions
- **SC-004**: Follow-up questions to an existing session produce contextually aware responses (referencing prior findings without manual re-injection) for at least 8 consecutive follow-ups, validated by checking that responses reference at least 2 specific prior findings per follow-up
- **SC-005**: Adaptive review intensity (full debate for design, escalation-capable reviews for implementation, full debate for final review) catches at least 80% of implementation bugs that would have been caught by uniform full-debate review, measured by comparing escalation-mode outcomes against full-debate baselines on a benchmark set of known-buggy implementations
- **SC-006**: Partial provider failure (one of three providers unavailable) still produces usable results from the remaining providers with clear warnings about the degraded state
- **SC-007**: Evaluation data accumulated over 2+ weeks of real usage reveals measurable model-task affinities — statistically distinguishable performance differences between models across task types

### Assumptions

- API keys for at least three major LLM providers (Anthropic, OpenAI, Google) are available and have sufficient rate limits for parallel multi-model queries
- The existing PAL/Zen MCP server codebase (Apache 2.0, ~16,500 lines) provides a viable foundation for forking, including provider abstractions, prompt engineering, and MCP infrastructure. The fork is maintained as a GitHub fork of the original repository with periodic manual merges to incorporate upstream improvements on a controlled schedule
- LLM providers maintain stable APIs during the development period — major breaking changes would require adapter updates
- Context window sizes across providers remain in the current range (128K–1M tokens) — significant reductions would affect session management design
- The system runs as a single long-lived local process alongside the coding agent, making in-memory session state viable for the duration of a coding session
- Session durability across MCP server restarts is not required for the initial version — sessions are transient within a coding session, with only evaluation data persisted to disk
- The fork runs as a separate, independently named MCP server. During development, it runs alongside the original PAL/Zen installation for convenience, but the fork is fully self-contained — end users do not need the original PAL/Zen installed
