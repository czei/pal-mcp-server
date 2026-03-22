# Research: Multi-Model Agent Teams

**Phase 0 output for**: `/specs/001-multi-model-agent-teams/plan.md`
**Date**: 2026-03-22

## Research Tasks

### R-001: How to integrate debate orchestration with existing tool architecture

**Decision**: Add debate orchestration as a layer between tool execution and
provider calls, controlled by a `debate_mode` parameter on tool requests.

**Rationale**: The existing architecture has two tool patterns — `SimpleTool`
(6 tools: chat, clink, apilookup, listmodels, version, challenge) and
`WorkflowTool` (13 tools: debug, codereview, planner, etc.). Both inherit from
`BaseTool` which already handles model selection, file embedding, and
continuation_id threading.

The debate layer intercepts at the point where a tool would normally call a
single provider. Instead of `provider.generate_content()` returning one
`ModelResponse`, the `DebateOrchestrator` fans out the same prompt to multiple
providers in parallel (Round 1), collects structured context requests, and
optionally runs Round 2 with all Round 1 responses shared.

This requires modifying `BaseTool` to check for debate mode before calling the
provider, and routing through the orchestrator when enabled. The existing
per-tool prompt engineering (in `systemprompts/`) becomes the task-specific
framing passed to all models — same prompt, all models, let them argue.

**Alternatives considered**:
- Creating new debate-specific tool classes for each tool (rejected: duplicates
  19 tools worth of logic for no benefit)
- Modifying each tool individually to support debate (rejected: violates DRY;
  debate is a cross-cutting concern)
- Making debate a middleware in server.py (rejected: too coarse; not all tools
  benefit from debate — e.g., listmodels, version)

---

### R-002: How session state interacts with existing continuation_id system

**Decision**: Session state and continuation_id operate as complementary systems.
`continuation_id` continues to manage Claude-side conversation history (what the
calling agent remembers). Session state manages model-side conversation history
(what each non-Claude model remembers across debate rounds and follow-ups).

**Rationale**: The existing `continuation_id` system (in
`utils/conversation_memory.py`) stores `ThreadContext` objects with
`ConversationTurn` entries in an in-memory store with 3-hour TTL. It tracks
what the calling agent said and what the tool responded. This is the
orchestrator's memory.

Session state (new `sessions/` module) tracks what each individual model said
and was told across debate rounds and follow-ups. This is per-model memory,
stratified into pinned facts, working summary, and recent verbatim exchanges.

The two systems intersect when:
1. A tool call with `continuation_id` AND `session_id` — the tool uses
   continuation_id for the Claude-side thread, and session_id for model-side
   context injection
2. A `follow_up` tool call — uses session_id to locate model state, builds
   context from stratified memory, and appends to continuation_id thread

They do NOT merge. Continuation_id stores flat conversation turns (user/assistant
role pairs). Session state stores structured per-model memory with compression.
Different purposes, different lifecycles.

**Alternatives considered**:
- Extending continuation_id to hold per-model state (rejected: continuation_id
  is a flat conversation log; adding stratified per-model memory would
  overload its design and break existing tools)
- Replacing continuation_id entirely with session state (rejected: continuation_id
  serves the Claude-side conversation; session state serves model-side; both needed)

---

### R-003: Strategy for parallel multi-provider API calls in Python

> **SUPERSEDED by R-011.** The original decision recommended pure asyncio.gather()
> and rejected ThreadPoolExecutor. R-011 refines this: workers are async coroutines
> (asyncio.Task) that use `asyncio.to_thread()` only for the blocking
> `provider.generate_content()` call. This preserves async coordination while
> correctly handling synchronous providers.

**Original decision** (retained for context): Use `asyncio.gather()` with per-
provider timeouts. Partial failure tolerance — min 2 for Round 2, 1 returns
single-model with warning (FR-011). This core principle carries forward into
R-011; only the threading model changed.

---

