<!--
Sync Impact Report:
- Version change: 1.0.0 → 1.1.0
- Principles modified:
  - II. Heavy Debate Upstream, Light Checks Downstream → II. Adaptive Review Intensity
    (rigid binary doctrine replaced with adaptive escalation per 3-model consensus review)
- Principles unchanged:
  - I. Cognitive Diversity Through Model Variety
  - III. Fork and Extend, Don't Rebuild
  - IV. Asymmetric Architecture
  - V. Evaluation From Day One
  - VI. Provider Abstraction
  - VII. Quality Gates (NON-NEGOTIABLE)
- Sections added:
  - Architectural Constraints
  - Development Workflow
  - Governance
- Templates requiring updates:
  - .specify/templates/plan-template.md — ✅ Constitution Check aligns (generic gate)
  - .specify/templates/spec-template.md — ✅ No constitution-specific sections required
  - .specify/templates/tasks-template.md — ✅ Phase structure compatible
- Follow-up TODOs: None
-->

# PAL MCP Server Constitution

## Core Principles

### I. Cognitive Diversity Through Model Variety

Different LLMs have different training data, different architectures, and different
blind spots. A single model debugging a problem finds *some* root causes. Multiple
models analyzing the same problem — then arguing about each other's findings —
collectively find more.

- Multi-model analysis MUST be the default for all decision-making tools (debug,
  codereview, planner, design), not an optional escalation
- When models disagree, the disagreement MUST be surfaced as signal — not suppressed
  or majority-voted away
- Minimum two models for a valid debate; three or more preferred
- Single-model fallback MUST be built in natively for conformance checks and
  graceful degradation

### II. Adaptive Review Intensity

Invest multi-model debate where it has the highest leverage, and use adaptive
escalation everywhere else. Conformance does not equal correctness — designs
operate at a different abstraction level than implementations, and implementation
is a discovery process that surfaces bugs no upstream debate could predict.

- **FULL DEBATE**: Specifying requirements, designing code/architecture, debugging
  root causes, planning implementation, final review of complete change sets
- **ADAPTIVE REVIEW**: Per-stage code reviews default to single-model analysis
  with a structured escalation signal (confidence score, complexity assessment,
  anomaly flags). When confidence is low, complexity is high, or anomalies are
  flagged, the system MUST auto-promote to full multi-model debate
- **LIGHT CHECK**: Task breakdown (mechanical derivation from debated plan),
  clearly mechanical edits (renames, docs, simple wiring)
- **NO REVIEW**: Builds, tests, git operations (deterministic, no judgment)
- Evaluation data SHOULD inform escalation thresholds over time — the system
  learns which stages and code patterns benefit most from full debate

### III. Fork and Extend, Don't Rebuild

The project is a fork of PAL/Zen MCP Server (Apache 2.0, ~16,500 lines). Inherit
proven code and add only what is missing. Never rebuild functionality that already
exists and works.

- All existing prompt engineering (~15 structured prompt files) MUST be preserved
  and used as task-specific framing for debates
- All existing provider abstractions (7+ providers, 111+ models) MUST be inherited
- New capabilities (session state, evaluation, debate orchestration) MUST integrate
  with existing patterns — especially the `continuation_id` threading system
- Attribution to the original author (Fahad Gilani / Beehive Innovations) and
  NOTICE file preservation are Apache 2.0 license obligations, not optional

### IV. Asymmetric Architecture

Claude is the orchestrator and sole executor. Non-Claude models are text-only
advisors. This is a deliberate architectural choice, not a limitation.

- Claude teammates MUST have full tool access (file editing, bash, MCP tools) and
  participate in the agent team message/broadcast system
- Non-Claude models accessed via the fork MUST remain text-in/text-out advisors —
  they do not edit files, run commands, or access the filesystem
- The fork does not read files from disk — the calling agent gathers requested
  artifacts and provides them to the fork
- One model writes code; multiple models decide *what* code to write
- Tool use format translation across providers is explicitly deferred — normalize
  at contract level (same output format), not mechanism level (same tool schemas)

