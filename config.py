"""
Configuration and constants for PAL MCP Server

This module centralizes all configuration settings for the PAL MCP Server.
It defines model configurations, token limits, temperature defaults, and other
constants used throughout the application.

Configuration values can be overridden by environment variables where appropriate.
"""

from utils.env import get_env

# Version and metadata
# These values are used in server responses and for tracking releases
# IMPORTANT: This is the single source of truth for version and author info
# Semantic versioning: MAJOR.MINOR.PATCH
__version__ = "9.8.2"
# Last update date in ISO format
__updated__ = "2025-12-15"
# Primary maintainer
__author__ = "Fahad Gilani"

# Model configuration
# DEFAULT_MODEL: The default model used for all AI operations
# This should be a stable, high-performance model suitable for code analysis
# Can be overridden by setting DEFAULT_MODEL environment variable
# Special value "auto" means Claude should pick the best model for each task
DEFAULT_MODEL = get_env("DEFAULT_MODEL", "auto") or "auto"

# Auto mode detection - when DEFAULT_MODEL is "auto", Claude picks the model
IS_AUTO_MODE = DEFAULT_MODEL.lower() == "auto"

# Each provider (gemini.py, openai.py, xai.py, dial.py, openrouter.py, custom.py, azure_openai.py)
# defines its own MODEL_CAPABILITIES
# with detailed descriptions. Tools use ModelProviderRegistry.get_available_model_names()
# to get models only from enabled providers (those with valid API keys).
#
# This architecture ensures:
# - No namespace collisions (models only appear when their provider is enabled)
# - API key-based filtering (prevents wrong models from being shown to Claude)
# - Proper provider routing (models route to the correct API endpoint)
# - Clean separation of concerns (providers own their model definitions)


# Temperature defaults for different tool types
# NOTE: Gemini 3.0 Pro notes suggest temperature should be set at 1.0
# in most cases. Lowering it can affect the models 'reasoning' abilities.
# Newer models / inference stacks are able to handle their randomness better.

# Temperature controls the randomness/creativity of model responses
# Lower values (0.0-0.3) produce more deterministic, focused responses
# Higher values (0.7-1.0) produce more creative, varied responses

# TEMPERATURE_ANALYTICAL: Used for tasks requiring precision and consistency
# Ideal for code review, debugging, and error analysis where accuracy is critical
TEMPERATURE_ANALYTICAL = 1.0  # For code review, debugging

# TEMPERATURE_BALANCED: Middle ground for general conversations
# Provides a good balance between consistency and helpful variety
TEMPERATURE_BALANCED = 1.0  # For general chat

# TEMPERATURE_CREATIVE: Higher temperature for exploratory tasks
# Used when brainstorming, exploring alternatives, or architectural discussions
TEMPERATURE_CREATIVE = 1.0  # For architecture, deep thinking

# Thinking Mode Defaults
# DEFAULT_THINKING_MODE_THINKDEEP: Default thinking depth for extended reasoning tool
# Higher modes use more computational budget but provide deeper analysis
DEFAULT_THINKING_MODE_THINKDEEP = get_env("DEFAULT_THINKING_MODE_THINKDEEP", "high") or "high"

# Consensus Tool Defaults
# Consensus timeout and rate limiting settings
DEFAULT_CONSENSUS_TIMEOUT = 120.0  # 2 minutes per model
DEFAULT_CONSENSUS_MAX_INSTANCES_PER_COMBINATION = 2

# NOTE: Consensus tool now uses sequential processing for MCP compatibility
# Concurrent processing was removed to avoid async pattern violations

# MCP Protocol Transport Limits
#
# IMPORTANT: This limit ONLY applies to the Claude CLI ↔ MCP Server transport boundary.
# It does NOT limit internal MCP Server operations like system prompts, file embeddings,
# conversation history, or content sent to external models (Gemini/OpenAI/OpenRouter).
#
# MCP Protocol Architecture:
# Claude CLI ←→ MCP Server ←→ External Model (Gemini/OpenAI/etc.)
#     ↑                              ↑
#     │                              │
# MCP transport                Internal processing
# (token limit from MAX_MCP_OUTPUT_TOKENS)    (No MCP limit - can be 1M+ tokens)
#
# MCP_PROMPT_SIZE_LIMIT: Maximum character size for USER INPUT crossing MCP transport
# The MCP protocol has a combined request+response limit controlled by MAX_MCP_OUTPUT_TOKENS.
# To ensure adequate space for MCP Server → Claude CLI responses, we limit user input
# to roughly 60% of the total token budget converted to characters. Larger user prompts
# must be sent as prompt.txt files to bypass MCP's transport constraints.
#
# Token to character conversion ratio: ~4 characters per token (average for code/text)
# Default allocation: 60% of tokens for input, 40% for response
#
# What IS limited by this constant:
# - request.prompt field content (user input from Claude CLI)
# - prompt.txt file content (alternative user input method)
# - Any other direct user input fields
#
# What is NOT limited by this constant:
# - System prompts added internally by tools
# - File content embedded by tools
# - Conversation history loaded from storage
# - Web search instructions or other internal additions
# - Complete prompts sent to external models (managed by model-specific token limits)
#
# This ensures MCP transport stays within protocol limits while allowing internal
# processing to use full model context windows (200K-1M+ tokens).