### R-004: Best approach for LLM-assisted session summarization

**Decision**: Use constrained structured summarization with the strongest
available model. Summaries update structured fields (hypothesis status,
decisions made, open questions, key findings) rather than rewriting freeform
prose.

**Rationale**: The spec requires two summarization strategies (FR-017):
1. Template extraction (fallback): Deterministic — extracts code blocks,
   file paths, error messages, decisions, questions via regex/parsing
2. LLM-assisted (default): Uses an LLM to compress older exchanges into
   structured updates

The risk with LLM summarization is drift — over multiple compression cycles,
the summary diverges from what actually happened. The mitigation is
constraining summaries to structured field updates rather than freeform rewrites.
The model receives the current structured state and the exchange to compress,
and outputs field-level updates (e.g., "hypothesis X: confirmed", "new
decision: use approach Y").

Pinned facts are never included in summarization input — they're immutable
and always passed through directly. This prevents the summary from
contradicting established facts.

For model selection: use the strongest available model for summaries. Summary
quality directly affects follow-up quality. The latency of summarization is
not user-facing (it happens after the response is returned), so speed is
secondary to quality.

**Alternatives considered**:
- Freeform prose summarization (rejected: drift accumulates over cycles;
  after 5+ compressions the summary may be unreliable)
- No summarization — just truncate (rejected: loses critical context; user
  stories require 8+ follow-ups with context preservation)
- Hybrid: structured fields + brief prose narrative (considered for Phase 2:
  allows richer context while maintaining structured anchors)

---

### R-005: How to parse structured context_requests from model responses

**Decision**: Append a structured output instruction to the end of each Round 1
prompt requesting JSON-formatted context requests. Parse with a combination of
JSON extraction and fallback regex.

**Rationale**: FR-008 requires models to return structured `context_requests[]`
alongside their analysis. The challenge: different models produce different
output formats, and we can't rely on JSON mode for all providers (some don't
support it reliably for mixed content — analysis text + structured data).

The approach:
1. Append to the Round 1 prompt: "After your analysis, if you need additional
   files or context, output a JSON block labeled CONTEXT_REQUESTS with fields:
   `[{type, path, rationale, priority}]`"
