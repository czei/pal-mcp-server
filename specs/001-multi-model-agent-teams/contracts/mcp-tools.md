# MCP Tool Contracts: Multi-Model Agent Teams

**Phase 1 output for**: `/specs/001-multi-model-agent-teams/plan.md`
**Date**: 2026-03-22

These contracts define the external interface exposed by the forked PAL/Zen MCP
server. All tools communicate via MCP's stdio transport. The caller sends JSON
tool requests; the server returns JSON tool responses.

## Modified Existing Tools (Debate Mode)

All existing decision-making tools gain an optional `debate_mode` parameter.
When `debate_mode` is enabled, the tool routes through the `DebateOrchestrator`
instead of calling a single provider.

### Debate Mode Parameters (added to all applicable tools)

These parameters are **optional** and added to the input schema of: `debug`,
`codereview`, `planner`, `thinkdeep`, `analyze`, `secaudit`, `docgen`,
`refactor`, `tracer`, `testgen`, `precommit`, `consensus`.

```json
{
  "debate_mode": {
    "type": "boolean",
    "description": "Enable multi-model debate. When true, the prompt is sent to multiple models in parallel (Round 1), then each model sees all others' responses and critiques them (Round 2). Default: false (single-model).",
    "default": false
  },
  "debate_models": {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "alias": { "type": "string", "description": "Human-readable name for this model in the debate (e.g., 'analyst', 'reviewer')" },
        "model": { "type": "string", "description": "Model identifier (e.g., 'gpt-4o', 'gemini-2.5-pro')" },
        "temperature": { "type": "number", "description": "Optional temperature override for this model" }
      },
      "required": ["alias", "model"]
    },
    "description": "Models to include in the debate. If omitted when debate_mode=true, uses default debate roster from config."
  },
  "session_id": {
    "type": "string",
    "description": "Existing debate session ID for follow-up context. If provided, models receive their prior state from this session."
  },
  "debate_max_rounds": {
    "type": "integer",
    "description": "Maximum debate rounds (1 = independent only, 2 = independent + adversarial). Default: 2.",
    "default": 2
  },
  "synthesis_mode": {
    "type": "string",
    "enum": ["synthesize", "select_best"],
    "description": "How to combine model responses. 'synthesize' (default): merge all perspectives into unified analysis with agreement/disagreement. 'select_best': score each response 1-10 against task objective, return highest-scoring as primary output with all scores. Use 'select_best' with debate_max_rounds=1 for ensemble selection without debate (ablation Config B).",
    "default": "synthesize"
  },
  "enable_context_requests": {
    "type": "boolean",
    "description": "Whether Round 1 prompts include context request instructions and responses are parsed for structured file requests. Default: true. Set false to disable context acquisition between rounds (isolates debate value from information acquisition — ablation Config C vs D).",
    "default": true
  },
  "escalation_mode": {
    "type": "string",
    "enum": ["adaptive", "always_full", "never"],
    "description": "Controls review escalation behavior. 'adaptive' (default): single-model review with auto-escalation on low confidence/high complexity. 'always_full': skip single-model, always use full multi-model debate. 'never': single-model only, no escalation regardless of confidence. Per-call override of global escalation config.",
    "default": "adaptive"
  },
  "escalation_confidence_threshold": {
    "type": "number",
    "description": "Per-call override of ESCALATION_CONFIDENCE_THRESHOLD (0.0-1.0). Only used when escalation_mode='adaptive'. Below this value triggers escalation to full debate.",
    "minimum": 0,
    "maximum": 1
  },
  "escalation_complexity_threshold": {
    "type": "string",
    "enum": ["low", "medium", "high"],
    "description": "Per-call override of ESCALATION_COMPLEXITY_THRESHOLD. Only used when escalation_mode='adaptive'. At or above this value triggers escalation."
  },
  "synthesis_model": {
    "type": "string",
    "description": "Override model for synthesis/selection step. Default: auto-select a model NOT in the debate roster (avoids bias), falling back to highest-capability available."
  }
}
```

**Ablation config mapping:**

| Config | Parameters |
|--------|-----------|
| **A** (baseline) | `debate_mode=false` |
| **B** (ensemble selection) | `debate_mode=true, debate_max_rounds=1, synthesis_mode="select_best"` |
| **C** (debate, no context enrichment) | `debate_mode=true, debate_max_rounds=2, enable_context_requests=false` |
| **D** (debate + context enrichment) | `debate_mode=true, debate_max_rounds=2, enable_context_requests=true` |
| **E** (tiered intensity) | **Multi-call strategy** (caller-orchestrated): Config D params for design-stage calls + `escalation_mode="adaptive"` for implementation-stage calls. The caller decides which calls are "design" vs "implementation" — the tool provides the per-call knobs. |

### Debate Mode Response Format (appended to normal tool output)

