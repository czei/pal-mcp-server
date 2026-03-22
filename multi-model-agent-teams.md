# Multi-Model Agent Teams: Architecture Exploration

**Status:** Potential / Research — **Recommended: Fork PAL/Zen (Option B-fork)**
**Date:** 2026-03-21 (updated with corrected findings)
**Context:** Professional tooling — leveraging multiple LLMs with different training data in agent team workflows for maximum problem-solving quality. Cost is not a constraint; the goal is the best possible outcome from every model interaction.

---

## Problem Statement

Current AI coding agent teams (including Claude Code's agent teams) spawn multiple instances of the same LLM. This provides parallelism but not cognitive diversity — all agents share the same training data, reasoning patterns, and blind spots.

A single LLM debugging a problem will find *some* root causes. Three LLMs debugging the same problem simultaneously — then arguing about whose hypothesis is correct — will collectively find more. The same applies to designing code, planning implementations, reviewing changes, and every other decision-making activity. Different models have different training data, different architectures, and different blind spots. When they disagree, that disagreement is signal.

### Core Principle: Adaptive Review Intensity

> **REVISED 2026-03-22** based on 3-model consensus review (GPT-5.4, Gemini 2.5 Pro,
> Claude Opus 4.6 — unanimous at 8/10 confidence). The original "Heavy Debate Upstream,
> Light Checks Downstream" principle was a rigid binary that incorrectly equated
> conformance with correctness. Replaced with adaptive escalation.

The wrong approach is uniform multi-model review at every stage. But the *also* wrong
approach is assuming that conformance checks are sufficient for implementation stages.
**Conformance ≠ correctness.** Code that faithfully implements a design can still contain
race conditions, off-by-one errors, API misuse, and edge cases that no amount of upstream
design debate could predict. Implementation is a discovery process — more than half of
real-world project time is spent finding bugs in implementations that follow specs.

**The fix: invest multi-model debate at design stages, use adaptive escalation during
implementation stages (single-model review that auto-promotes to full debate when
confidence is low or complexity is high), and always do a final full debate.**

| Activity | Multi-model debate? | Why |
|----------|---------------------|-----|
| **Specifying** requirements | **FULL DEBATE** | Wrong requirements waste everything downstream; different models catch different ambiguities and missing cases |
| **Designing** code (approach, API shape, patterns) | **FULL DEBATE** | Design errors cascade; three models proposing different architectures surfaces tradeoffs none would find alone |
| **Debugging** (root cause hypotheses) | **FULL DEBATE** | Each model notices different things; parallel investigation costs no extra wall-clock time |
| **Planning** (implementation steps, sequencing) | **FULL DEBATE** | Models disagree on what's risky, what to do first, what to defer |
| **Task breakdown** (derived from plan) | LIGHT — single model | Mostly mechanical derivation from the debated plan; flag anomalies only |
| **Code implementation** (writing/editing files) | NO — single model executes | One model implements the consensus design. Mechanical execution doesn't benefit from debate. |
| **Per-stage code review** | **ADAPTIVE** — single model with escalation | Default: single-model review with confidence/escalation signal. Auto-promotes to FULL DEBATE when confidence low, complexity high, or anomalies flagged. Conformance ≠ correctness — implementations reveal bugs no design debate could predict. |
| **Final code review** (complete change set) | **FULL DEBATE** | Last gate before commit; catches integration issues across stages |
| **Running** builds, tests, git operations | NO | Deterministic operations, no judgment involved |

### Why This Is Faster Than Uniform Review

**Current workflow** (uniform multi-model review at every stage):
```
specify → FULL review → plan → FULL review → tasks → FULL review
  → code stage 1 → FULL review → code stage 2 → FULL review
  → code stage 3 → FULL review

6 stages × ~20-30s full review = ~2-3 min review time
Plus rework cycles when late-stage reviews catch design issues
```

**Proposed workflow** (heavy upstream, light downstream):
```
specify → FULL DEBATE (~15s)
  → plan → FULL DEBATE (~15s)
    → tasks → light check (~5s)
      → code stage 1 → conformance check (~5s)
        → code stage 2 → conformance check (~5s)
          → code stage 3 → conformance check (~5s)
            → FINAL FULL DEBATE on complete change (~15s)

Total: ~65s review time
Far fewer rework cycles because design issues caught before code was written
```

The bigger time savings isn't review duration — it's **fewer rework cycles**. A design
flaw caught in spec debate costs 15 seconds to fix. The same flaw caught in stage-3
code review costs minutes of rework across all prior stages.

### The Three Levels of Review

**Design review** (multi-model debate): "Is this the right approach? What are we missing?
What could go wrong?" — requires diverse perspectives, benefits from adversarial critique.

**Adaptive implementation review** (single-model with escalation): "Does this code
implement the agreed design? Are there bugs, race conditions, edge cases, or API misuse
that the design couldn't anticipate?" — a single model does the initial review AND
outputs a structured confidence/escalation signal. If the reviewer flags low confidence,
high complexity, or anomalies it can't resolve alone, the system auto-promotes to full
multi-model debate. This catches the critical category of bugs where code faithfully
implements a design but the implementation itself is flawed.

**Mechanical check** (single-model, no escalation): Renames, docs updates, simple
wiring, generated code refreshes. No judgment required.

> **Why not just "conformance checks"?** The original principle assumed that if code
> conforms to the plan, it works. This is a false equivalence. Designs operate at a
> different abstraction level than implementations. A design saying "use a token bucket
> rate limiter" can be correct while the implementation has an off-by-one in the refill
> calculation. More than half of real engineering time is spent finding bugs in
> implementations that follow specs. Adaptive escalation catches these early.

### Why Different Models Find Different Things

- **Different training data** — different corpora emphasize different APIs, patterns, and failure modes
- **Different architectures** — chain-of-thought (o1/o3) vs structured reasoning (Claude) vs multimodal (Gemini) produce genuinely different reasoning patterns
- **Different blind spots** — when three models all agree, confidence is high; when they disagree, the disagreement points to something worth investigating

## Current State

### What We Already Have

**PAL/Zen MCP tools** already provide multi-model access:
- `mcp__pal__consensus` queries multiple models and synthesizes responses
- `mcp__pal__codereview`, `debug`, `planner`, etc. route to various models
- `mcp__pal__listmodels` shows available models

**Limitation:** PAL/Zen is request-response (stateless). Each call is independent — there is no persistent agent context, no conversation history, no multi-turn reasoning within a single model agent.

### Claude Code Agent Teams

- Each teammate gets its own isolated context window
- Communication via `message` / `broadcast`
- Shared task list for coordination
- All teammates are Claude instances — no model diversity

## Options Evaluated

### Option A: Fork/Modify Opencode (Open-Source Coding Agent)

**What it provides:**
- Multi-provider support out of the box (Anthropic, OpenAI, Google, Bedrock, Ollama)
- Its own agent loop with tool use
- Go codebase, well-structured, actively maintained

**What would need to be built:**
- Agent team coordination (it's single-agent today)
- Message passing between agent instances
- Shared task management
- Orchestrator for work assignment

**Assessment: Not recommended.** This replaces Claude Code rather than extending it. You lose Claude Code's mature tool use, MCP integration, CLAUDE.md context loading, permission model, and the existing PAL/Zen integration. You'd be building a competing system, not enhancing the current one.

### Option B: Fork PAL/Zen for Deeper Agent Team Integration (NOW RECOMMENDED)

> **CORRECTION (2026-03-21):** The original assessment below was based on false assumptions
> that PAL/Zen was a hosted service with opaque internals. Investigation revealed that
> PAL/Zen is 100% open source (Apache 2.0), runs entirely locally via stdio, and the full
> codebase — including all prompt engineering and provider abstractions — is on disk. The
> original "risky" assessment is retracted. See "Corrected Findings" section below.

**What it provides:**
- Already integrated with Claude Code via MCP
- Already routes to 7+ providers (OpenAI, Gemini, OpenRouter, Azure, xAI, Ollama, custom)
- ~12,866 lines of tested tool implementations (consensus, codereview, debug, planner, etc.)
- ~15 prompt engineering files with sophisticated structured workflows
- Clean provider abstraction (`ModelProvider` ABC with `ModelCapabilities`, `ModelResponse`)
- Apache 2.0 license — derivative works explicitly permitted
- Full codebase at `~/.claude-mcp-servers/zen-mcp-server/`

**What would need to be built:**
- **Multi-model debate layer** — convert existing single-model tools (debug, codereview, planner, etc.) into multi-model debate tools where 3+ models argue in parallel, then their disagreements are synthesized. The existing prompt engineering per tool becomes the *task-specific framing* for the debate.
- **Request-as-output schema** — agents return analysis + structured `context_requests[]` listing files/artifacts they wish they'd had. Controller gathers between Round 1 and Round 2. (See Context Management Consensus section.)
- **Session management with stratified memory** — per-model state (pinned facts, working summary, recent verbatim, checkpoints) + shared context (code files, gathered artifacts, round responses). MCP server holds sessions in-memory; reconstructs message arrays per API call. (See "How Context Is Maintained Across LLMs" section.)
- **Provider-aware compression** — different context limits per provider (128K-1M) require per-model compression thresholds. Pinned facts never compress; working summary tightens via constrained LLM summarization (structured fields only, prevents drift).
- Evaluation/metrics logger (JSONL)
- `follow_up` tool with session context injection
- `compare_models` tool for evaluation queries

**Assessment: RECOMMENDED.** Fork inherits ~16,500 lines of prompt engineering and provider
abstraction. The key architectural change is making multi-model debate the default for all
decision-making tools, not just `consensus`. The existing per-tool prompts (debug, codereview,
planner, etc.) become the structured framing that each model receives — same prompt, all models,
let them argue. Session state lives in the MCP server process, not in any LLM — every provider
API call is stateless, but the server reconstructs context from stored state.

### Option C: New MCP Server as Multi-Model Agent Coordinator (Superseded by Option B)

**What it provides:**
- Native integration with Claude Code via MCP (no fork needed)
- Claude stays as orchestrator (proven, excellent at tool use)
- Borrow provider abstraction from Opencode (~20% of its codebase)
- Build only the novel pieces: persistent context + coordination

**What would need to be built:**
- Provider abstraction layer (borrow from Opencode's Go provider configs)
- Stateful agent sessions with per-model conversation history
- MCP tool interface for Claude Code to interact with model agents
- Context window management per provider (different limits)
- Capability profiles per model

## Option C Detailed Design: `multi-model-mcp` Server (Reference — Fork approach preferred)

> **NOTE:** This detailed design was produced before discovering PAL/Zen is fully forkable.
> The session management, evaluation, and tool schema designs below remain valid and should
> be applied to the PAL/Zen fork. The provider abstraction and MCP infrastructure sections
> are superseded — PAL/Zen already has these built.

### Architecture Overview

```
Claude Code ←── stdio ──→ multi-model-mcp server (TypeScript)
                            ├── Provider Adapters
                            │     ├── Anthropic  (@anthropic-ai/sdk)
                            │     ├── OpenAI     (openai)
                            │     └── Google     (@google/generative-ai)
                            ├── Session Manager
                            │     ├── Rolling summaries (bounded memory)
                            │     └── Sliding window (last 3 exchanges)
                            ├── 6 MCP Tools
                            │     ├── multi_query    (parallel fan-out)
                            │     ├── follow_up      (stateful continuation)
                            │     ├── synthesize     (cross-model synthesis)
                            │     ├── compare_models (evaluation queries)
                            │     ├── list_sessions  (session inventory)
                            │     └── destroy_session
                            └── Evaluation Logger (JSONL + aggregation)

Complements PAL/Zen (kept for quick one-shot queries)
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | TypeScript | Official MCP SDK + all 3 provider SDKs in npm |
| Transport | stdio | Local child process, no network complexity |
| State model | Rolling summary + 3 recent exchanges | Bounded memory, not raw transcript growth |
| Summary strategy | LLM-assisted (strongest available model) | Best summary quality for session continuity |
| Tool use | Text-only Phase 1 | Defer hardest problem (format translation) |
| Evaluation | JSONL from day 1 | Data-driven model quality optimization |
| Error handling | Partial failure + circuit breakers | One provider down doesn't kill the request |
| PAL/Zen | Fork and extend | Multi-model debate becomes the default for design stages |
| Debate strategy | Adaptive intensity | Full multi-model debate for spec/plan/debug; adaptive single-model review with auto-escalation for implementation stages (conformance ≠ correctness); final multi-model review on complete change |

**1. Claude as orchestrator, not participant.** Claude Code's agent loop handles tool use, file editing, and project context. Model agents are advisory — they analyze, review, and provide perspectives. Claude synthesizes and executes. One model writes code; multiple models decide *what* code to write.

**2. Thin-state sessions, not full transcripts.** Each session stores: pinned facts (immutable), working summary (compressed), last 2-3 verbatim exchanges, and named checkpoints. Stratified compression is task-aware and provider-aware.

**3. Normalize at contract level, not mechanism level.** Don't make all models use the same tools — require the same output format ("enumerate risks", "produce a patch plan").

**4. Adaptive review intensity.** Multi-model debate for design decisions (specify, plan, debug, architecture). Adaptive single-model review with auto-escalation for implementation stages — the reviewer outputs confidence/complexity signals, and the system promotes to full multi-model debate when confidence is low or anomalies are flagged. This catches both design issues (upstream debate) AND implementation bugs (adaptive escalation) that conformance-only checks would miss. Final multi-model review on the complete change as the last gate.

**5. Evaluation from day 1.** Every interaction logs model, latency, tokens, task_type, and quality signals. The `compare_models` tool queries this data to understand which models produce the best results for which task types — optimizing for quality, not cost.

### Project Structure

```
multi-model-mcp/
├── package.json
├── tsconfig.json
├── config.example.yaml
├── src/
│   ├── index.ts                    # MCP server entry point, tool registration
│   ├── config/
│   │   ├── loader.ts               # YAML config loading, env var resolution
│   │   └── schema.ts               # Config types + validation
│   ├── providers/
│   │   ├── types.ts                # ProviderAdapter interface + response types
│   │   ├── registry.ts             # Provider registry (name → adapter)
│   │   ├── anthropic.ts            # Anthropic adapter
│   │   ├── openai.ts               # OpenAI adapter
│   │   └── google.ts               # Google adapter
│   ├── sessions/
│   │   ├── types.ts                # Session, Checkpoint, Exchange types
│   │   ├── manager.ts              # Session lifecycle (create/get/destroy/gc)
│   │   ├── memory.ts               # Rolling summary + sliding window logic
│   │   └── store.ts                # In-memory store (SQLite later)
│   ├── tools/
│   │   ├── multi-query.ts          # Parallel multi-model query
│   │   ├── follow-up.ts            # Stateful follow-up with context
│   │   ├── synthesize.ts           # Cross-model synthesis
│   │   ├── compare-models.ts       # Evaluation metric queries
│   │   ├── list-sessions.ts        # Session inventory
│   │   ├── destroy-session.ts      # Session cleanup
│   │   └── schemas.ts              # JSON Schema definitions for all tools
│   ├── evaluation/
│   │   ├── logger.ts               # Structured JSONL event logging
│   │   ├── metrics.ts              # Cost estimation, token counting, latency
│   │   └── reporter.ts             # Aggregation queries for compare_models
│   └── utils/
│       ├── rate-limiter.ts          # Per-provider token bucket
│       ├── circuit-breaker.ts       # Provider health + fallback
│       └── errors.ts                # Error types and formatting
├── test/
│   ├── providers/                   # Mocked SDK unit tests
│   ├── sessions/                    # Session management tests
│   ├── tools/                       # Tool integration tests
│   └── fixtures/                    # Mock responses, sample configs
└── logs/                            # JSONL evaluation logs (gitignored)
```

### Provider Abstraction Layer

```typescript
// src/providers/types.ts
interface ProviderAdapter {
  readonly name: string;
  readonly capabilities: ModelCapabilities;

  chat(request: ChatRequest): Promise<ChatResponse>;
  streamChat?(request: ChatRequest): AsyncIterable<ChatChunk>;
  estimateCost(inputTokens: number, outputTokens: number): number;
  maxContextTokens(): number;
}

interface ChatRequest {
  systemPrompt?: string;
  messages: Message[];
  temperature?: number;
  maxTokens?: number;
  responseFormat?: 'text' | 'json';
  jsonSchema?: object;
}

interface ChatResponse {
  content: string;
  inputTokens: number;
  outputTokens: number;
  latencyMs: number;
  model: string;
  finishReason: string;
}

interface ModelCapabilities {
  maxContext: number;
  supportsJson: boolean;
  supportsStreaming: boolean;
  costPer1kInput: number;
  costPer1kOutput: number;
  tags: string[];    // ['code-strong', 'security', 'long-context']
}
```

Each adapter (anthropic.ts, openai.ts, google.ts) implements `ProviderAdapter` and translates `ChatRequest` to native SDK calls. This is the ONLY place provider-specific code lives.

### Session Management

> **Updated 2026-03-22** based on context management consensus. See
> "Context Management Consensus" and "How Context Is Maintained Across LLMs"
> sections for the full architecture and implementation details.

```typescript
// src/sessions/types.ts — per-model state within a debate session
interface ModelState {
  providerName: string;
  modelId: string;
  maxContext: number;              // Provider-specific limit

  // Stratified memory (task-aware compression)
  pinnedFacts: PinnedFact[];      // Immutable — never compressed
  workingSummary: string;         // Compressed narrative, updated per exchange
  recentExchanges: Exchange[];    // Last 2-3 verbatim (sliding window)
  checkpoints: Checkpoint[];      // Named snapshots after synthesis points

  totalExchangeCount: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  totalCostEstimate: number;
}

// Shared across all models in a session
interface SharedContext {
  originalPrompt: string;
  codeFiles: Attachment[];
  round1Responses: Record<string, string>;  // alias → full verbatim
  gatheredArtifacts: Attachment[];           // From context_requests
}

interface DebateSession {
  id: string;
  taskType: string;               // "debug", "design", "review", "plan"
  models: Record<string, ModelState>;  // alias → per-model state
  sharedContext: SharedContext;
  createdAt: Date;
  lastActiveAt: Date;
}

interface PinnedFact {
  content: string;
  source: string;                 // Which model/round established this
  category: 'hypothesis' | 'decision' | 'constraint' | 'finding';
  status: 'active' | 'confirmed' | 'rejected';
}
```

**Context construction for each API call** (built fresh per model from stored state):
```
[System prompt — task-specific framing from PAL/Zen prompt engineering]
[Pinned facts — structured, always included, never compressed]
[Working summary — compressed narrative of older exchanges]
[Last 2-3 verbatim exchanges — uncompressed]
[Shared context — code files, gathered artifacts]
[New prompt]
```

**Summary strategy:**
- *Template* (fallback): Deterministic extraction of code blocks, file paths, error messages, decisions, questions. Fast, no hallucination risk.
- *LLM-assisted* (default): Use the strongest available model to compress the oldest exchange into structured field updates (hypothesis status, decisions made, open questions). Constrained to update structured fields rather than rewriting freeform prose — prevents summary drift. Config flag: `summary_strategy: "template" | "llm"`. Default: `"llm"`.

**Compression is provider-aware**: Gemini (1M context) compresses much later than Claude (200K). Each model gets the richest history its context window can hold.

### MCP Tool Definitions

**Tool 1: `multi_query`** — Parallel multi-model query
```
Input:  prompt, models[{alias, model, system_prompt?, temperature?}],
        attachments[]?, response_format?, task_type?
Output: session_id, responses[{alias, model, content, latency_ms,
        tokens:{input,output}, cost_estimate, status}],
        warnings[{alias, model, error, message}]?
```
Creates a session with one agent per model. Fans out prompt in parallel with independent timeouts. Returns all successful responses + warnings for failures (partial failure is OK).

**Tool 2: `follow_up`** — Stateful continuation
```
Input:  session_id, alias, prompt, attachments[]?, checkpoint_name?
Output: alias, model, content, latency_ms, tokens, cost_estimate,
        session_exchanges_total, summary_included
```
Sends a follow-up to a specific agent within an existing session. The agent receives its rolling summary + recent exchanges + the new prompt. Optionally creates a named checkpoint.

**Tool 3: `synthesize`** — Cross-model synthesis
```
Input:  responses[{alias, content}], rubric?, synthesizer_model?
Output: synthesis, agreement_points[], disagreement_points[],
        recommendations[], synthesizer_model
```
Uses a model (default: strongest available) to synthesize multiple responses into structured analysis with agreement/disagreement/recommendations.

**Tool 4: `compare_models`** — Evaluation queries
```
Input:  task_type?, model?, since?, group_by?
Output: comparisons[{model, task_type?, query_count, avg_latency_ms,
        total_tokens, avg_tokens_per_response, success_rate,
        follow_up_rate, avg_follow_up_depth}]
```
Queries JSONL evaluation logs. Aggregates by model, task_type, or both. Filterable by date.

**Tool 5: `list_sessions`** — Session inventory
```
Input:  active_only?
Output: sessions[{session_id, created_at, agents[{alias, model,
        exchange_count, total_cost}]}]
```

**Tool 6: `destroy_session`** — Cleanup
```
Input:  session_id
Output: { destroyed: true, evaluation_data_preserved: true }
```

### Configuration

```yaml
# config.yaml
providers:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    default_model: claude-sonnet-4-6
    rate_limit_rpm: 60
    timeout_ms: 30000
  openai:
    api_key: ${OPENAI_API_KEY}
    default_model: gpt-4o
    rate_limit_rpm: 60
    timeout_ms: 30000
  google:
    api_key: ${GOOGLE_AI_API_KEY}
    default_model: gemini-2.5-pro
    rate_limit_rpm: 60
    timeout_ms: 30000

models:
  claude-sonnet-4-6:
    provider: anthropic
    max_context: 200000
    cost_per_1k_input: 0.003
    cost_per_1k_output: 0.015
    tags: [code-strong, security, structured-output]
  gpt-4o:
    provider: openai
    max_context: 128000
    cost_per_1k_input: 0.0025
    cost_per_1k_output: 0.010
    tags: [code-strong, general, fast]
  gemini-2.5-pro:
    provider: google
    max_context: 1048576
    cost_per_1k_input: 0.00125
    cost_per_1k_output: 0.005
    tags: [long-context, code-strong, multimodal]

sessions:
  max_recent_exchanges: 3
  summary_strategy: llm
  summary_llm_model: gpt-4o           # Use strongest model for best summary quality
  gc_idle_minutes: 60
  max_concurrent_sessions: 20

evaluation:
  log_dir: ./logs
  log_format: jsonl
  retention_days: 30

circuit_breaker:
  failure_threshold: 3
  reset_timeout_ms: 60000
```

### Claude Code Integration

```json
// ~/.claude/settings.json (or project .claude/settings.json)
{
  "mcpServers": {
    "multi-model": {
      "command": "npx",
      "args": ["tsx", "/path/to/multi-model-mcp/src/index.ts"],
      "env": {
        "ANTHROPIC_API_KEY": "...",
        "OPENAI_API_KEY": "...",
        "GOOGLE_AI_API_KEY": "..."
      }
    }
  }
}
```

### Error Handling and Degradation

**Error hierarchy:**
- `ProviderUnavailableError` — API key missing, network down, circuit open
- `ProviderRateLimitError` — rate limit hit, includes retry-after
- `ProviderTimeoutError` — exceeded timeout_ms
- `ProviderContentFilterError` — model refused prompt
- `SessionNotFoundError` — invalid session_id
- `ConfigurationError` — invalid config.yaml

**Degradation strategy for `multi_query`:**
1. One provider fails → return successful responses + `warnings[]` noting failures
2. All providers fail → structured error suggesting PAL/Zen fallback
3. Circuit breaker prevents retrying consistently-failing providers

**Rate limiting:** Token bucket per provider. Requests queue when bucket empty, with max wait. Exceeded → immediate `ProviderRateLimitError`.

### Evaluation Infrastructure

Every model interaction produces a JSONL log entry:
```json
{
  "timestamp": "2026-03-21T14:30:00Z",
  "event": "model_response",
  "session_id": "abc-123",
  "alias": "analyst",
  "model": "gpt-4o",
  "provider": "openai",
  "task_type": "code-review",
  "input_tokens": 2450,
  "output_tokens": 890,
  "latency_ms": 3200,
  "status": "success",
  "is_follow_up": false,
  "exchange_number": 1,
  "follow_up_requested": false,
  "user_accepted": null
}
```

The `compare_models` tool reads and aggregates these logs — this is the "evaluation from day 1" infrastructure. Key quality signals: which model's responses lead to follow-ups (indicating depth/value), which get accepted by users, and which task types each model excels at.

### Usage Examples

**Multi-model code review:**
```javascript
multi_query({
  prompt: "Review this code for correctness, security, and performance:\n\n```java\n...\n```",
  models: [
    { alias: "correctness", model: "gpt-4o",
      system_prompt: "Senior Java engineer focused on correctness and edge cases." },
    { alias: "security", model: "claude-sonnet-4-6",
      system_prompt: "Security auditor. Focus on OWASP top 10, injection, auth bypass." },
    { alias: "performance", model: "gemini-2.5-pro",
      system_prompt: "Performance engineer. Focus on complexity, memory leaks, hot paths." }
  ],
  task_type: "code-review"
})
// → 3 independent reviews returned in parallel
```

**Debugging with follow-up:**
```javascript
// After initial multi_query, user says "GPT's race condition theory looks right"
follow_up({
  session_id: "abc-123",
  alias: "correctness",
  prompt: "Your race condition theory is promising. Here's the thread pool config and lock code. Trace the exact failure sequence:\n\n[code]"
})
// → Model receives its prior analysis (via summary) + new context
```

**Evaluation after a week of use:**
```javascript
compare_models({ group_by: "model_and_task_type", since: "2026-03-14" })
// → GPT produces the most actionable code review findings (highest follow-up rate),
//   Claude catches the most security issues (highest acceptance rate on security tasks),
//   Gemini provides the deepest architecture analysis (longest follow-up chains)
```

### Testing Strategy

**Unit tests:**
- Provider adapters (mocked SDKs) — verify request translation + response parsing
- Session management — creation, summary generation, sliding window, GC, checkpoints
- Config loader — env var resolution, validation, error cases

**Integration tests:**
- `multi_query` with mocked providers — parallel execution, partial failure
- `follow_up` with session state — context carries through
- `compare_models` with seeded JSONL data

**End-to-end test:**
- Start MCP server via stdio, call multi_query → follow_up → synthesize → compare_models → destroy_session
- Requires real API keys (skipped in CI without them)

### Build Sequence

```
Step 1:  Project scaffolding (package.json, tsconfig, config schema)
Step 2:  Config loader with env var resolution
Step 3:  Provider types + Anthropic adapter
Step 4:  OpenAI adapter
Step 5:  Google adapter
Step 6:  Provider registry + unit tests for all 3
Step 7:  Session types + in-memory store
Step 8:  Memory module (rolling summary, sliding window)
Step 9:  Session manager (lifecycle, GC)
Step 10: Evaluation logger (JSONL writer)
Step 11: Session + evaluation unit tests
Step 12: MCP server entry point (index.ts, stdio transport)
Step 13: multi_query tool (parallel fan-out, partial failure)
Step 14: follow_up tool (session lookup, context construction)
Step 15: synthesize tool
Step 16: compare_models tool (JSONL reader + aggregation)
Step 17: list_sessions + destroy_session tools
Step 18: Rate limiter + circuit breaker
Step 19: Integration tests + end-to-end test
Step 20: Claude Code integration testing (real usage)
Step 21: config.example.yaml + README
Step 22: Bug fixes from real usage
```

### Phase 2+ Evolution Path (Designed For, Not Built Now)

The Phase 1 architecture explicitly supports expansion without rewriting:

**Phase 2 — Tool-capable agents:**
- Add `tools` array to `ProviderAdapter.chat()` request
- Add `src/tools/translation/` with per-provider tool schema translators
- Capability profiles gate which models receive tools
- `multi_query` and `follow_up` gain optional `allow_tools` parameter

**Phase 3 — Agent coordination:**
- `SharedBoard` — key-value store visible to all session agents
- `route_to_best(task_type, prompt)` — uses compare_models data for auto-selection
- Agent-to-agent messaging (A's output → B's input)

**Phase 4 — Learning:**
- Reads evaluation logs to build model-task affinity scores
- Auto-updates routing weights over time
- User override always available

None of these require changing Phase 1 tool schemas — they add new tools and enrich existing ones with optional parameters.

## Complementary Technique: Prompt-Level Diversity (Stacks with Multi-Model)

Multi-model debate provides diversity from different training data. Prompt-level diversity
adds a second axis — different analytical lenses on top of different models. These stack.

**For the multi-model debate layer (PAL fork):**
All models receive the same task-specific prompt (debug prompt, review prompt, etc.), but
the fork can optionally add diversity parameters:
1. **Different temperatures** — conservative (t=0.1) vs creative (t=0.8) for non-Claude models. Available because the PAL fork calls provider APIs directly, where temperature is a standard parameter.
2. **Different emphasis instructions** — appended to the shared prompt: "pay special attention to thread safety" vs "pay special attention to error handling." This is lighter than full role assignment — it nudges without pretending to know which model is best at what.

> **Note:** Claude Code does NOT expose temperature, top_p, or other inference parameters.
> The only inference control available for Claude teammates is effort level (thinking budget).
> Temperature control is only available for non-Claude models called through the PAL fork's
> provider APIs.

**For Claude Code teammates (execution agents):**
1. **Different spawn prompts** — give each teammate a different implementation focus (one writes code, one writes tests, one does integration)
2. **Different effort levels** — low/medium/high/max controls reasoning depth (this is NOT temperature — it controls thinking budget)

The key insight: prompt-level diversity is a *supplement* to model-level diversity, not a
substitute. Three instances of the same model with different prompts produce less diversity
than three different models with the same prompt. Use both when maximum coverage matters.

## Open Questions

1. ~~**Licensing:** Can Opencode's provider layer be referenced?~~ **RESOLVED** — PAL/Zen is Apache 2.0, fork directly instead of borrowing from Opencode
2. **Provider account management:** Enterprise API accounts with appropriate rate limits across all providers. Rate limits, not cost, are the practical constraint at scale.
3. **Context window divergence:** Models have different limits (128K vs 200K vs 1M) — session manager must track per-model usage. PAL/Zen's `ModelCapabilities` already tracks `max_context` per model.
4. **Summary quality:** LLM-assisted summarization is the default, but which model produces the best summaries? May vary by domain. Evaluate strongest models (Opus, GPT-4o, Gemini Pro) for summary quality.
5. **Upstream tracking:** How to stay in sync with PAL/Zen upstream while maintaining fork additions? Git rebase strategy vs. maintaining a patch set.
6. **Continuation ID integration:** PAL/Zen already has `continuation_id` for multi-step workflows. How does session state interact with this? Extend the existing mechanism or run parallel?
7. **Fork location:** Separate repo recommended (own release cycle, clear attribution per Apache 2.0 requirements)

## Corrected Findings: PAL/Zen Is Fully Forkable (2026-03-21)

The 4-model consensus and the original Option C design were based on incorrect assumptions
about PAL/Zen's architecture. After direct investigation, all assumptions have been corrected:

### What PAL/Zen Actually Is

| Fact | Detail |
|------|--------|
| **Repository** | [github.com/BeehiveInnovations/pal-mcp-server](https://github.com/BeehiveInnovations/pal-mcp-server) |
| **License** | Apache 2.0 (fork freely, make derivative works) |
| **Language** | Python 3.12 |
| **Local install** | `~/.claude-mcp-servers/zen-mcp-server/` |
| **Transport** | stdio (local child process, NO hosted backend) |
| **Author** | Fahad Gilani / Beehive Innovations |
| **Version** | 9.8.2 |

### Codebase Contents

| Directory | Lines | Contents |
|-----------|-------|----------|
| `tools/` | ~12,866 | Tool implementations — consensus, codereview, debug, planner, thinkdeep, etc. |
| `systemprompts/` | ~15 files | Full prompt engineering per tool with structured evaluation frameworks |
| `providers/` | ~3,690 | Provider abstraction — OpenAI, Gemini, OpenRouter, Azure, xAI, Ollama, custom |
| `server.py` | — | MCP server entry point, tool registration, stdio transport |
| `config.py` | — | API keys, model defaults, provider setup |

### Why the Original "Forking Is Risky" Assessment Was Wrong

| Original Assumption | Reality |
|---------------------|---------|
| "PAL/Zen is a hosted service" | Runs 100% locally via stdio, no remote backend |
| "Internals weren't designed for stateful agents" | True, but adding state is straightforward engineering |
| "Forking means taking on routing infrastructure" | Infrastructure is ~3,690 lines of clean Python with abstract base classes |
| "Prompt engineering is opaque" | All prompts in `systemprompts/` as structured Python templates |
| "License unknown" | Apache 2.0 — derivative works explicitly permitted |

### Prompt Engineering Sophistication

The prompts are substantial and well-engineered. Example from `consensus_prompt.py`:
- 7-dimension evaluation framework (technical feasibility, project suitability, user value, implementation complexity, alternatives, industry perspective, long-term implications)
- Stance injection via `{stance_prompt}` for for/against/neutral perspectives
- File-request protocol for additional context
- Structured output format (verdict, confidence score, key takeaways)
- Anti-anchoring design (prior model responses not shared with subsequent models)

Similar depth exists for codereview (severity tagging, anti-noise prompting), debug (hypothesis generation, reproduction minimization), planner (decomposition, dependency sequencing, scope control), and others.

Rebuilding this from scratch would be feasible but unnecessary — it represents significant iterative tuning that a fork inherits for free.

### Revised Recommendation: Fork PAL/Zen + Add Session State

**Fork the repo and add only what's missing:**

```
pal-mcp-server (fork)
├── [INHERITED] tools/              # 12,866 lines — all existing tools
├── [INHERITED] systemprompts/      # All prompt engineering
├── [INHERITED] providers/          # 7+ provider adapters
├── [INHERITED] server.py           # MCP server infrastructure
├── [INHERITED] config.py           # Configuration management
│
├── [NEW] sessions/                 # Session state management
│   ├── types.py                    # Session, Exchange, Checkpoint types
│   ├── manager.py                  # Lifecycle (create/get/destroy/gc)
│   ├── memory.py                   # Rolling summary + sliding window
│   └── store.py                    # In-memory store (SQLite later)
│
├── [NEW] evaluation/               # Metrics infrastructure
│   ├── logger.py                   # JSONL structured logging
│   ├── metrics.py                  # Quality signals, latency, token tracking
│   └── reporter.py                 # Aggregation for compare_models
│
├── [NEW] tools/follow_up.py        # Stateful follow-up tool
├── [NEW] tools/compare_models.py   # Evaluation query tool
├── [NEW] tools/list_sessions.py    # Session inventory tool
└── [NEW] tools/destroy_session.py  # Session cleanup tool
```

**What the fork inherits (free):**
- All prompt engineering (~15 structured prompt files)
- Provider abstraction for 7+ providers (already built and tested)
- Model capability profiles and intelligent routing
- Auto model selection logic
- MCP server infrastructure (stdio transport, tool registration)
- Configuration management with env var support
- Continuation ID threading (already exists — session state extends this)
- 111 available models via configured providers

**What the fork adds (~4 new files + 4 new tools):**
- Session management with rolling summaries (same design as Option C)
- Evaluation JSONL logging (same design as Option C)
- `follow_up` tool that injects session context before calling existing tools
- `compare_models` tool for evaluation queries

### Fork vs. Option C: Side-by-Side

| Dimension | Fork PAL/Zen | Build Option C from scratch |
|-----------|-------------|---------------------------|
| Prompt engineering | Inherited (15 files) | Rebuild from scratch |
| Provider adapters | Inherited (7+ providers) | Build 3 providers |
| Model routing | Inherited (111 models) | Build basic routing |
| MCP infrastructure | Inherited | Build with MCP SDK |
| Session state | Build it | Build it (same work) |
| Evaluation logging | Build it | Build it (same work) |
| Language | Python (existing) | TypeScript (new) |
| Maintenance | Track upstream + own additions | Own everything |
| Risk | Upstream divergence | No prompt engineering baseline |

**The fork approach does less work and gets more.** The only advantage Option C had was a clean-slate TypeScript codebase — but that advantage is dwarfed by inheriting 16,500+ lines of tested, iteratively-tuned code.

### Key Existing Feature: Continuation IDs

PAL/Zen already has a `continuation_id` threading system for multi-turn conversations (visible in the consensus and planner tools). The session management module extends this concept:
- Current: `continuation_id` maintains context within a single tool's multi-step workflow
- Extended: Sessions maintain context across multiple tool invocations and across different tools

This means the fork isn't fighting the existing architecture — it's extending a pattern that already exists.

---

## Integration with Claude Code Agent Teams

This section addresses how the forked PAL/Zen MCP server actually fits into Claude Code's
existing agent team model.

### How Agent Teams Work Today

```
Lead Agent (Claude)
├── Teammate A (Claude) — isolated context, own tools
├── Teammate B (Claude) — isolated context, own tools
└── Teammate C (Claude) — isolated context, own tools

Communication: message(to), broadcast(all)
Shared state:  task list only
MCP tools:     each teammate loads project MCP servers independently
```

Key properties:
- Each teammate is a separate Claude Code session with its own context window
- Teammates do NOT share conversation history — only explicit messages
- Each teammate loads the same project context (CLAUDE.md, MCP servers, skills)
- **Each teammate independently has access to configured MCP tools**

That last point is critical: if the forked PAL/Zen is configured as an MCP server in
Claude Code's settings, **every teammate in an agent team gets access to multi-model tools**.

### Three Integration Patterns

#### Pattern 1: Lead-Coordinated Multi-Model (Simplest)

The lead agent uses multi-model tools directly. Teammates remain Claude-only workers.

```
Lead Agent (Claude — orchestrator)
│
├── Calls multi_query() for multi-model perspectives
│   ├── GPT response
│   ├── Gemini response
│   └── Claude (via PAL) response
│
├── Calls synthesize() to merge perspectives
│
├── Sends findings to teammates via message()
│
├── Teammate A (Claude) — implements based on lead's synthesized guidance
├── Teammate B (Claude) — implements based on lead's synthesized guidance
└── Teammate C (Claude) — tests/validates
```

**When to use:** Architecture decisions, design reviews, debugging hypotheses —
cases where multi-model diversity informs the plan, but execution is done by Claude
teammates.

**How it works:**
1. Lead receives user request
2. Lead calls `multi_query` to get diverse perspectives (GPT, Gemini, Claude via PAL)
3. Lead calls `synthesize` to produce a unified plan
4. Lead uses `message` to send the plan to Claude teammates
5. Teammates execute (code changes, tests, etc.) using their normal Claude tools
6. Lead calls `follow_up` if a specific model's perspective needs deepening

**Session state benefit:** The lead can `follow_up` with the GPT "analyst" agent later
when teammate A reports a problem — the analyst remembers its earlier analysis.

#### Pattern 2: Teammate-Level Multi-Model (Each Teammate Consults Other LLMs)

Each Claude teammate independently calls multi-model tools for its own subtask.

```
Lead Agent (Claude — orchestrator)
│
├── Teammate "frontend" (Claude)
│   └── Calls multi_query("Review this React component...")
│       ├── GPT response (React expertise)
│       └── Gemini response (performance perspective)
│
├── Teammate "backend" (Claude)
│   └── Calls multi_query("Review this Java service...")
│       ├── GPT response (API design)
│       └── Gemini response (scalability)
│
└── Teammate "security" (Claude)
    └── Calls multi_query("Audit this auth flow...")
        ├── GPT response (OWASP perspective)
        └── Claude-via-PAL response (code analysis)
```

**When to use:** Parallel workstreams where each teammate benefits from diverse input
on its own subtask.

**How it works:**
1. Lead creates team with task assignments
2. Each teammate independently calls multi-model tools as needed
3. Each teammate's multi-model sessions are independent (separate session IDs)
4. Teammates report results back to lead via `message`
5. Lead synthesizes across all teammates

**Session state benefit:** Each teammate maintains its own follow-up sessions with
non-Claude models. The "frontend" teammate can have an ongoing conversation with GPT
about React patterns while the "backend" teammate has a separate conversation about
Java architecture.

**Note:** Each teammate's multi-model calls are independent sessions. The `compare_models`
evaluation tool tracks which models produce the best results for which task types, enabling
continuous refinement of model selection per workstream.

#### Pattern 3: Multi-Model Agents AS Teammates (Replaces Some Claude Instances)

Instead of all-Claude teams, the lead uses the forked PAL/Zen to create persistent
non-Claude agents that function like virtual teammates.

```
Lead Agent (Claude — orchestrator, sole tool user)
│
├── "analyst" session (GPT-4o via PAL fork) — persistent advisory agent
│   └── Lead calls follow_up() to converse over multiple turns
│
├── "reviewer" session (Gemini via PAL fork) — persistent advisory agent
│   └── Lead calls follow_up() to converse over multiple turns
│
├── Teammate A (Claude) — implements code changes
│   └── Has file editing, bash, full Claude Code tool access
│
└── Teammate B (Claude) — tests and validates
    └── Has file editing, bash, full Claude Code tool access
```

**When to use:** When you want persistent non-Claude perspectives alongside Claude
teammates who do the actual code execution.

**How it works:**
1. Lead creates a multi-model session via `multi_query` (creates persistent agents)
2. Lead also spawns Claude teammates for execution work
3. Lead consults non-Claude agents via `follow_up` for analysis/review
4. Lead directs Claude teammates via `message` for implementation
5. Non-Claude agents are advisory (text-only), Claude teammates are execution agents

**Key distinction:** Claude teammates have full tool access (file editing, bash, MCP tools).
Non-Claude model agents (via the PAL fork) are text-in/text-out advisors. The lead bridges
between them — taking advice from multi-model agents and directing execution to Claude
teammates.

**Session state benefit:** This is where persistent session state matters most. The GPT
"analyst" builds understanding across multiple exchanges — it's not starting from scratch
each time the lead asks a follow-up question.

### Which Pattern to Use When

The question isn't just "which coordination pattern?" — it's also "full debate or
conformance check?" The stage in the workflow determines the review weight.

| Scenario | Debate Weight | Pattern | Rationale |
|----------|---------------|---------|-----------|
| Specifying requirements | **FULL DEBATE** | 1 (Lead-coordinated) | Wrong requirements waste everything downstream |
| Designing code / architecture | **FULL DEBATE** | 1 or 3 (persistent for complex designs) | Design errors cascade; this is the highest-leverage debate |
| Debugging root causes | **FULL DEBATE** | 1 (Lead-coordinated) | Different models notice different things in parallel |
| Planning implementation steps | **FULL DEBATE** | 1 (Lead-coordinated) | Models disagree on risk, sequencing, scope |
| Task breakdown (from debated plan) | Light check | Single model | Mostly mechanical derivation; flag anomalies only |
| Per-stage code implementation | None (single model executes) | Teammate writes code | Implements the already-debated design |
| Per-stage code review | **ADAPTIVE** — single + escalation | Single model with auto-promote | Reviewer outputs confidence signal; auto-escalates to full debate when anomalies found (conformance ≠ correctness) |
| Final review (complete change set) | **FULL DEBATE** | 1 (Lead-coordinated) | Last gate; catches integration issues across stages |
| Large feature with workstreams | Mixed | 2 (Teammate-level) | Each workstream does its own upstream debates |
| Long-running work with evolving context | Mixed | 3 (Multi-model as teammates) | Persistent sessions for design; light checks for implementation |

### MCP Configuration for Agent Teams

The forked PAL/Zen server is configured once in Claude Code settings. All agent team
members (lead and teammates) automatically have access:

```json
// ~/.claude/settings.json
{
  "mcpServers": {
    "pal-fork": {
      "command": "python",
      "args": ["/path/to/pal-fork/server.py"],
      "env": {
        "OPENAI_API_KEY": "...",
        "GOOGLE_AI_API_KEY": "...",
        "OPENROUTER_API_KEY": "..."
      }
    }
  }
}
```

**Important:** There is ONE MCP server process shared across all teammates. This means:
- Session state is globally accessible — any teammate can `follow_up` on any session
- The lead can create a multi-model session, then tell a teammate its `session_id`
  via `message`, and the teammate can call `follow_up` on that session
- Evaluation logs capture interactions from all teammates in one place
- Rate limiters apply across the whole team (prevents accidentally DDoSing a provider)

### Session Handoff Between Lead and Teammates

This is a powerful pattern enabled by the shared MCP server:

```
1. Lead calls multi_query("Analyze this auth vulnerability...")
   → Gets session_id: "sec-001"
   → GPT finds a potential CSRF issue
   → Gemini identifies a session fixation risk

2. Lead messages Teammate-Security:
   "Investigate session_id sec-001. The GPT analyst found CSRF at line 45.
    Use follow_up(session_id='sec-001', alias='analyst') to dig deeper
    with the GPT agent, then implement the fix."

3. Teammate-Security calls follow_up(session_id='sec-001', alias='analyst',
   prompt="Show me the exact request flow that enables the CSRF...")
   → GPT analyst responds with full context (it remembers its earlier analysis)

4. Teammate-Security implements the fix, then messages Lead with results
```

The session persists across different Claude Code sessions/teammates because it lives
in the MCP server's memory, not in any individual Claude context window.

### What This Does NOT Do

To be clear about limitations:

1. **Non-Claude models cannot use Claude Code tools.** They cannot edit files, run bash,
   or read the filesystem. They are text-only advisors. Only Claude teammates have tool
   access. This is by design — it avoids the tool use format translation problem.

2. **Non-Claude models don't participate in the message/broadcast system.** They can't
   send messages to Claude teammates or the lead. Communication is always: Claude calls
   the MCP tool → gets response → relays via message if needed.

3. **Non-Claude models don't see the shared task list.** They have no awareness of the
   team structure. They respond to whatever prompt is sent to them.

4. **This is not a symmetric federation.** Claude teammates are first-class agents with
   full tool access and team communication. Non-Claude models are expert consultants that
   Claude agents call on for analysis. The architecture is deliberately asymmetric.

### How This Addresses the Original Problem

The original problem: "all agents share the same training data, reasoning patterns, and
blind spots."

The fork + agent teams solution provides cognitive diversity through three complementary
mechanisms:

1. **Different LLM providers** (via forked PAL multi-model tools) — genuinely different
   training data and reasoning architectures
2. **Persistent advisory sessions** (via fork's session state) — non-Claude models
   accumulate understanding across multiple exchanges
3. **Claude teammate role diversity** (via agent team system prompts) — same model but
   different analytical lenses (already available today)

These stack: a team should have Claude teammates with role-diverse prompts, each
consulting the strongest non-Claude models via the PAL fork, producing diversity at
both the model level and the prompting level. In a professional tooling context where
quality is the priority, always use the most capable model available for each provider —
GPT-4o/5.x for OpenAI, Gemini 2.5 Pro for Google, Claude Opus for Anthropic. Reserve
smaller models only for latency-sensitive operations like session summarization where
speed of the summarization step itself matters more than marginal quality differences.

---

## What Coding Sessions Actually Look Like

The patterns above are abstract. Here are two concrete sessions showing how multi-model
debate works as the **default operating mode** — not an escalation, but how every
substantive task begins.

### The Core Principle: Debate First, Execute After

Every decision-making task — debugging, code design, review, planning — starts with
multiple LLMs analyzing the same problem in parallel and then arguing about the right
approach. Claude, as project manager, reviews the debate and makes the final call. One
model then executes (writes code, applies fixes). The debate costs no extra wall-clock
time because models run in parallel.

**The fork extends PAL/Zen's existing `consensus` pattern to ALL tool types:**

| Current PAL/Zen | Fork |
|-----------------|------|
| `debug` → one model investigates | `debug` → 3 models investigate in parallel, then debate |
| `codereview` → one model reviews | `codereview` → 3 models review in parallel, then debate |
| `planner` → one model plans | `planner` → 3 models plan in parallel, then debate |
| `consensus` → multiple models debate | `consensus` → same (this is already the right pattern) |

The fork essentially makes every tool work like `consensus` does today, with task-specific
prompt framing (the existing per-tool prompts from PAL/Zen become the structured context
each model receives).

---

### Session 1: Debugging — Multi-Model Root Cause Analysis

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: Developer reports a bug → Claude immediately launches debate      │
│ (No single-model investigation first — debate IS the investigation)        │
└─────────────────────────────────────────────────────────────────────────────┘

User:  Cloud browser engines aren't releasing after a load test finishes.
       The engine count stays at max and new tests can't start.
       Here's the diagnostic log from a stuck engine:
       [pastes 40 lines of log output]

Claude (Lead):
  → Reads the log, gathers the relevant source files
  → Immediately launches multi-model debug (this is the default —
    not an escalation)

  → Claude calls debug() [fork version — runs 3 models in parallel]:
    prompt: "Java browser shutdown sequence has a race condition.
             [includes BrowserShutdownManager.java, EngineLifecycleService.java,
              the state machine transitions, and the diagnostic log]
             The Chrome.quit() call can hang indefinitely on headless Linux
             when GPU cleanup stalls. Analyze the code, identify ALL root
             causes (there may be more than one), and propose fixes."

    ── Same prompt, same code, all three models. No role assignment.
       The debug prompt framing (from PAL/Zen's existing debug prompt
       engineering) structures their analysis. ──

┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: Round 1 — Independent analysis (parallel, ~4-8 seconds)           │
│ Each model analyzes the same code independently                            │
└─────────────────────────────────────────────────────────────────────────────┘

  Model A (GPT): Identifies the timeout issue. Also notices the shutdown
    thread pool is shared with the health-check heartbeat — if all pool
    threads block on Chrome.quit(), heartbeats stop, controller marks
    the engine as dead, triggering a second cleanup path that ALSO calls
    Chrome.quit() → deadlock.

  Model B (Gemini): Identifies the timeout issue. Also flags that Chrome
    on headless Linux leaves zombie GPU helper processes after main
    process exits. Process.waitFor() returns but the port is still held
    by the zombie. Recommends killing the process group, not just the PID.

  Model C (Claude/PAL): Identifies the timeout issue. Also finds a state
    machine gap — forced kill should go RUNNING → SHUTTING_DOWN →
    FORCE_KILLED → AVAILABLE, not directly to AVAILABLE, so the RMI
    callback tells the controller it was a forced kill (warning, not error).

  ── All three found the obvious fix. Each also found a DIFFERENT
     secondary issue. This is typical — blind spots don't overlap. ──

┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: Round 2 — Debate (models see each other's Round 1 responses)      │
│ This is where the real value emerges                                       │
└─────────────────────────────────────────────────────────────────────────────┘

  → The fork shares all three Round 1 responses with all three models
    and asks: "Review the other analyses. What did they get right?
    What did they miss? What do you disagree with? Revise your
    recommendation."

  Model A (GPT): "Model B's zombie process point is valid — I missed
    that. But Model C's FORCE_KILLED state is over-engineered. The
    existing SHUTTING_DOWN state can carry a 'forced' flag on the RMI
    callback without adding a new state machine transition. Adding
    states increases the surface area for state transition bugs."

  Model B (Gemini): "Model A's deadlock analysis is correct and
    serious — I missed the shared thread pool. Agree with Model C
    on needing a distinct signal for forced kills, but Model A's
    point about a flag vs. a new state is worth considering.
    HOWEVER — Model A's 'dedicated executor' fix has its own risk:
    two executors means two places where shutdown threads can
    accumulate if the pool isn't sized correctly."

  Model C (Claude/PAL): "Both Model A and B found real issues I missed.
    On the state machine debate: Model A is right that a flag is
    simpler than a new state. I'll revise — use the existing
    SHUTTING_DOWN → AVAILABLE transition but add a 'forceKilled'
    boolean to the RMI callback payload. On Model B's executor
    sizing concern: valid. The dedicated executor should have a
    max pool size equal to the max concurrent browsers per engine."

  ── ROUND 2 FINDINGS:
     - Unanimous: timeout fix needed
     - Unanimous: dedicated shutdown executor (Model A's idea,
       Model B added a sizing constraint, Model C agreed)
     - Unanimous: process group kill (Model B's idea, others agreed)
     - Debated → resolved: flag on RMI callback, NOT new state
       (Model A challenged Model C; Model C conceded)
     - New finding from debate: executor pool sizing must match
       max concurrent browsers (Model B's contribution in Round 2)
  ──

┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: Claude synthesizes and validates                                   │
│ Claude reviews the debate, checks claims against code, decides             │
└─────────────────────────────────────────────────────────────────────────────┘

  → Claude reads the thread pool config — confirms it IS shared
  → Claude reads the process kill code — confirms it kills PID only
  → Claude reads the RMI callback — confirms no forced-kill signal

Claude: Debug debate produced four fixes, all validated against code:

  1. **Timeout + forced kill** on Chrome.quit() (unanimous, Round 1)
  2. **Dedicated shutdown executor**, pool size = max browsers per
     engine (Model A Round 1, Model B added sizing in Round 2)
  3. **Process group kill** via kill -PGID (Model B Round 1, unanimous)
  4. **forceKilled flag** on RMI shutdown callback — NOT a new state
     machine transition (Model C proposed state in Round 1, Model A
     challenged in Round 2, Model C conceded — flag is simpler)

  Note: The debate CHANGED the design. Model C's original proposal
  (new FORCE_KILLED state) was argued down to a simpler flag approach.
  That refinement only happened because the models debated.

  Want me to implement?

User: Yes, go ahead.

┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 5: Implementation — single model executes the debated design         │
│ Multi-model debate for design decisions during implementation              │
└─────────────────────────────────────────────────────────────────────────────┘

  → Claude creates a team:
    - Teammate "impl" (Claude) — implements the code changes
    - Teammate "tests" (Claude) — writes tests
    - Keeps the debug session alive (session_id: "shutdown-debug-001")

  → Teammate "impl" starts coding. Hits a design question about
    ExecutorService teardown (JVM shutdown vs engine recycling).

  → Calls follow_up() on the existing session — all three models
    debate again (they remember their earlier analysis via rolling
    summary). Two say shutdownNow(), one raises a concern about
    reference leaks during recycling. Consensus: shutdownNow() +
    2s awaitTermination(), with explicit nulling of the old
    EngineLifecycleService reference.

  → Teammate "tests" hits a question about simulating hung processes.
    Also calls follow_up(). Models debate: mock vs real process.
    Consensus: real OS process via bash trap, because the test needs
    to exercise the actual process-group kill logic.

  → Both teammates finish, report back to Lead.

┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 6: Final review + build                                              │
│ Full multi-model debate here because this is the LAST gate before commit   │
│ (per-stage reviews during implementation were light conformance checks)    │
└─────────────────────────────────────────────────────────────────────────────┘

  → Claude runs codereview() [fork version — full debate on complete diff]:
    All three models review the combined diff against the debated design.
    Round 1: independent review. Round 2: adversarial critique.
    One model flags a potential NPE in the force-kill path. Others confirm.
    Claude fixes it.

  ── NOTE: This is the only FULL multi-model review on the code.
     Per-stage reviews during Phase 5 were single-model conformance
     checks ("does this match the debated design?"). The design was
     already stress-tested in Phases 2-4, so per-stage reviews don't
     need to re-litigate the approach. ──

  → Claude runs the build: ./build-maven.sh clean install
  → Build passes, tests pass

Claude: All four fixes implemented, reviewed, and passing. The final
  review debate caught an NPE in the force-kill path that implementation
  missed. Ready for you to test.

User: Looks good, commit it.
```

### Key Difference From Previous Version: Actual Debate

The previous version of this example had models respond independently, then Claude
synthesized. That's a fan-out, not a debate. The critical addition is **Round 2** —
where models see each other's Round 1 responses and argue:

- Model A **challenged** Model C's FORCE_KILLED state → Model C **conceded**
- Model B **added a constraint** to Model A's executor idea (pool sizing)
- The final design was **different from any single model's Round 1 proposal**

This is the mechanism that produces better outcomes than any single model. Not just
"more findings" (Round 1 does that), but **refined findings** where proposals get
stress-tested by other models before implementation.

---

### Session 2: Code Design — Multi-Model Architecture Debate Before Writing Code

This example shows the same pattern applied to new feature development, not just
debugging. The principle is identical: debate the design first, then one model implements.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: User requests a new feature → Claude launches design debate       │
└─────────────────────────────────────────────────────────────────────────────┘

User:  I need to add auto-scaling to the cloud browser engine pool.
       When load test VU count increases, spin up more engines. When
       it decreases, shut them down. The controller already knows the
       current VU count and target VU count.

Claude (Lead):
  → Reads the relevant controller code and engine pool manager
  → Launches multi-model planner (3 models, parallel):
    prompt: "[includes EnginePoolManager.java, CloudEngineController.java,
              current scaling constants, and the VU counting mechanism]
             Design an auto-scaling system for browser engine pools.
             Requirements: scale up when VUs increase, scale down when
             VUs decrease, avoid thrashing (rapid up/down cycles),
             handle engine startup time (60-90 seconds).
             Propose the implementation design."

┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: Round 1 — Three different designs proposed                        │
└─────────────────────────────────────────────────────────────────────────────┘

  Model A: Proposes a reactive approach — check VU count every 30s,
    scale up/down by 1 engine per check cycle, with a 3-minute
    cooldown after each scale event to prevent thrashing.

  Model B: Proposes a predictive approach — track the VU count trend
    (increasing/decreasing/stable) over a sliding window, and scale
    based on where VUs will be in 90 seconds (to account for engine
    startup time). Pre-emptive scaling.

  Model C: Proposes a target-based approach — compute the ideal
    engine count from VU count and browsers-per-engine ratio, then
    converge toward the target with a dampening factor. No timers
    or cooldowns needed — the math handles stability.

  ── Three genuinely different architectures. Not minor variations
     — fundamentally different approaches to the same problem. ──

┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: Round 2 — Models argue about each other's designs                 │
└─────────────────────────────────────────────────────────────────────────────┘

  Model A: "Model B's predictive approach is fragile — VU ramp
    patterns aren't always linear, and the prediction will be wrong
    during step-load profiles. Model C's target-based approach is
    elegant but ignores engine startup time — by the time engines
    are ready, the VU count may have changed again. My cooldown
    approach is simpler and handles both cases."

  Model B: "Model A's cooldown is too slow — 3 minutes means you're
    always behind during ramp-up. Model C's dampening factor is
    interesting but needs to account for the 60-90s startup delay.
    I'll revise: instead of pure prediction, use Model C's target
    computation but START engines 90 seconds before they're needed
    based on the ramp rate. Hybrid approach."

  Model C: "Model A is right that my approach ignores startup time.
    Model B's revised hybrid is close to what I'd recommend now.
    But both miss a critical edge case: during scale-DOWN, you can't
    kill engines that are mid-transaction. You need a drain state —
    stop assigning new VUs to the engine, wait for current VUs to
    finish, then shut down. Neither of you addressed graceful drain."

  ── ROUND 2 PRODUCED:
     - A hybrid design (Model B revised, incorporating Model C's
       target computation)
     - A critical missing requirement (graceful drain during
       scale-down, from Model C's Round 2 challenge)
     - Rejection of the pure predictive approach (Model A's critique
       about step-load profiles)
     - The final design is BETTER THAN any Round 1 proposal ──

┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: Claude synthesizes the debated design                             │
└─────────────────────────────────────────────────────────────────────────────┘

Claude: Design debate converged on a hybrid approach:

  1. **Target computation**: ideal engine count = ceil(currentVUs /
     browsersPerEngine) with a dampening factor (don't scale for
     <10% target change)
  2. **Predictive startup**: when target is increasing, start engines
     90s early based on ramp rate
  3. **Graceful drain for scale-down**: new state DRAINING — stop
     assigning VUs, wait for completion, then shut down
  4. **No cooldown timer needed** — dampening factor + drain delay
     provide natural stability

  This combines elements from all three proposals but matches none
  of them exactly. The drain state (from Round 2) was missed by all
  three in Round 1.

  Want me to implement this design?

User: Yes.

  → Single Claude teammate implements the debated design.
  → Per-stage conformance checks (single model): "Does this implement
    the hybrid target computation with dampening factor?" — not a
    design review. The design was already debated.
  → During implementation, follow_up() calls go back to the same
    session for design questions that come up (e.g., "what should
    the dampening threshold be?" — gets debated because it's a
    design decision, not an implementation detail).
  → Final multi-model codereview() on complete change before commit.

  ── TOTAL MULTI-MODEL DEBATES: 3
       1. Design debate (Round 1 + Round 2)
       2. Follow-up design question (dampening threshold)
       3. Final code review on complete diff
     SINGLE-MODEL CONFORMANCE CHECKS: 2-3
       Per implementation stage: "matches the plan?"
     Compare to uniform review: would have been 5-6 full debates ──
```

---

### What These Sessions Demonstrate

| Capability | Session 1 (Debug) | Session 2 (Design) |
|-----------|-------------------|---------------------|
| **Round 1: Independent analysis** | Each model finds different root causes | Each model proposes a different architecture |
| **Round 2: Adversarial debate** | Models challenge each other's proposals; FORCE_KILLED state argued down to a simpler flag | Models critique each other's designs; hybrid approach emerges that none proposed initially |
| **New findings from debate** | Executor pool sizing constraint (Round 2 only) | Graceful drain requirement (Round 2 only) |
| **Design refinement** | Final fix is simpler than any Round 1 proposal | Final design combines elements from all three, matches none |
| **Heavy upstream, light downstream** | Full debate for root cause (Phases 2-4); light conformance checks during implementation (Phase 5); full debate for final review (Phase 6) | Full debate for architecture (Phases 2-4); light conformance during implementation; full debate for final review |
| **Persistent sessions** | Implementation follow-ups reuse the debug session for design questions | Implementation follow-ups reuse the design session |

### The Two-Round Debate Pattern

The critical mechanism for design-stage debates:

```
Round 1: All models analyze independently, in parallel (~4-8 seconds)
         → Surfaces different findings/proposals from different training data
         → Each model also returns context_requests[] (what files they wish they had)

Controller gathers requested context (~2-5 seconds)
         → Reads files agents requested, deduplicates, filters

Round 2: All models see each other's Round 1 responses + new context, argue (~4-8 seconds)
         → Challenges weak proposals, surfaces missed requirements,
           produces a refined result better than any Round 1 proposal

Total wall-clock time: ~12-20 seconds (two parallel rounds + context gathering)
Single-model time:    ~4-8 seconds (one analysis)
```

This is the same pattern `mcp__pal__consensus` uses today. The fork extends it to
debug, planner, and spec — any stage where **design decisions** are being made.

### The Conformance Check Pattern

For implementation stages (task breakdown, per-stage code review):

```
Single model reviews against the debated design (~3-5 seconds)
  → "Does this code implement the agreed approach?"
  → "Did the implementation deviate from the plan?"
  → "Are there bugs in the execution (not the design)?"

No Round 2 needed — this is a factual check, not a debate.
```

### Why This Is Faster Than Uniform Multi-Model Review

**Current workflow** (multi-model review at every stage):
- 5-6 full debates × ~20-30s each = **~2-3 minutes** of review
- Plus rework when late-stage reviews catch design issues
- Each stage re-litigates "is this the right approach?"

**Proposed workflow** (heavy upstream, light downstream):
- 2-3 full debates × ~15-20s each = **~45-60s** of debate
- 2-3 conformance checks × ~5s each = **~10-15s** of checking
- Total: **~65-75s**
- Far fewer rework cycles — design issues caught before any code written

**The key insight**: if your downstream conformance checks keep finding *design* issues
(not just implementation bugs), your upstream debate wasn't rigorous enough. Fix the
debate, don't add more review gates.

### What These Sessions Would Look Like WITHOUT Multi-Model

**Debug session**: Claude would find the timeout bug and fix it. Likely miss the thread
pool deadlock, the zombie process issue, or both. Ship a partial fix that works most of
the time and fails intermittently under load.

**Design session**: Claude would propose one architecture (probably the reactive approach
— simplest). Miss the graceful drain requirement entirely. Build something that works
for ramp-up but drops transactions during scale-down.

In both cases, the single-model fix would be *functional but incomplete* — exactly the
kind of gap that only surfaces in production under conditions that are hard to reproduce
in testing.

### What These Sessions Would Look Like WITH Uniform Review (Current Approach)

Both sessions would produce the same quality outcome — the design issues would still be
caught. But the process would be slower:

- **Debug session**: 4 fixes identified through debate (same). But each implementation
  stage gets a full 3-model review asking "is this the right approach?" when the approach
  was already debated. The shutdown executor fix gets re-questioned. The process group
  kill gets re-debated. Time wasted re-confirming decisions already made.

- **Design session**: Hybrid auto-scaling design emerges (same). But the task breakdown,
  each code stage, and each review all trigger full multi-model deliberation. Models
  re-debate the dampening factor at every stage instead of settling it once.

The quality ceiling is the same. The time cost is 2-3x higher.

### How Model-Task Affinities Emerge Over Time

The examples above use no model-to-task routing — every model sees the same prompt.
But the evaluation infrastructure (JSONL logging + `compare_models` tool) tracks which
models' findings survive the debate and get implemented. After weeks of real usage,
patterns may emerge:

- "Model A's Round 2 challenges cause design changes 70% of the time"
- "Model B catches OS/infrastructure issues others miss"
- "Model C's Round 1 proposals get revised most often but its Round 2 critiques are sharp"

These are **discovered empirically, not assumed**. If the data shows clear patterns,
the system could eventually weight certain models' contributions differently — but only
after the data justifies it. Until then, same prompt, all models, let them argue.

---

## Context Management Consensus (2026-03-22)

Four models consulted via `mcp__pal__consensus`: GPT-5.2 (FOR stateful + questioning),
Claude Opus 4.6 (AGAINST — keep stateless), GPT-5.4 (NEUTRAL), Gemini 2.5 Pro (NEUTRAL).

### The Problem

PAL/Zen's current design is completely stateless. Every consensus/debug/review call starts
from zero — the controller (Claude) must feed ALL required information as part of the query.
Two issues:

1. **Controller blind spots**: Claude can't anticipate what the debating agents will need.
   A model analyzing concurrency might need the thread pool config; a model analyzing
   process handling might need the signal handler code. Neither was included because
   Claude didn't know to look there.

2. **No follow-up continuity**: After a debate produces findings and implementation begins,
   new questions arise. Currently the entire prior debate must be re-summarized and re-fed
   for each follow-up — lossy and expensive.

### Consensus Results

**Universal agreement (4/4):**
- Fork PAL/Zen for multi-model debate — right approach
- Round 1 must be stateless — independent analysis, no anchoring bias
- Full verbatim Round 1 responses in Round 2 (3.5/4 — GPT-5.4 allows structured
  extraction for planning tasks, all others say always verbatim)
- Structured context templates per task type improve quality regardless of sessions
- Claude remains sole executor — agents advise, Claude acts

**Persistent sessions: 3 FOR, 1 AGAINST**

| Model | Position | Confidence |
|-------|----------|------------|
| GPT-5.2 | Stateful default for multi-turn tasks | 8/10 |
| GPT-5.4 | Stateless Round 1, thin-state for follow-ups | 9/10 |
| Gemini | Stateful sessions — natural extension of continuation_id | 9/10 |
| Claude Opus | Keep stateless, Claude's context window IS the state | 7/10 |

Opus's dissent: Claude's own context window already maintains session state. Re-injecting
into stateless calls is "curated, not lossy." Valid point for single-conversation use, but
doesn't hold when Claude teammates share sessions or when users start new conversations
about the same issue.

**Agent questioning: split resolved by Gemini's "request-as-output" pattern**

| Position | Models | Confidence |
|----------|--------|------------|
| Interactive questioning (blocking, mid-debate) | GPT-5.2, GPT-5.4 | 8-9/10 |
| Reject entirely (fix controller instead) | Claude Opus | 7/10 |
| **Request-as-output (non-blocking)** | **Gemini** | **9/10** |

The key insight from Gemini: agents don't need to *block* and wait for answers. Instead,
they complete their analysis AND return a structured list of context they wish they'd had:

```json
{
  "analysis": "... full analysis ...",
  "context_requests": [
    {
      "artifact_type": "source_file",
      "path": "EngineThreadPoolManager.java",
      "why_needed": "Shutdown uses a shared executor — need to verify pool config",
      "priority": "high"
    },
    {
      "artifact_type": "config",
      "path": "diagnostic.properties",
      "why_needed": "Need to check if debug logging covers shutdown sequence",
      "priority": "low"
    }
  ]
}
```

The controller gathers requested context between Round 1 and Round 2. This:
- Preserves simple fan-out/fan-in flow (no interactive protocol)
- Lets agents surface what they need (no controller blind spots)
- Adds zero latency to Round 1 (agents don't block)
- Keeps control flow deterministic and debuggable

**Memory strategy (3/4 agreement): stratified, task-aware**
- **Pinned facts** (immutable): error signatures, file paths, hypotheses with status
- **Working summary** (compressed): concise narrative, updated per exchange
- **Recent verbatim** (sliding window): last 2-3 exchanges
- **Checkpoints** (explicit): snapshots after major synthesis points
- Compression varies by task type (debug preserves hypotheses/evidence, design
  preserves decisions/tradeoffs, review preserves findings/severity)

**Risk flagged by 3/4 models: summary drift.** LLM-assisted summarization can hallucinate
facts into the rolling summary. Mitigation: constrain summarization to update structured
fields (pinned facts, hypothesis status), not rewrite freeform prose.

### Recommended Debate Flow

```
Round 1: Stateless fan-out (parallel, ~4-8s)
  → All models analyze independently
  → Each returns: analysis + structured context_requests[]

Controller gathers requested context (~2-5s)
  → Reads files agents requested
  → Deduplicates across agents
  → Controller decides what's worth including (agents request, controller filters)

Round 2: Adversarial debate with enriched context (~4-8s)
  → All models see: full verbatim Round 1 responses + newly gathered context
  → Models argue, challenge, revise

Session persists for follow-ups
  → Thin state: pinned facts + working summary + last 2-3 exchanges
  → Available to any Claude teammate via session_id
```

Total wall-clock: ~12-20 seconds for a complete two-round debate with context enrichment.

---

## How Context Is Maintained Across LLMs in the PAL Fork

This section addresses the practical engineering of session state. The core challenge:
**every LLM provider API is stateless.** OpenAI, Anthropic, Google — none of them
maintain server-side conversation state. Every API call is independent. So how do you
give models the illusion of memory?

### The Answer: The MCP Server IS the Session Store

The PAL fork MCP server runs as a single long-lived process (stdio child of Claude Code).
It holds session state in memory. For each API call, it **reconstructs the conversation**
from its stored state and sends it as a fresh message array.

```
┌──────────────────────────────────────────────────────────────────────┐
│ PAL Fork MCP Server (single Python process, in-memory state)        │
│                                                                      │
│  sessions: {                                                         │
│    "debug-001": {                                                    │
│      models: {                                                       │
│        "model-a": {                                                  │
│          provider: "openai",                                         │
│          model_id: "gpt-5.2",                                        │
│          pinned_facts: [...],         # Structured, immutable        │
│          working_summary: "...",      # Compressed narrative         │
│          recent_exchanges: [...],     # Last 2-3 verbatim            │
│          total_tokens_used: 47200,    # Track per-model usage        │
│          max_context: 400000          # Provider-specific limit      │
│        },                                                            │
│        "model-b": {                                                  │
│          provider: "google",                                         │
│          model_id: "gemini-2.5-pro",                                 │
│          pinned_facts: [...],                                        │
│          working_summary: "...",                                     │
│          recent_exchanges: [...],                                    │
│          total_tokens_used: 38500,                                   │
│          max_context: 1048576                                        │
│        },                                                            │
│        "model-c": { ... }                                            │
│      },                                                              │
│      shared_context: {               # Shared across all models      │
│        original_prompt: "...",                                        │
│        code_files: [...],                                            │
│        round1_responses: {...},                                      │
│        gathered_artifacts: [...]      # From context_requests        │
│      },                                                              │
│      created_at: "2026-03-22T...",                                   │
│      last_active: "2026-03-22T..."                                   │
│    }                                                                 │
│  }                                                                   │
└──────────────────────────────────────────────────────────────────────┘
```

### How Each API Call Is Constructed

When the controller calls `follow_up(session_id="debug-001", prompt="new question")`,
the MCP server builds a **fresh message array per model** from stored state:

```python
def build_messages(session, model_key, new_prompt):
    model_state = session.models[model_key]
    messages = []

    # 1. System prompt (task-specific framing from PAL/Zen prompt engineering)
    messages.append({
        "role": "system",
        "content": get_task_prompt(session.task_type)  # Inherited from PAL/Zen
    })

    # 2. Pinned facts (structured, always included, never compressed)
    if model_state.pinned_facts:
        messages.append({
            "role": "system",
            "content": format_pinned_facts(model_state.pinned_facts)
            # "Established facts:\n- Shutdown thread pool is shared with heartbeat\n
            #  - Chrome leaves zombie GPU processes on headless Linux\n
            #  - Engine state machine has no FORCE_KILLED transition"
        })

    # 3. Working summary (compressed narrative of older exchanges)
    if model_state.working_summary:
        messages.append({
            "role": "user",
            "content": f"Summary of prior analysis:\n{model_state.working_summary}"
        })

    # 4. Recent verbatim exchanges (last 2-3, uncompressed)
    for exchange in model_state.recent_exchanges:
        messages.append({"role": "user", "content": exchange.prompt})
        messages.append({"role": "assistant", "content": exchange.response})

    # 5. Shared context (code files, gathered artifacts)
    if session.shared_context.gathered_artifacts:
        messages.append({
            "role": "user",
            "content": format_artifacts(session.shared_context.gathered_artifacts)
        })

    # 6. New prompt
    messages.append({"role": "user", "content": new_prompt})

    return messages
```

**The model sees this as a single conversation.** It has no idea that the "prior analysis
summary" is a compressed version of exchanges it actually had. From the provider API's
perspective, this is just a fresh chat completion request with a carefully constructed
message history.

### Per-Model vs. Shared State

This is critical: **each model has its own memory, but some state is shared.**

| State Type | Per-Model | Shared | Why |
|-----------|-----------|--------|-----|
| Pinned facts | Yes — each model may pin different facts | Merged for synthesis | Models notice different things |
| Working summary | Yes — each model's own compressed history | No | Models have different conversation paths |
| Recent exchanges | Yes — each model's last 2-3 turns | No | Follow-ups may go to individual models |
| Original prompt | No | Yes | Same problem statement for all |
| Code files | No | Yes | Same source code for all |
| Gathered artifacts | No | Yes | Context requests are deduplicated and shared |
| Round 1 responses | No | Yes — all models see all Round 1 responses in Round 2 |

### Context Window Management Per Provider

Different providers have different context limits. The session manager must track
token usage per model and compress when approaching limits:

```python
def check_and_compress(model_state):
    messages = build_messages(...)
    estimated_tokens = count_tokens(messages)

    # Different thresholds per provider
    threshold = model_state.max_context * 0.75  # Leave 25% headroom for response

    if estimated_tokens > threshold:
        # Compress: move oldest recent exchange into working summary
        oldest = model_state.recent_exchanges.pop(0)
        model_state.working_summary = update_summary(
            model_state.working_summary,
            oldest,
            model_state.pinned_facts,  # Summary must not contradict pinned facts
            strategy=session.summary_strategy  # "template" or "llm"
        )
```

**Provider-specific context budgets:**

| Provider | Max Context | Effective Budget (75%) | Implications |
|----------|-------------|----------------------|--------------|
| OpenAI GPT-5.x | 400K-1.1M | 300K-825K | Generous — rarely needs compression |
| Anthropic Claude | 200K | 150K | Moderate — compress after ~5-8 follow-ups |
| Google Gemini 2.5 Pro | 1M | 750K | Very generous — almost never compress |

The asymmetry actually helps: Gemini's 1M context means it can hold full verbatim
history for much longer than the others, making it a good "deep memory" participant
in long debugging sessions.

### The Compression Pipeline

When compression is needed, the summary update is **constrained to structured fields**
to prevent drift (consensus recommendation):

```python
def update_summary(current_summary, exchange_to_compress, pinned_facts, strategy):
    if strategy == "template":
        # Deterministic extraction — fast, no hallucination risk
        return extract_structured(current_summary, exchange_to_compress)

    elif strategy == "llm":
        # LLM-assisted — better quality but risk of drift
        return llm_compress(
            current_summary,
            exchange_to_compress,
            constraints={
                "must_preserve": pinned_facts,         # Cannot contradict these
                "output_format": "structured_update",   # Not freeform prose
                "fields": [
                    "hypotheses_status",    # Which hypotheses were confirmed/rejected
                    "decisions_made",       # What was decided and why
                    "open_questions",       # What remains unresolved
                    "key_code_references"   # File:line references worth keeping
                ]
            }
        )
```

### Session Lifecycle in Practice

```
1. Claude calls debug(prompt, code_files)
   → MCP server creates session "debug-001"
   → Fans out to 3 providers (parallel API calls)
   → Stores Round 1 responses in session.shared_context
   → Returns responses + context_requests to Claude

2. Claude gathers requested files, calls debate(session_id, extra_context)
   → MCP server adds gathered_artifacts to session.shared_context
   → Builds Round 2 messages: system prompt + Round 1 responses + new context
   → Fans out to 3 providers (parallel)
   → Stores Round 2 responses, updates per-model recent_exchanges
   → Returns debate results to Claude

3. During implementation, Claude teammate calls follow_up(session_id, question)
   → MCP server looks up session "debug-001"
   → Builds messages from: pinned_facts + working_summary + recent_exchanges + question
   → Fans out to 3 providers (parallel)
   → Each model responds with context from its accumulated understanding
   → MCP server updates recent_exchanges, compresses if needed
   → Returns responses to teammate

4. Session idle for 60 minutes → GC cleans it up
   → Evaluation data (JSONL) preserved
   → Session state discarded
```

### What Happens When the MCP Server Restarts?

Sessions are in-memory. If the MCP server restarts (Claude Code restart, crash, etc.),
all sessions are lost. This is acceptable because:

- Sessions are meant to be transient (within a coding session, not across days)
- The evaluation JSONL is persisted to disk — long-term learning survives restarts
- If durability is needed later, add SQLite persistence (the `store.py` abstraction
  makes this a swap, not a rewrite)

### How This Differs From Chat History

This is NOT "save the chat and replay it." Key differences:

1. **Stratified compression** — pinned facts never compress, working summary gets
   tighter, recent exchanges slide. Chat history is flat.

2. **Task-aware** — debug sessions preserve hypotheses and evidence; design sessions
   preserve decisions and tradeoffs. Chat history is generic.

3. **Per-model independent** — each model has its own memory. Model A might have
   followed up 3 times on a concurrency theory while Model B only participated in
   the group rounds. Their memories diverge.

4. **Shared artifacts** — code files, gathered context, and Round 1/2 responses are
   stored once and referenced by all models. Not duplicated per conversation.

5. **Provider-aware compression** — Gemini (1M context) compresses later than
   GPT (400K) which compresses later than Claude (200K). Each model gets the
   richest history its context window can hold.

---

## Multi-Model Consensus Results (2026-03-21)

> **NOTE:** This consensus was conducted BEFORE discovering that PAL/Zen is fully open source
> and locally installed. The models assumed PAL/Zen was a hosted service with opaque internals,
> which led to dismissing the fork option. The corrected recommendation above supersedes the
> consensus's Option C preference. However, the consensus findings on session state design,
> evaluation infrastructure, and phased approach remain valid and are incorporated into the
> fork plan.

Four models were consulted via `mcp__pal__consensus`: GPT-5.2 (FOR Option C), Claude Opus 4.6 (AGAINST new infrastructure), GPT-5.4 (NEUTRAL), Gemini 2.5 Pro (NEUTRAL).

### Universal Agreement (4/4 models)

1. **Option A (Opencode fork) is rejected** — replaces Claude Code rather than extending it
2. **Option C architecture is the right long-term direction** — new MCP server with Claude as orchestrator
3. **Tool use format translation is the hardest problem** — must be deferred past Phase 1; it's an ongoing maintenance treadmill, not a one-time project
4. **Phase 1 must be text-in/text-out only** — no downstream tool use by model agents
5. **Claude Code must remain the sole tool-using executor** initially
6. **Verify Opencode license** before borrowing provider abstraction
7. **All models scored 8/10 confidence** on their respective positions

### Key Disagreement: Build Now vs. Measure First

| Position | Models | Argument |
|----------|--------|----------|
| Build thin Option C now | GPT-5.2, GPT-5.4, Gemini | Persistent state adds 20-40% value beyond stateless for iterative workflows (debugging, refactoring, architecture review) |
| Enhance PAL/Zen first, measure, then decide | Claude Opus | Claude's own context window IS the state layer — it can re-inject prior findings into each PAL call. Persistent state in subsidiary models is redundant until proven otherwise. |

### Critical Insight from Claude Opus (Dissent)

> "Claude Code *itself* already maintains full session context. When Claude calls `mcp__pal__consensus`, it can include all relevant prior findings in the prompt. The 'state' lives in Claude's context window, not in the subsidiary models."

This reframes the question: persistent multi-model state may be solving a problem that Claude's context window already handles. The counter-argument (from GPT-5.2/5.4) is that for long debugging sessions or multi-hour refactors, re-injecting context is lossy — summarizing prior findings for re-injection inevitably loses nuance. The subsidiary model benefits from having accumulated its own understanding through direct multi-turn interaction.

### New Options Identified

| Option | Description | Source |
|--------|-------------|--------|
| **D: MCP meta-wrapper over PAL/Zen** | Thin coordinator storing session summaries locally, calling PAL for execution. Lowest effort if PAL APIs are stable. | GPT-5.2, GPT-5.4 |
| **E: Single-model diversity first** | Claude agent teams with enforced role separation, varied prompts/effort levels, PAL for escalation. Best immediate ROI. *Note: consensus incorrectly assumed temperature control was available in Claude Code — it is not. Only effort level is controllable.* | GPT-5.4 |
| **F: Benchmark-first** | Define 20-50 representative tasks, compare single-Claude vs PAL consensus vs thin-state prototype. Prevents overbuilding. | GPT-5.4 |

### Revised Phased Recommendation (Consensus)

All four models converged on a **validate-before-building** approach, differing only on where to draw the "build" trigger:

**Phase 0 — Immediate (days, no new infrastructure):**
- Use Claude agent teams with enforced role separation (adversarial, optimistic, domain-specialist prompts)
- Vary effort levels across agents (temperature is NOT available in Claude Code)
- Use PAL `consensus` for multi-model perspective on key decisions
- **Goal:** Validate whether cognitive diversity improves outcomes at all

**Phase 1 — If Phase 0 validates (1-3 weeks):**
Thin-state MCP coordinator with refined API (from GPT-5.4):
- `multi_query(prompt, model_specs[], attachments[])` — parallel multi-model query
- `follow_up(session_id, model_alias, prompt)` — with server-managed compact summary, not full transcript replay
- `synthesize(responses[], rubric)` — structured cross-model synthesis
- `compare_models(task_type, outputs)` — logging quality/latency/outcome metadata for evaluation
- 3 providers max: Anthropic, OpenAI, Google
- Text-only outputs, optionally JSON schema constrained
- Claude remains sole tool user and file reader
- **Complements PAL/Zen, does not replace it**

**Phase 2 — If Phase 1 data justifies (months):**
- Add tool use translation for Tier 1 models
- Capability profiles: text-only, structured-output, tool-capable, long-context, code-strong, security-strong

**Phase 3 — If Phase 2 proves value:**
- Full agent coordination, learning, quality-aware routing

### Key Design Principles (from consensus)

1. **Normalize at the contract level, not the mechanism level** — don't try to make all models use the same tools; require the same output format ("produce a patch plan", "enumerate risks", "give test cases") (GPT-5.2)
2. **Ephemeral session memory with checkpoints > full persistent conversational identity** — summaries and explicit checkpoints, not raw transcript growth (GPT-5.4)
3. ~~**Multi-model should be a "hard-problem escalation button", not always-on**~~ — **SUPERSEDED (2026-03-22).** The right model is neither "always-on for everything" nor "escalation only." Full multi-model debate for **design stages** (specify, plan, debug root cause, architecture). Single-model conformance checks for **implementation stages** (task breakdown, per-stage code review). Final multi-model review on the complete change. This is faster than uniform review AND produces better outcomes than selective escalation — design issues are caught before code is written, and downstream reviews don't re-litigate settled decisions.
4. **Include evaluation infrastructure from day 1** — without benchmarks, there's no way to know which models actually produce superior results for which task types (GPT-5.4)
5. **Degrade gracefully to PAL one-shot** — if the MCP server has issues, fall back to existing stateless tools (GPT-5.2)

### PAL/Zen Enhancement Recommendations (from Claude Opus)

Even without building Option C, these enhancements to PAL/Zen would deliver significant value:
1. Add optional conversation-ID with server-side history caching (lightweight statefulness)
2. Add model-strength metadata so Claude can make informed routing decisions
3. Improve `consensus` with configurable synthesis strategies (voting, adversarial, weighted-by-domain)
4. Add quality tracking and model performance profiling per query
5. Add a `deep_analysis` tool that sends richer context to a specific model with optional prior-response inclusion

## Research Paper: Multi-Model Adversarial Debate for Software Engineering

**Status:** Concept — dependent on PAL fork implementation for experimental platform

### The Gap in Existing Literature

Multi-model approaches on coding benchmarks already exist, but they all use models as
**specialists in a pipeline** — one model plans, another generates code, another debugs.
Examples:

- **Replit.ai Agent** (SWE-bench): Claude 3.7 Sonnet orchestrates, o4-mini generates
  code. Different models, different roles, no debate.
- **Claude + GPT-4o** (9 SWE-bench submissions): Same pattern — role assignment across
  models in a pipeline.
- **MapCoder** (ACL 2024): 4 agents (recall → plan → generate → debug), but all are
  the same model with different prompts.
- **AgentCoder**, **ChatDev**, **MetaGPT**: Multi-agent, but same-model with role
  diversity, not cross-model debate.

**What no one has published:**
1. Cross-model adversarial debate — multiple different LLMs see the same task, propose
   solutions independently, then argue about whose approach is better
2. Ablation of debate phases — is the value from model diversity, adversarial critique,
   or information acquisition?
3. Tiered debate intensity — heavy debate for design decisions, light conformance checks
   for implementation
4. Request-as-output — agents identifying missing context as a structured output that
   enriches subsequent debate rounds

### Research Question

> *In multi-model LLM collaboration for software engineering, where does the marginal
> quality come from — model diversity, adversarial critique, or information acquisition
> — and how should debate intensity be allocated across the software development
> lifecycle?*

### The Contamination Problem

SWE-bench has a serious memorization issue that any study must address.

["The SWE-Bench Illusion"](https://arxiv.org/html/2506.12286v3) (Microsoft Research)
showed that state-of-the-art models can identify the buggy file path **76% of the time
using only the issue description, without seeing the codebase.** On repos NOT in
SWE-bench, accuracy drops to 53%. Models have seen these bugs and fixes in their
training data — they're partly remembering, not reasoning.

This affects the debate paper in a specific way:
- If all three models memorized the same fix → debate adds nothing → valid negative finding
- If models memorized *different* things → debate surfaces the union → real diversity
  value, but it's "diversity of memorization," not reasoning
- If *no* model memorized the fix → these are the tasks where genuine debate matters most

**The solution: dual-benchmark design.** Run experiments on both a contaminated benchmark
(for comparability) and a contamination-free benchmark (for validity).

### Experimental Design: Dual-Benchmark Ablation Study

#### Benchmarks

| Benchmark | Tasks | Purpose | Contamination Status |
|-----------|-------|---------|---------------------|
| [**SWE-bench Verified**](https://www.swebench.com/) | 500 curated tasks from real GitHub repos (Django, scikit-learn, sympy) | **Comparability** — every major model has published baselines | **Contaminated** — tasks are in training data; models can partly memorize solutions |
| [**SWE-bench-Live**](https://github.com/microsoft/SWE-bench-Live) | Monthly-updated tasks from live repos; tasks created AFTER model training cutoffs | **Validity** — proves results are from reasoning, not recall | **Clean** — by construction, models cannot have seen these issues |

Running both benchmarks answers a question that neither alone can:

```
If debate helps on Verified but NOT on Live
  → The value was diversity of memorization, not reasoning
  → Still publishable, but weaker claim

If debate helps on BOTH Verified and Live
  → The value is genuine reasoning diversity
  → Strong claim: debate improves actual problem-solving

If debate helps MORE on Live than Verified
  → Debate is most valuable precisely when memorization fails
  → Strongest possible finding: debate is the antidote to
    the limits of single-model memorization
```

The third outcome is the most interesting — and the most likely, because
contamination-free tasks are where models must actually reason, which is where
different training data produces genuinely different analysis.

#### Additional Benchmark Option

[**SWE-rebench**](https://swe-rebench.com) (Nebius) offers 21,000+ tasks with explicit
contamination tracking tied to model release dates. If SWE-bench-Live's monthly cadence
doesn't provide enough tasks at experiment time, SWE-rebench provides a larger
contamination-aware alternative.

#### Models

Claude Opus 4.x, GPT-5.x, Gemini 2.5 Pro — the strongest available from each major
provider. Use the most capable models to maximize the chance that diversity produces
genuinely different analysis, not just quality variance.

#### Configurations (Ablation)

| Config | Description | What It Tests |
|--------|-------------|---------------|
| **A** | Single model, single attempt | Baseline — published numbers exist |
| **B** | 3 models, parallel, pick best-scoring patch | Does model diversity alone help? (ensemble selection) |
| **C** | 3 models, Round 1 independent + Round 2 adversarial debate | Does debate add value beyond diversity? |
| **D** | 3 models, Round 1 + context requests + Round 2 with enriched context | Does information acquisition add further value? |
| **E** | Config D with tiered intensity (full debate for diagnosis/design, conformance check for implementation) | Does tiered debate match full-debate quality at lower cost? |

**Baselines for Config A:**

*SWE-bench Verified* (published — no experiments needed):

| Model | SWE-bench Verified (published) |
|-------|-------------------------------|
| Claude Opus 4.5 | ~80.9% |
| GPT-5.2 | ~75-78% (estimated from leaderboard) |
| Gemini 2.5 Pro | ~76.8% |

*SWE-bench-Live* (must run — no debate-specific baselines published):
Single-model baselines must be generated as part of the experiment. This adds cost
but is necessary for the contamination-free comparison.

**Headline results require beating baselines on BOTH benchmarks:**
- Verified: Config C or D > ~80.9% → debate beats best individual model (comparable)
- Live: Config C or D > best single-model on Live → debate beats reasoning alone (valid)
- If Live gain > Verified gain → debate helps MORE when memorization can't help (strongest finding)

#### Integration with SWE-bench Harness

SWE-bench's evaluation harness expects a single agent producing a patch file. The debate
system wraps internally:

```
SWE-bench harness
  → sends issue + repo to our system
    → Claude (orchestrator) reads the issue and relevant code
    → Launches multi-model debate (Round 1 → context requests → Round 2)
    → Claude synthesizes consensus fix approach
    → Claude implements the patch (single model execution)
  → returns patch file to harness
  → harness runs tests → pass/fail
```

From the harness's perspective, it's one agent. The debate is invisible — it happens
inside the agent's "thinking" step.

### Metrics

#### Primary Metrics
- **Pass rate on SWE-bench Verified** — directly comparable to all published results
- **Pass rate on SWE-bench-Live** — contamination-free validation of reasoning improvement
- **Delta between Verified and Live gains** — measures whether debate compensates for memorization loss

#### Secondary Metrics (per-task analysis)

| Metric | What It Measures | How to Capture |
|--------|-----------------|----------------|
| **Unique finding rate** | How often does a model identify something no other model found? | Compare Round 1 responses — count findings unique to one model |
| **Round 2 change rate** | How often does debate change the final approach vs. Round 1? | Compare pre-debate synthesis vs. post-debate synthesis |
| **Context request hit rate** | How often do requested files lead to new findings? | Compare findings before vs. after context enrichment |
| **Disagreement-to-insight rate** | When models disagree, how often does the disagreement point lead to a better solution? | Classify disagreements as productive (led to fix) vs. noise |
| **Task complexity correlation** | Does debate help more on harder tasks? | Correlate debate value-add with task difficulty (e.g., lines changed, files touched) |
| **Contamination sensitivity** | Does debate help more on contamination-free tasks? | Compare debate lift on Verified vs. Live; segment Verified tasks by estimated memorization likelihood |

#### Ablation Analysis

The ablation tells a clean story:

```
If B > A:  Model diversity helps (different models solve different problems)
If C > B:  Adversarial debate adds value beyond diversity
If D > C:  Information acquisition (context requests) adds further value
If E ≈ D:  Tiered debate achieves full-debate quality at lower cost
```

Each comparison isolates exactly one variable. If any step shows no improvement,
that phase can be dropped — saving latency without sacrificing quality.

### Expected Contributions

1. **First cross-model adversarial debate results on a coding benchmark.** Existing
   multi-model work uses pipeline role assignment. This is the first to show models
   arguing about the same task and producing a consensus that beats individual models.

2. **Contamination-controlled evaluation.** Dual-benchmark design (SWE-bench Verified +
   SWE-bench-Live) separates reasoning improvement from memorization diversity. Answers
   "does debate help because models know different things, or because they reason
   differently?" — a question no prior multi-model study has addressed.

3. **Phase ablation for multi-model coding.** Quantifies the independent contribution
   of diversity, debate, and information acquisition. Answers "where does the value
   come from?" with data rather than intuition.

4. **Request-as-output pattern.** Novel mechanism where debating agents return structured
   lists of missing context alongside their analysis. No prior work has formalized or
   measured this.

5. **Tiered debate intensity model.** Formalizes the observation that design decisions
   benefit from full debate while implementation stages need only conformance checks.
   Practical guidance for allocating compute budget across the development lifecycle.

6. **Reproducible experimental platform.** The PAL fork + SWE-bench harness integration
   is fully open-source (Apache 2.0 base). Other researchers can replicate and extend.

### Paper Outline

```
Title: "Multi-Model Adversarial Debate for Software Engineering:
        Does Debate Improve Reasoning or Just Recall?"

Abstract
  - Multi-model debate (3 LLMs argue, then consensus) vs single-model
  - Dual-benchmark: SWE-bench Verified (contaminated, comparable) +
    SWE-bench-Live (clean, valid)
  - Verified results: [X]% vs best single-model [80.9%]
  - Live results: [Y]% vs best single-model [Z]%
  - Key finding: debate helps [more/less/equally] on contamination-free
    tasks, indicating value comes from [reasoning/recall] diversity
  - Ablation: diversity contributes [N]%, debate adds [M]%, context
    requests add [K]%

1. Introduction
   - Current multi-model approaches: pipeline with role assignment
   - Gap: no adversarial debate, no ablation of debate phases
   - The contamination question: do multi-model gains survive when
     models can't memorize solutions?
   - Contributions: debate pattern, ablation, request-as-output,
     tiered intensity, contamination analysis

2. Related Work
   2.1 Multi-agent coding systems
       - MapCoder, AgentCoder, ChatDev, MetaGPT
         (same model, different roles — pipeline, not debate)
   2.2 Multi-model SWE-bench submissions
       - Replit (Claude + o4-mini), Claude+GPT-4o submissions
         (role assignment, not adversarial debate)
   2.3 LLM debate for reasoning
       - Du et al. 2023, Liang et al. 2023
         (math/logic benchmarks, not software engineering)
   2.4 Ensemble methods
       - Majority voting, best-of-N, mixture-of-agents
         (selection, not adversarial critique)
   2.5 Benchmark contamination
       - "The SWE-Bench Illusion" (Microsoft) — memorization evidence
       - SWE-bench-Live, SWE-rebench — contamination-free alternatives
       - Why contamination matters for multi-model studies

3. Method
   3.1 Two-Round Debate Pattern
       - Round 1: parallel independent analysis (same prompt, all models)
       - Request-as-output: agents return context_requests[]
       - Controller gathers requested artifacts
       - Round 2: adversarial critique with enriched context
       - Synthesis: orchestrator produces consensus approach
   3.2 Request-as-Output: Agent-Driven Information Acquisition
       - Structured schema: artifact_type, path, why_needed
       - Non-blocking: agents complete analysis AND request more context
       - Controller filters and gathers between rounds
   3.3 Tiered Debate Intensity
       - Full debate for diagnosis/design (high-leverage decisions)
       - Conformance check for implementation (single model)
       - Full debate for final review (last quality gate)
   3.4 Session Management
       - Stateless Round 1 (anti-anchoring)
       - Thin-state for follow-ups (stratified memory)
       - Provider-aware compression (128K-1M context windows)

4. Experimental Setup
   4.1 Dual benchmark: SWE-bench Verified + SWE-bench-Live
       - Verified: 500 tasks, published baselines, contaminated
       - Live: monthly-updated tasks, contamination-free
       - Why both: comparability + validity
   4.2 Models: Claude Opus, GPT-5.x, Gemini 2.5 Pro
   4.3 Configurations A-E (ablation)
   4.4 Harness integration (debate inside agent wrapper)
   4.5 Contamination controls
       - Compare single-model performance drop (Verified → Live)
         vs. debate performance drop (Verified → Live)
       - If debate drop < single-model drop, debate compensates
         for memorization loss
   4.6 Statistical methodology (confidence intervals, significance
       tests, multiple comparison correction)

5. Results
   5.1 Pass rates by configuration — BOTH benchmarks (main result)
   5.2 Ablation: contribution of each phase
   5.3 Contamination analysis: Verified vs. Live gain comparison
   5.4 Per-task analysis: when does debate help most?
   5.5 Disagreement analysis: productive vs. noise
   5.6 Context request analysis: hit rate by task type
   5.7 Cost analysis: tokens, latency, $/task by configuration

6. Analysis
   6.1 Does debate improve reasoning or just recall?
       - Tasks where debate helps on Live but not Verified
         (reasoning value)
       - Tasks where debate helps on Verified but not Live
         (memorization diversity)
       - Tasks where debate helps on both (universal value)
   6.2 Case studies: tasks solved by debate but not single model
   6.3 Case studies: tasks where debate fails (all agree wrongly)
   6.4 Task complexity threshold: below what complexity is
       debate unnecessary?
   6.5 Model complementarity: which model pairs produce
       the most productive disagreements?
   6.6 Context request analysis: what do models ask for,
       and does it help?

7. Discussion
   7.1 Implications for coding agent design
   7.2 The contamination-debate interaction: multi-model as
       a hedge against memorization failure
   7.3 Tiered debate as a practical cost-quality tradeoff
   7.4 Request-as-output as a general agentic pattern
   7.5 Limitations: provider cost, API rate limits, benchmark scope,
       model version pinning
   7.6 Generalizability: will these results hold as models improve?

8. Conclusion
   - Multi-model debate beats best single model by [N]% (Verified)
     and [M]% (Live — contamination-free)
   - Debate helps [more/less/equally] without memorization,
     suggesting value is from [reasoning/recall] diversity
   - Value comes primarily from [debate/diversity/context] (ablation)
   - Tiered intensity achieves [X]% of full-debate quality at [Y]% cost
   - Open-source platform available for replication

Appendix A: Full results table (all tasks × 5 configs × 2 benchmarks)
Appendix B: Debate transcript examples (3-4 illustrative cases)
Appendix C: Prompt templates used for each debate round
Appendix D: Request-as-output schema and hit rate analysis
Appendix E: Contamination analysis methodology and per-task scores
```

### Prerequisites

The paper requires the PAL fork to exist as an experimental platform:

| Dependency | Status | Needed For |
|-----------|--------|------------|
| PAL fork with multi-model debate | Not started | All configurations except A |
| Request-as-output schema | Not started | Configuration D |
| Session management | Not started | Follow-up rounds during implementation |
| SWE-bench Verified harness wrapper | Not started | Running experiments (contaminated benchmark) |
| SWE-bench-Live harness wrapper | Not started | Running experiments (clean benchmark) |
| Evaluation JSONL logging | Not started | All secondary metrics |
| Contamination analysis tooling | Not started | Verified vs. Live comparison metrics |

The PAL fork is the foundation. Without it, there's no experimental platform.
Building the fork first, then running SWE-bench experiments, is the natural sequence.

**Estimated cost:** ~$1,500-$7,500 in API costs (500+ tasks × 5 configs × 3 models
× 2 benchmarks). Higher than single-benchmark studies, but the contamination-controlled
design is what makes the paper novel and the results credible.

### Target Venues

| Venue | Fit | Timeline |
|-------|-----|----------|
| **ICLR 2027** | Strong — AI agents, empirical study | Submit Oct 2026 |
| **NeurIPS 2026** | Strong — LLM methodology | Submit May 2026 (tight) |
| **ICSE 2027** | Strong — software engineering focus | Submit Sep 2026 |
| **ACL 2027** | Moderate — NLP/agents track | Submit Jan 2027 |
| **arXiv preprint** | Immediate visibility | Anytime after experiments complete |

ICSE (International Conference on Software Engineering) may be the best fit — the
paper is fundamentally about software engineering methodology, and the audience is
practitioners and researchers who care about real-world coding effectiveness. ICLR
and NeurIPS have broader reach but more competition for attention.

### Risks

1. **Debate doesn't help enough.** If Config C only beats Config A by 1-2%, the result
   is real but not exciting. Mitigation: the ablation is still publishable — "debate
   adds marginal value on SWE-bench because tasks are mostly single-cause bugs" is a
   valid finding that helps the field.

2. **Gains don't survive contamination control.** If debate helps on Verified but not
   on Live, the value was memorization diversity, not reasoning. Mitigation: this is
   actually a valuable finding — it would be the first empirical evidence that
   multi-model gains on contaminated benchmarks are inflated. Still publishable,
   with a different headline.

3. **Context requests don't help.** SWE-bench provides the full repository, so the
   controller (Claude) already has access to all files. Context requests may add less
   value here than in a real workflow where the controller must choose what to include.
   Mitigation: measure and report honestly; this limitation itself is a finding. Note
   that this effect may differ between Verified (controller has seen similar repos) and
   Live (genuinely unfamiliar repos where context requests may matter more).

4. **Cost.** Running 500+ tasks × 5 configurations × 3 models × 2 benchmarks =
   ~15,000+ model invocations. At ~$0.10-0.50/invocation average, that's $1,500-$7,500
   in API costs. Higher than single-benchmark design but necessary for the contamination
   analysis that makes the paper novel.

5. **SWE-bench task structure may not favor debate.** Many SWE-bench tasks are
   single-file, single-cause bugs where one good model is sufficient. The debate
   pattern may show larger gains on multi-file, multi-cause issues. Analysis should
   segment by task complexity. SWE-bench Pro (1,865 tasks, 123 languages, longer-horizon)
   could supplement if SWE-bench Verified tasks are too simple.

6. **SWE-bench-Live task volume.** SWE-bench-Live updates monthly, so the available task
   count at experiment time depends on timing. If insufficient, SWE-rebench (21,000+
   tasks with contamination tracking) provides an alternative or supplement.

7. **Reproducibility.** Model capabilities change over time (updates, deprecations).
   Pin exact model versions and record all API parameters. Publish all prompts and
   configurations for replication. The dual-benchmark design helps here — SWE-bench-Live
   is explicitly designed for temporal reproducibility with contamination tracking.

## References

### Architecture & Tools
- [Claude Code Agent Teams Documentation](https://docs.anthropic.com/en/docs/claude-code)
- [Opencode Repository](https://github.com/opencode-ai/opencode) — Go-based multi-provider coding agent
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- PAL/Zen MCP tools (already integrated in this project)

### Benchmarks
- [SWE-bench](https://www.swebench.com/) — Software engineering benchmark for LLM agents
- [SWE-bench Verified Leaderboard](https://llm-stats.com/benchmarks/swe-bench-verified) — Current model rankings
- [SWE-bench-Live](https://github.com/microsoft/SWE-bench-Live) (Microsoft, NeurIPS 2025) — Monthly-updated contamination-free benchmark
- [SWE-rebench](https://swe-rebench.com) (Nebius) — 21,000+ tasks with automated contamination tracking
- [SWE-Bench Pro: Long-Horizon Software Engineering Tasks](https://arxiv.org/pdf/2509.16941) — Extended benchmark (1,865 tasks, 123 languages)

### Contamination & Benchmark Validity
- [The SWE-Bench Illusion: When State-of-the-Art LLMs Remember Instead of Reason](https://arxiv.org/html/2506.12286v3) (Microsoft Research) — Evidence that models memorize SWE-bench solutions
- [Does SWE-Bench-Verified Test Agent Ability or Model Memory?](https://arxiv.org/pdf/2512.10218) — Further memorization analysis
- [SWE-rebench: Contamination-Free Evaluation of Software Engineering Agents](https://arxiv.org/abs/2505.20411) — Automated decontamination pipeline

### Multi-Agent Systems
- [Dissecting SWE-Bench Leaderboards: Architectures of LLM Repair Systems](https://arxiv.org/html/2506.17208v2) — Analysis of multi-model SWE-bench submissions
- [MapCoder: Multi-Agent Code Generation](https://aclanthology.org/2024.acl-long.269/) — Same-model multi-agent, role-based pipeline
- [MultiAgentBench: Evaluating Collaboration of LLM Agents](https://arxiv.org/abs/2503.01935) — Multi-agent evaluation framework