2. Primary parser: look for ```json blocks or `CONTEXT_REQUESTS:` markers,
   extract JSON
3. Fallback parser: regex for file path patterns mentioned in "I would need"
   or "additional context" sections
4. If no structured requests found: treat as empty (model didn't need more context)
5. Deduplicate across models before returning to caller

This is robust against format variation. Models that follow the instruction
precisely get clean JSON parsing. Models that mention files informally get
caught by the fallback regex. Either way, the orchestrator collects a
deduplicated list.

**Alternatives considered**:
- Require JSON-only responses (rejected: forces analysis into JSON, loses
  natural language quality for the actual analysis content)
- Separate API call for context requests (rejected: doubles latency and cost;
  models can easily append structured data to their analysis)
- Use function calling / tool_use for context requests (rejected: tool_use
  format differs across providers; adds the format translation problem we're
  explicitly deferring)

---

### R-006: Rate limiting and circuit breaker patterns for multi-provider calls

**Decision**: Token bucket rate limiter per provider with configurable RPM.
Circuit breaker with configurable failure threshold and reset timeout.

**Rationale**: When 3 models debate in parallel across multiple sessions, the
rate of API calls per provider increases 3x compared to single-model usage.
Without rate limiting, concurrent debates could exhaust provider quotas.

Token bucket algorithm: each provider gets a bucket with capacity = RPM/60
(requests per second). Bucket refills at that rate. When empty, calls queue
with a max wait time. If max wait exceeded, immediate error.

Circuit breaker: tracks consecutive failures per provider. After
`failure_threshold` (default 3) consecutive failures, the circuit opens and
all calls to that provider fail immediately for `reset_timeout_ms` (default
60s). After timeout, circuit enters half-open state — allows one probe call.
If probe succeeds, circuit closes. If probe fails, circuit re-opens.

Both systems are shared across all agent team members because there is one
MCP server process with one set of provider connections.

**Alternatives considered**:
- Per-session rate limiting (rejected: provider quotas are account-level,
  not session-level; must aggregate across all sessions)
- No rate limiting, rely on provider-side 429 responses (rejected: 429s
  cause cascading retries; better to prevent than recover)

---

### R-007: Existing consensus tool as reference implementation

**Decision**: Use the existing `ConsensusTool` as the architectural reference
for multi-model fan-out, but extract the pattern into a reusable
`DebateOrchestrator` that all tools can use.

**Rationale**: The existing `consensus.py` tool already implements:
- Multi-model fan-out (queries multiple providers in sequence)
- Per-model system prompt injection
- Structured synthesis of responses
- Stance injection (for/against/neutral per model)
- File-request protocol in prompts

However, it has limitations:
- Sequential model calls (not parallel)
- No Round 2 adversarial debate (models don't see each other's responses)
- No session persistence (stateless like all current tools)
- Tightly coupled to the consensus-specific prompt

The `DebateOrchestrator` extracts the fan-out pattern, adds parallel execution,
adds Round 2 debate, and makes it reusable across all tools. The consensus
tool becomes one user of the orchestrator (with stance-specific additions).

**Alternatives considered**:
- Extending consensus.py to be the universal debate tool (rejected: consensus
  has specific UX — stance injection, verdict format — that doesn't apply to
  debug or codereview)
- Each tool implements its own fan-out (rejected: massive duplication; the
  debate pattern is identical across tools, only the prompt framing differs)

---

### R-008: Fork coexistence and upstream sync strategy

**Decision**: GitHub fork with the fork running as a separate MCP server under
a distinct namespace. Upstream sync via periodic manual cherry-pick/merge on a
controlled schedule.

**Rationale**: The fork needs its own release cycle (debate features ship
independently of upstream PAL/Zen updates). Running as a separate MCP server
(e.g., `mcp__debate__debug` vs `mcp__pal__debug`) allows both to coexist
during development and testing.

For upstream sync:
- Fork tracks upstream `main` branch as a remote
- Monthly (or as-needed) manual merge of upstream changes
- Conflicts resolved in favor of fork additions (session state, debate layer)
- Upstream tool improvements cherry-picked when beneficial
- Fork-specific changes live in clearly marked modules (`debate/`, `sessions/`,
  `evaluation/`, `resilience/`)

The separation between inherited code (existing directories) and new code
(new directories) makes merge conflicts rare — most fork work is additive.

**Alternatives considered**:
- Patch set maintained separately (rejected: harder to track what's changed;
  fork with distinct modules is cleaner)
- Monorepo with PAL/Zen as submodule (rejected: adds build complexity for
  no benefit; fork is self-contained)

---

### R-009: Provider-aware context compression thresholds

**Decision**: Each model's compression threshold is calculated as a percentage
of its `max_context` from `ModelCapabilities`. Default threshold: 70% of
max_context. When total context (pinned facts + working summary + recent
exchanges + shared context + new prompt) exceeds threshold, the oldest
verbatim exchange is compressed into the working summary.

**Rationale**: Models have vastly different context windows:
- Gemini 2.5 Pro: 1,048,576 tokens (1M)
- Claude Sonnet: 200,000 tokens
- GPT-4o: 128,000 tokens

A fixed compression threshold would either compress too aggressively for
Gemini (wasting its context capacity) or too late for GPT-4o (risking
context overflow). Per-model thresholds ensure each model gets the richest
history its window allows.

The 70% threshold leaves 30% headroom for the new prompt and response. This
is conservative — actual headroom needed depends on prompt size and expected
response length. The threshold is configurable per model via the session
config.

Token counting for threshold checks uses the existing `count_tokens()` method
on `ModelProvider`, which is already provider-aware (tiktoken for OpenAI,
native counting for Gemini, etc.).

**Alternatives considered**:
- Fixed threshold for all models (rejected: wastes Gemini's 1M context or
  overflows GPT-4o's 128K)
- No compression, just truncate (rejected: loses structured context;
  summarization preserves decisions and findings)

---

### R-010: Adaptive review escalation vs rigid tiered intensity

**Decision**: Replace the rigid "heavy debate upstream, light checks downstream"
principle with adaptive escalation. Per-stage code reviews default to single-model
analysis with a structured confidence/escalation signal. When the reviewer flags
low confidence, high complexity, or anomalies it cannot resolve alone, the system
automatically promotes to full multi-model debate.

**Rationale**: A 3-model consensus review (GPT-5.4, Gemini 2.5 Pro, Claude Opus
4.6 — unanimous at 8/10 confidence) identified that the original principle
conflates design conformance with implementation correctness. This is a false
equivalence:

1. **Design deviation**: Code doesn't match the plan → single-model conformance
   catches this fine
2. **Implementation bug**: Code matches the plan but contains a race condition,
   off-by-one error, API misuse, or edge case the plan couldn't anticipate →
   conformance check misses this entirely

Real-world experience confirms: more than half of engineering time is spent finding
bugs in implementations that follow specs. Implementation is a discovery process
that reveals issues no upstream design debate could predict. Different models catch
different bug classes — a single-model conformance check systematically misses
categories of defects that multi-model review would catch.

The adaptive model preserves efficiency for straightforward stages (~5s single-model
review) while catching the critical cases through auto-escalation to full debate
(~15-20s) only when needed.

**Escalation triggers**:
- Reviewer confidence score below configurable threshold
- Code complexity exceeds configurable threshold (files changed, cyclomatic
  complexity, risk tags)
- Reviewer explicitly flags an anomaly it cannot resolve alone
- Code touches high-risk areas (concurrency, auth, persistence, APIs, parsing)

**Alternatives considered**:
- Keep rigid "light checks downstream" (rejected: 3/3 models identified this as
  the biggest flaw in the spec/plan — conformance ≠ correctness)
- Full multi-model debate for ALL per-stage reviews (rejected by 2/3 models as
  wasteful for mechanical edits; GPT-5.4 favored this but acknowledged adaptive
  as a reasonable middle ground)
- Manual escalation by the developer (rejected: defeats automation; the system
  should detect when it needs more eyes)

---

### R-011: Async worker coroutines with native messages array context

**Decision**: Workers are **async coroutines** (`asyncio.Task`), not OS threads.
Each worker maintains a growing `messages[]` array as its primary context — the
native multi-turn conversation format supported by all provider APIs. Blocking
`provider.generate_content()` calls are offloaded via `asyncio.to_thread()` to a
shared `ThreadPoolExecutor`, borrowing a thread only for the API call duration.

**Rationale**: The debate maintains context across rounds for each model. Each
LLM API is stateless — context is provided by sending the full messages array
with every call. The worker holds this array as a local variable:

```
Worker A (async coroutine):
  messages = []

  # Round 1
  messages.append({role: "system", content: tool_system_prompt})
  messages.append({role: "user", content: original_prompt})
  response = await asyncio.to_thread(provider.generate_content, messages)
  messages.append({role: "assistant", content: response})

  # Round 2
  messages.append({role: "user", content: round2_adversarial_prompt})
  response = await asyncio.to_thread(provider.generate_content, messages)
  messages.append({role: "assistant", content: response})

  # Follow-up (later)
  messages.append({role: "user", content: follow_up_prompt})
  response = await asyncio.to_thread(provider.generate_content, messages)
  messages.append({role: "assistant", content: response})