When `debate_mode=true`, the tool response includes additional debate metadata:

```json
{
  "content": "... normal tool output (synthesis of debate) ...",
  "debate_metadata": {
    "session_id": "uuid-string",
    "trace_id": "uuid-string",
    "round": 2,
    "synthesis_mode": "synthesize",
    "participation": "3/3",
    "round2_participation": "3/3",
    "responses": [
      {
        "alias": "analyst",
        "model": "gpt-4o",
        "provider": "openai",
        "round1_summary": "Brief summary of Round 1 findings",
        "round2_summary": "Brief summary of Round 2 critique",
        "status": "success",
        "latency_ms": 4200,
        "tokens": { "input": 3400, "output": 1200 }
      }
    ],
    "agreement_points": ["..."],
    "disagreement_points": ["..."],
    "recommendations": ["..."],
    "scores": null,
    "selected_alias": null,
    "selection_rationale": null,
    "context_requests": [
      {
        "artifact_type": "file",
        "path": "src/services/auth.py",
        "rationale": "Need to see the auth middleware implementation",
        "priority": "high",
        "requested_by": "analyst"
      }
    ],
    "timing": {
      "round1_ms": 4500,
      "round2_ms": 5200,
      "synthesis_ms": 3100
    },
    "warnings": []
  }
}
```

### Single-Model Response Format (when `debate_mode=false`)

When a tool runs in single-model mode (including per-stage code reviews), the
response includes an escalation signal for adaptive review intensity (FR-021):

```json
{
  "content": "... normal single-model tool output ...",
  "escalation_signal": {
    "confidence": 0.85,
    "complexity": "medium",
    "anomalies_detected": false,
    "escalation_recommended": false,
    "escalation_reason": null,
    "risk_areas": []
  }
}
```

When escalation is triggered:

```json
{
  "content": "... single-model review flagging concerns ...",
  "escalation_signal": {
    "confidence": 0.35,
    "complexity": "high",
    "anomalies_detected": true,
    "escalation_recommended": true,
    "escalation_reason": "Potential race condition in session cleanup that cannot be validated by conformance check alone — concurrent access to shared state requires multi-model analysis",
    "risk_areas": ["concurrency", "state-management"]
  }
}
```

The orchestrator reads `escalation_recommended` and auto-promotes to full
multi-model debate when `true`. Escalation thresholds are configurable:

```bash
ESCALATION_CONFIDENCE_THRESHOLD=0.6    # Below this → escalate
ESCALATION_COMPLEXITY_THRESHOLD=high   # At or above → escalate
ESCALATION_AUTO_RISK_AREAS=concurrency,auth,persistence,parsing  # Always escalate
```

---

## New Tools

### Tool: `follow_up`

Stateful follow-up to a specific model within an existing debate session.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "description": "Debate session ID (from a prior debate_mode response)"
    },
    "alias": {
      "type": "string",
      "description": "Model alias to follow up with (e.g., 'analyst')"
    },
    "prompt": {
      "type": "string",
      "description": "Follow-up question or instruction"
    },
    "attachments": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Additional file paths to include in this follow-up"
    },
    "checkpoint_name": {
      "type": "string",
      "description": "Optional: create a named checkpoint after this exchange"
    }
  },
  "required": ["session_id", "alias", "prompt"]
}
```

**Output Schema**:
```json
{
  "alias": "string",
  "model": "string",
  "content": "string (model response)",
  "latency_ms": "integer",
  "tokens": { "input": "integer", "output": "integer" },
  "session_exchanges_total": "integer",
  "summary_included": "boolean (whether compressed history was used)",
  "continuation_id": "string (Claude-side conversation threading — separate from session_id. session_id tracks model-side debate state; continuation_id tracks the calling agent's conversation log. Both are returned so the caller can maintain both.)"
}
```

**Error Cases**:
- `session_id` not found → `SessionNotFoundError` (session may have been GC'd)
- `alias` not found in session → `AliasNotFoundError`
- Provider unavailable → `ProviderUnavailableError` with circuit breaker status

---

### Tool: `compare_models`

Query evaluation logs for model performance analysis.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "task_type": {
      "type": "string",
      "description": "Filter by task type (e.g., 'debug', 'codereview'). Omit for all."
    },
    "model": {
      "type": "string",
      "description": "Filter by model (e.g., 'gpt-4o'). Omit for all."
    },
    "since": {
      "type": "string",
      "description": "ISO 8601 date. Only include records after this date."
    },
    "group_by": {
      "type": "string",
      "enum": ["model", "task_type", "model_and_task_type"],
      "description": "How to aggregate results. Default: 'model'.",
      "default": "model"
    }
  },
  "required": []
}
```