def _calculate_mcp_prompt_limit() -> int:
    """
    Calculate MCP prompt size limit based on MAX_MCP_OUTPUT_TOKENS environment variable.

    Returns:
        Maximum character count for user input prompts
    """
    # Check for Claude's MAX_MCP_OUTPUT_TOKENS environment variable
    max_tokens_str = get_env("MAX_MCP_OUTPUT_TOKENS")

    if max_tokens_str:
        try:
            max_tokens = int(max_tokens_str)
            # Allocate 60% of tokens for input, convert to characters (~4 chars per token)
            input_token_budget = int(max_tokens * 0.6)
            character_limit = input_token_budget * 4
            return character_limit
        except (ValueError, TypeError):
            # Fall back to default if MAX_MCP_OUTPUT_TOKENS is not a valid integer
            pass

    # Default fallback: 60,000 characters (equivalent to ~15k tokens input of 25k total)
    return 60_000


MCP_PROMPT_SIZE_LIMIT = _calculate_mcp_prompt_limit()

# Language/Locale Configuration
# LOCALE: Language/locale specification for AI responses
# When set, all AI tools will respond in the specified language while
# maintaining their analytical capabilities
# Examples: "fr-FR", "en-US", "zh-CN", "zh-TW", "ja-JP", "ko-KR", "es-ES",
# "de-DE", "it-IT", "pt-PT"
# Leave empty for default language (English)
LOCALE = get_env("LOCALE", "") or ""

# =============================================================================
# Multi-Model Debate Configuration
# =============================================================================

# Master feature flag — when False, all debate code paths are disabled,
# debate fields excluded from schemas, fork behaves as vanilla PAL/Zen
DEBATE_FEATURE_ENABLED = get_env("DEBATE_FEATURE_ENABLED", "true").lower() == "true"

# Whether debate_mode defaults to true for applicable tools
DEBATE_DEFAULT_ENABLED = get_env("DEBATE_DEFAULT_ENABLED", "false").lower() == "true"

# Default models for debate when debate_models not specified per-call
# Comma-separated model identifiers
DEBATE_DEFAULT_MODELS = [
    m.strip()
    for m in (get_env("DEBATE_DEFAULT_MODELS", "") or "").split(",")
    if m.strip()
]

# Maximum debate rounds (1 = independent only, 2 = independent + adversarial)
DEBATE_MAX_ROUNDS = int(get_env("DEBATE_MAX_ROUNDS", "2") or "2")

# Per-model timeout in milliseconds
DEBATE_PER_MODEL_TIMEOUT_MS = int(
    get_env("DEBATE_PER_MODEL_TIMEOUT_MS", "30000") or "30000"
)

# Summary strategy for session memory compression: "llm" or "template"
DEBATE_SUMMARY_STRATEGY = get_env("DEBATE_SUMMARY_STRATEGY", "llm") or "llm"

# Override model for synthesis step (empty = auto-select non-participant)
DEBATE_SYNTHESIS_MODEL = get_env("DEBATE_SYNTHESIS_MODEL", "") or ""

# =============================================================================
# Session Management Configuration
# =============================================================================

# Idle timeout before session garbage collection (minutes)
SESSION_GC_IDLE_MINUTES = int(
    get_env("SESSION_GC_IDLE_MINUTES", "60") or "60"
)

# Maximum concurrent debate sessions (also sizes the thread pool)
SESSION_MAX_CONCURRENT = int(
    get_env("SESSION_MAX_CONCURRENT", "20") or "20"
)

# Sliding window size for recent verbatim exchanges
SESSION_MAX_RECENT_EXCHANGES = int(
    get_env("SESSION_MAX_RECENT_EXCHANGES", "3") or "3"
)

# =============================================================================
# Evaluation Configuration
# =============================================================================

# Directory for JSONL evaluation logs
EVALUATION_LOG_DIR = get_env("EVALUATION_LOG_DIR", "./logs") or "./logs"

# Log retention in days
EVALUATION_RETENTION_DAYS = int(
    get_env("EVALUATION_RETENTION_DAYS", "30") or "30"
)

# =============================================================================
# Resilience Configuration (per-provider)
# =============================================================================