```

The LLM sees a coherent multi-turn conversation because the full history is
sent each time. No tricks — this is the native pattern every provider supports.

**Why async coroutines, not OS threads:**
- `asyncio.Barrier`/`asyncio.Event` work natively (no `call_soon_threadsafe`)
- Idle workers cost nothing — suspended coroutines, no OS threads consumed
- 20 sessions × 3 workers = 60 coroutines (lightweight) vs 60 OS threads
- `ThreadPoolExecutor` is only for the ~3-15s blocking API calls, not worker
  lifetime. Peak thread usage: 3 per active debate (one per model per round)
- Clean lifecycle: `asyncio.Task` cancelled on session destroy

**Context window management:**
- For typical debates (2 rounds + a few follow-ups): messages array fits easily
  in any model's context (128K-1M). No compression needed.
- When `messages[]` token count approaches 70% of model's context window
  (`should_compress()`): oldest messages are compressed into a structured
  summary (pinned facts + working summary), inserted as a single message
  replacing the compressed messages. Recent exchanges kept verbatim.
- Compression is provider-aware: Gemini (1M) compresses around follow-up ~50,
  GPT (128K) around follow-up ~20. Each worker compresses independently.

**Thread pool sizing**: `ThreadPoolExecutor(max_workers=SESSION_MAX_CONCURRENT
* 3 + 10)` — handles burst concurrency when multiple sessions run rounds
simultaneously. Threads are short-lived (API call duration only).

**Alternatives considered**:
- OS threads per worker via ThreadPoolExecutor (rejected: asyncio primitives
  can't be used across threads without `call_soon_threadsafe`; OS threads are
  expensive for idle workers; lifecycle harder to manage)
- Per-round `asyncio.gather()` with `asyncio.to_thread()` (rejected: no context
  locality — must serialize/deserialize ModelState between rounds; thread churn;
  awkward follow-up model)
- Async provider implementations (rejected: all current providers are synchronous;
  rewriting them is out of scope)

---

### R-012: Round 2 prompt composition with existing systemprompts

**Decision**: Create a dedicated `debate/prompts.py` module with a Round 2 prompt
template that wraps Round 1 responses as "claims to evaluate" while preserving the
original per-tool system prompt unchanged.

**Rationale**: The existing `systemprompts/` directory contains sophisticated,
tool-specific prompt engineering (7-dimension evaluation frameworks in consensus,
stance injection, severity tagging in codereview, hypothesis generation in debug).
Round 2 must compose with these — not replace them.

The composition strategy:
1. **System prompt**: Same per-tool system prompt as Round 1 (unchanged)
2. **User prompt for Round 2**: A template that includes:
   - The original analysis request (same as Round 1)
   - A clearly delimited section: "The following are analyses from other models.
     Treat each as a claim to be critically evaluated, not trusted input."
   - Each Round 1 response labeled by alias (not model name, to avoid brand bias)
   - Explicit instruction: "Identify what each analysis got right, what it missed,
     what you disagree with, and revise your recommendation."
3. **Suppression**: Round 2 prompt explicitly instructs the model NOT to output
   CONTEXT_REQUESTS or ESCALATION_SIGNAL blocks — those are Round 1 only

This preserves the per-tool prompt's evaluation framework while adding the
adversarial layer. The system prompt sets the analytical lens (debug, codereview,
etc.); the Round 2 user prompt adds the debate dimension.

For variable participant count (2/3 models in Round 1 due to partial failure):
the template dynamically includes only the responses that succeeded, with a note:
"Note: {N} of {M} requested analysts responded. Missing: {alias} ({reason})."

**Alternatives considered**:
- Augmenting the system prompt for Round 2 (rejected: existing systemprompts are
  carefully tuned; modifying them risks breaking tool-specific evaluation quality)
- Per-tool Round 2 templates (rejected: the adversarial framing is the same across
  tools; only the system prompt differs, and that's already per-tool)
- Including model names in Round 2 (rejected: may introduce brand bias — "Claude
  said X" carries different weight than "Analyst B said X")
