# Quickstart: Multi-Model Agent Teams

**Phase 1 output for**: `/specs/001-multi-model-agent-teams/plan.md`
**Date**: 2026-03-22

## Prerequisites

- Python 3.12+
- API keys for at least 2 of: OpenAI, Google AI, Anthropic
- Claude Code (or any MCP-compatible client)
- Git (for fork management)

## Setup

### 1. Fork and Clone

```bash
# Fork the upstream PAL/Zen repo on GitHub, then:
git clone https://github.com/<your-org>/pal-mcp-server.git pal-debate-server
cd pal-debate-server

# Add upstream remote for future syncs
git remote add upstream https://github.com/BeehiveInnovations/pal-mcp-server.git
```

### 2. Install Dependencies

```bash
# Create virtual environment
python3.12 -m venv .pal_venv
source .pal_venv/bin/activate

# Install dependencies (inherited requirements + new ones)
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy example env and fill in API keys
cp .env.example .env

# Required: at least 2 of these for debate mode
OPENAI_API_KEY=sk-...
GOOGLE_AI_API_KEY=AIza...
ANTHROPIC_API_KEY=sk-ant-...

# Optional: debate-specific settings
DEBATE_DEFAULT_ENABLED=false
DEBATE_DEFAULT_MODELS=gpt-4o,gemini-2.5-pro,claude-sonnet-4-6
SESSION_GC_IDLE_MINUTES=60
```

### 4. Register with Claude Code

Add to `~/.claude/settings.json` (or project `.claude/settings.json`):

```json
{
  "mcpServers": {
    "debate": {
      "command": "python",
      "args": ["/absolute/path/to/pal-debate-server/server.py"],
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "GOOGLE_AI_API_KEY": "AIza...",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

### 5. Verify Installation

Restart Claude Code, then:

```
Use mcp__debate__listmodels to show available models
```

You should see models from all configured providers.

## Usage Examples

### Multi-Model Debug (Debate Mode)

```
Use mcp__debate__debug with debate_mode=true to analyze this race condition:
[paste code and error description]
```

The tool will:
1. Send your bug report to 3 models in parallel (Round 1)
2. Share all Round 1 responses and ask models to critique each other (Round 2)
3. Synthesize agreement/disagreement/recommendations
4. Return a session_id for follow-ups

### Follow Up on a Debate

```
Use mcp__debate__follow_up with session_id="abc-123" alias="analyst"
to ask: "Your race condition theory — trace the exact lock sequence"
```

The model receives its compressed prior analysis + your new question.

### Single-Model Mode (Conformance Checks)

```
Use mcp__debate__codereview to check if this implementation matches the design
[paste code]
```

Without `debate_mode=true`, tools work exactly like the original PAL/Zen —
single-model analysis. Use this for conformance checks during implementation.

### Evaluate Model Performance

```
Use mcp__debate__compare_models with group_by="model_and_task_type"
since="2026-03-14" to see which models perform best at which tasks
```

## Running Quality Checks

```bash
source .pal_venv/bin/activate

# Run all quality checks
./code_quality_checks.sh

# Run integration tests
./run_integration_tests.sh

# Run quick simulator tests
python communication_simulator_test.py --quick
```

## Development Workflow

1. Make changes
2. Run `./code_quality_checks.sh`
3. Run relevant tests
4. Restart Claude Code session (MCP server reloads on restart)
5. Test with real multi-model debate

## Upstream Sync

```bash
# Fetch upstream changes
git fetch upstream

# Merge upstream main into your branch
git merge upstream/main

# Resolve conflicts (fork additions in debate/, sessions/, evaluation/,
# resilience/ should not conflict with upstream changes)
```