# Rate limits in requests per minute
RATE_LIMIT_RPM_OPENAI = int(get_env("RATE_LIMIT_RPM_OPENAI", "60") or "60")
RATE_LIMIT_RPM_GOOGLE = int(get_env("RATE_LIMIT_RPM_GOOGLE", "60") or "60")
RATE_LIMIT_RPM_OPENROUTER = int(
    get_env("RATE_LIMIT_RPM_OPENROUTER", "60") or "60"
)

# Circuit breaker settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(
    get_env("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "3") or "3"
)
CIRCUIT_BREAKER_RESET_TIMEOUT_MS = int(
    get_env("CIRCUIT_BREAKER_RESET_TIMEOUT_MS", "60000") or "60000"
)

# =============================================================================
# Adaptive Escalation Configuration
# =============================================================================

# Confidence threshold — below this triggers escalation (0.0-1.0)
ESCALATION_CONFIDENCE_THRESHOLD = float(
    get_env("ESCALATION_CONFIDENCE_THRESHOLD", "0.6") or "0.6"
)

# Complexity threshold — at or above triggers escalation
ESCALATION_COMPLEXITY_THRESHOLD = (
    get_env("ESCALATION_COMPLEXITY_THRESHOLD", "high") or "high"
)

# Risk areas that always trigger escalation (comma-separated)
ESCALATION_AUTO_RISK_AREAS = [
    a.strip()
    for a in (
        get_env("ESCALATION_AUTO_RISK_AREAS", "concurrency,auth,persistence,parsing")
        or "concurrency,auth,persistence,parsing"
    ).split(",")
    if a.strip()
]

# =============================================================================
# Debate Config Validation
# =============================================================================


def validate_debate_config() -> tuple[list[str], list[str]]:
    """
    Validate all debate configuration at startup.

    Returns a list of warning messages (non-fatal). Raises ConfigurationError
    for fatal misconfigurations (import from debate.errors deferred to avoid
    circular imports — this function returns errors as strings for the caller
    to handle).
    """
    warnings = []
    errors = []

    # Range validation
    if not (0.0 <= ESCALATION_CONFIDENCE_THRESHOLD <= 1.0):
        errors.append(
            f"ESCALATION_CONFIDENCE_THRESHOLD={ESCALATION_CONFIDENCE_THRESHOLD} "
            f"must be between 0.0 and 1.0"
        )

    if ESCALATION_COMPLEXITY_THRESHOLD not in ("low", "medium", "high"):
        errors.append(
            f"ESCALATION_COMPLEXITY_THRESHOLD='{ESCALATION_COMPLEXITY_THRESHOLD}' "
            f"must be 'low', 'medium', or 'high'"
        )

    if DEBATE_MAX_ROUNDS < 1:
        errors.append(f"DEBATE_MAX_ROUNDS={DEBATE_MAX_ROUNDS} must be >= 1")

    if DEBATE_PER_MODEL_TIMEOUT_MS <= 0:
        errors.append(
            f"DEBATE_PER_MODEL_TIMEOUT_MS={DEBATE_PER_MODEL_TIMEOUT_MS} must be > 0"
        )

    if SESSION_GC_IDLE_MINUTES <= 0:
        errors.append(
            f"SESSION_GC_IDLE_MINUTES={SESSION_GC_IDLE_MINUTES} must be > 0"
        )

    if SESSION_MAX_CONCURRENT <= 0:
        errors.append(
            f"SESSION_MAX_CONCURRENT={SESSION_MAX_CONCURRENT} must be > 0"
        )

    if DEBATE_SUMMARY_STRATEGY not in ("llm", "template"):
        errors.append(
            f"DEBATE_SUMMARY_STRATEGY='{DEBATE_SUMMARY_STRATEGY}' "
            f"must be 'llm' or 'template'"
        )

    # Cross-field validation
    if DEBATE_DEFAULT_ENABLED and len(DEBATE_DEFAULT_MODELS) < 2:
        errors.append(
            f"DEBATE_DEFAULT_ENABLED=true requires at least 2 models in "
            f"DEBATE_DEFAULT_MODELS (got {len(DEBATE_DEFAULT_MODELS)})"
        )

    # Warnings for optional config
    if DEBATE_FEATURE_ENABLED and not DEBATE_DEFAULT_MODELS:
        warnings.append(
            "DEBATE_DEFAULT_MODELS is empty — callers must specify "
            "debate_models explicitly on every debate call"
        )

    if DEBATE_SYNTHESIS_MODEL:
        warnings.append(
            f"DEBATE_SYNTHESIS_MODEL='{DEBATE_SYNTHESIS_MODEL}' set — "
            f"overrides automatic non-participant selection"
        )

    return warnings, errors


# =============================================================================
# Threading configuration
# =============================================================================
# Simple in-memory conversation threading for stateless MCP environment
# Conversations persist only during the Claude session