**Output Schema**:
```json
{
  "comparisons": [
    {
      "model": "string",
      "task_type": "string or null",
      "query_count": "integer",
      "avg_latency_ms": "integer",
      "total_tokens": "integer",
      "avg_tokens_per_response": "integer",
      "success_rate": "float (0.0–1.0)",
      "follow_up_rate": "float (fraction of sessions with follow-ups)",
      "avg_follow_up_depth": "float (average exchanges per session)"
    }
  ],
  "period": {
    "from": "ISO 8601 date",
    "to": "ISO 8601 date",
    "total_records": "integer"
  }
}
```

---

### Tool: `list_sessions`

List active debate sessions.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "active_only": {
      "type": "boolean",
      "description": "If true, only return non-expired sessions. Default: true.",
      "default": true
    }
  },
  "required": []
}
```

**Output Schema**:
```json
{
  "sessions": [
    {
      "session_id": "string",
      "task_type": "string",
      "status": "string (ACTIVE, COMPLETED, etc.)",
      "created_at": "ISO 8601",
      "last_active_at": "ISO 8601",
      "models": [
        {
          "alias": "string",
          "model": "string",
          "provider": "string",
          "exchange_count": "integer",
          "total_tokens": "integer"
        }
      ]
    }
  ]
}
```

---

### Tool: `destroy_session`

Explicitly destroy a debate session. Evaluation data is preserved.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "description": "Session ID to destroy"
    }
  },
  "required": ["session_id"]
}
```

**Output Schema**:
```json
{
  "destroyed": true,
  "evaluation_data_preserved": true,
  "session_id": "string"
}
```

**Error Cases**:
- `session_id` not found → returns `{ "destroyed": false, "reason": "session not found" }`

---

## Error Response Format

All tools use a consistent error format:

```json
{
  "error": {
    "type": "string (error class name)",
    "message": "string (human-readable description)",
    "provider": "string or null (if provider-specific)",
    "retry_after_ms": "integer or null (for rate limit errors)"
  }
}
```

**Error Types**:
| Error | HTTP Analog | Description |
|-------|-------------|-------------|
| `ProviderUnavailableError` | 503 | API key missing, network down, circuit open |
| `ProviderRateLimitError` | 429 | Rate limit exceeded; includes retry_after_ms |
| `ProviderTimeoutError` | 504 | Exceeded per_model_timeout_ms |
| `ProviderContentFilterError` | 451 | Model refused the prompt |
| `SessionNotFoundError` | 404 | Invalid or expired session_id |
| `AliasNotFoundError` | 404 | Alias not found in session |
| `ConfigurationError` | 500 | Invalid configuration |

---

## Configuration Contract

The fork is configured via environment variables (inherited from PAL/Zen)
plus new debate-specific settings:

```bash
# Existing (inherited from PAL/Zen — use actual env var names from server.py)
OPENAI_API_KEY=...
GEMINI_API_KEY=...                    # NOTE: PAL/Zen uses GEMINI_API_KEY, not GOOGLE_AI_API_KEY
OPENROUTER_API_KEY=...                # For Anthropic models via OpenRouter (PAL/Zen has no native Anthropic provider)
DEFAULT_MODEL=auto

# Master feature flag
DEBATE_FEATURE_ENABLED=true           # Master switch — false disables ALL debate code paths + schema fields

# Debate behavior
DEBATE_DEFAULT_ENABLED=false          # Whether debate_mode defaults to true for applicable tools
DEBATE_DEFAULT_MODELS=gpt-4o,gemini-2.5-pro,anthropic/claude-opus-4.6
DEBATE_MAX_ROUNDS=2                   # Default max rounds per debate
DEBATE_PER_MODEL_TIMEOUT_MS=30000     # Per-model timeout
DEBATE_SUMMARY_STRATEGY=llm           # "llm" or "template"
DEBATE_SYNTHESIS_MODEL=               # Empty = auto-select non-participant; set to override

# Session management
SESSION_GC_IDLE_MINUTES=60            # Idle timeout for session GC
SESSION_MAX_CONCURRENT=20             # Max concurrent sessions (also sizes thread pool)
SESSION_MAX_RECENT_EXCHANGES=3        # Sliding window size

# Evaluation
EVALUATION_LOG_DIR=./logs             # JSONL log directory
EVALUATION_RETENTION_DAYS=30          # Log retention

# Resilience (per-provider)
RATE_LIMIT_RPM_OPENAI=60
RATE_LIMIT_RPM_GOOGLE=60
RATE_LIMIT_RPM_OPENROUTER=60
CIRCUIT_BREAKER_FAILURE_THRESHOLD=3
CIRCUIT_BREAKER_RESET_TIMEOUT_MS=60000

# Adaptive escalation
ESCALATION_CONFIDENCE_THRESHOLD=0.6
ESCALATION_COMPLEXITY_THRESHOLD=high
ESCALATION_AUTO_RISK_AREAS=concurrency,auth,persistence,parsing
```