### V. Evaluation From Day One

Every model interaction MUST produce structured evaluation data. Model selection
without data is guesswork.

- Every interaction MUST log: model, provider, task type, token counts, latency,
  and status to JSONL
- Evaluation data MUST be preserved even when sessions are destroyed or expire
- The `compare_models` tool MUST enable querying by model, task type, or both
- Quality signals (follow-up rate, acceptance rate, follow-up depth) MUST be
  tracked to identify model-task affinities over time
- Optimize for outcome quality, not cost — use the most capable model available
  per provider; reserve smaller models only for latency-sensitive operations like
  session summarization

### VI. Provider Abstraction

Provider-specific code lives in exactly one place. Every tool works against
normalized interfaces.

- Each provider adapter MUST implement the `ModelProvider` ABC with
  `ModelCapabilities` and `ModelResponse`
- Provider-aware context compression MUST respect per-model context limits
  (128K–1M) — Gemini compresses later than Claude; each model gets the richest
  history its context window allows
- Rate limiting MUST be per-provider and shared across all agent team members
  (one MCP server process, one rate limiter per provider)
- Circuit breakers MUST prevent retrying consistently failing providers — one
  provider down MUST NOT kill the entire request

### VII. Quality Gates (NON-NEGOTIABLE)

All code changes MUST pass quality checks before merge. No exceptions.

- `./code_quality_checks.sh` MUST pass (ruff linting, black formatting, isort,
  unit tests) before any PR
- Integration tests (`./run_integration_tests.sh`) MUST pass for changes touching
  provider code, tool implementations, or session management
- Simulator tests (`communication_simulator_test.py --quick`) MUST pass for
  changes affecting tool behavior or conversation threading
- Security vulnerabilities (command injection, path traversal, OWASP top 10) MUST
  be caught and fixed immediately — never shipped knowingly

## Architectural Constraints

- **Language**: Python 3.12 — inherited from PAL/Zen; MUST NOT change language
- **Transport**: stdio — local child process, no network server, no hosted backend
- **State model**: In-memory sessions with stratified memory (pinned facts, working
  summary, recent verbatim exchanges, named checkpoints) — sessions are transient
  within a coding session; only evaluation data persists to disk
- **Summary strategy**: LLM-assisted compression (default) or deterministic template
  extraction (fallback) — constrained to structured field updates to prevent drift;
  MUST NOT contradict pinned facts
- **Session sharing**: One MCP server process shared across all agent team members —
  any teammate can follow up on any session via session ID
- **Tool naming**: Fork MUST use the same tool names as original PAL/Zen under a
  distinct server namespace — drop-in replacement by changing the namespace prefix
- **Self-contained**: Fork MUST NOT depend on an original PAL/Zen installation;
  single-model operation built in natively

## Development Workflow

- **Before changes**: Activate venv (`source .pal_venv/bin/activate`), run
  `./code_quality_checks.sh`, verify server health via logs
- **After changes**: Run quality checks, integration tests, quick simulator tests,
  check logs, restart Claude session for updated code
- **Before PR**: Final quality check, integration tests, quick simulator test suite,
  verify 100% pass rate
- **Upstream sync**: GitHub fork with periodic manual merges — upstream improvements
  incorporated on a controlled schedule, not automatically
- **Commit discipline**: Each commit MUST be atomic and pass all quality gates
  independently

## Governance

This constitution defines the non-negotiable architectural principles and quality
standards for the PAL MCP Server fork. It supersedes ad-hoc decisions and informal
conventions.

- **Amendments** require: (1) documented rationale, (2) impact assessment on
  existing code and artifacts, (3) version bump per semantic versioning
- **Compliance** is verified through quality gates (Principle VII) and code review
- **Runtime guidance** for day-to-day development lives in `CLAUDE.md` — this
  constitution governs architectural decisions and standards
- **Conflicts**: If a proposed change conflicts with a Core Principle, the change
  MUST either be modified to comply or the Principle MUST be formally amended first

**Version**: 1.1.0 | **Ratified**: 2026-03-22 | **Last Amended**: 2026-03-22
