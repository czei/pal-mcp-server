# Copyright 2026 — Multi-Model Agent Teams (fork of PAL MCP Server)
# Original work Copyright 2024-2025 Fahad Gilani / Beehive Innovations
# Licensed under the Apache License, Version 2.0

"""
Debate orchestrator: coordinates async worker coroutines for multi-model debate.

Workers are async coroutines that maintain per-model messages[] arrays.
Blocking provider.generate_content() is offloaded via asyncio.to_thread().
The orchestrator coordinates rounds by dispatching tasks to workers and
gathering results.

See research.md R-011, R-012 for architecture rationale.
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Optional

from debate.context_requests import deduplicate_requests, parse_context_requests
from debate.errors import (
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from debate.prompts import (
    build_context_request_instruction,
    build_round2_prompt,
)
from debate.synthesis import select_best, select_synthesis_model, synthesize
from evaluation.logger import EvaluationLogger
from evaluation.metrics import build_evaluation_record
from resilience.circuit_breaker import CircuitBreaker
from resilience.rate_limiter import TokenBucketRateLimiter
from sessions.types import (
    DebateConfig,
    DebateSession,
    ModelState,
    SessionStatus,
    WorkerRuntime,
)
from tools.models import (
    DebateResult,
    DebateWarning,
    ModelDebateResponse,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Per-model round execution (T014 + T023)
# =============================================================================


# Maximum retry attempts for transient failures
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 1.0  # seconds


async def _execute_round_for_model(
    runtime: WorkerRuntime,
    model_state: ModelState,
    provider_call_fn: Callable,
    user_content: str,
    timeout_ms: int,
    round_num: int,
) -> dict[str, Any]:
    """
    Execute one round for one model with retry on transient failures (T029).

    Appends to messages[], calls provider, appends response. Retries on
    timeout or transient errors with exponential backoff, respecting
    circuit breaker state (guarded_call handles this).

    Args:
        runtime: WorkerRuntime holding this model's messages[].
        model_state: ModelState metadata.
        provider_call_fn: Async callable(messages, model_id) → response dict.
        user_content: The user prompt for this round.
        timeout_ms: Timeout in milliseconds.
        round_num: Round number (for logging).

    Returns:
        Dict with content, latency_ms, tokens, status, error.
    """
    result = {
        "content": "",
        "latency_ms": 0,
        "tokens": {"input": 0, "output": 0},
        "status": "pending",
        "error": None,
    }

    runtime.messages.append({"role": "user", "content": user_content})
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            start = time.monotonic()
            response = await asyncio.wait_for(
                provider_call_fn(runtime.messages, model_state.model_id),
                timeout=timeout_ms / 1000.0,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)

            content = response.get("content", "")
            runtime.messages.append({"role": "assistant", "content": content})

            result["content"] = content
            result["latency_ms"] = elapsed_ms
            result["tokens"] = response.get("tokens", {"input": 0, "output": 0})
            result["status"] = "success"

            model_state.total_exchange_count += 1
            model_state.total_input_tokens += result["tokens"].get("input", 0)
            model_state.total_output_tokens += result["tokens"].get("output", 0)

            return result

        except asyncio.TimeoutError:
            last_error = f"Round {round_num} timed out after {timeout_ms}ms"
            if attempt < MAX_RETRIES:
                backoff = RETRY_BACKOFF_BASE * (2**attempt)
                logger.info(
                    f"Worker {model_state.alias}: Round {round_num} timeout, "
                    f"retry {attempt + 1}/{MAX_RETRIES} in {backoff}s"
                )
                await asyncio.sleep(backoff)
            else:
                result["status"] = "timeout"
                result["error"] = last_error

        except (ProviderUnavailableError, ProviderTimeoutError) as e:
            # Circuit breaker open or provider down — don't retry
            last_error = str(e)
            result["status"] = "error"
            result["error"] = last_error
            break

        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                backoff = RETRY_BACKOFF_BASE * (2**attempt)
                logger.info(
                    f"Worker {model_state.alias}: Round {round_num} error ({e}), "
                    f"retry {attempt + 1}/{MAX_RETRIES} in {backoff}s"
                )
                await asyncio.sleep(backoff)
            else:
                result["status"] = "error"
                result["error"] = last_error

    # All retries exhausted — clean up the unanswered user message
    if runtime.messages and runtime.messages[-1]["role"] == "user":
        runtime.messages.pop()
    logger.warning(
        f"Worker {model_state.alias}: Round {round_num} failed after " f"{MAX_RETRIES + 1} attempts: {last_error}"
    )

    return result


# =============================================================================
# Debate Orchestrator (T015 + T023)
# =============================================================================


class DebateOrchestrator:
    """
    Coordinates multi-model debate via async worker coroutines.

    The orchestrator dispatches rounds to workers using asyncio.gather()
    and collects results. Each worker maintains its own messages[] array
    for native multi-turn context with its provider.
    """

    def __init__(
        self,
        session_manager,
        rate_limiters: Optional[dict[str, TokenBucketRateLimiter]] = None,
        circuit_breakers: Optional[dict[str, CircuitBreaker]] = None,
    ):
        self.session_manager = session_manager
        self.rate_limiters = rate_limiters or {}
        self.circuit_breakers = circuit_breakers or {}
        self.eval_logger = EvaluationLogger()

    async def run_debate(
        self,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
        model_configs: list[dict[str, Any]],
        debate_config: Optional[DebateConfig] = None,
        provider_call_fn: Optional[Callable] = None,
        available_models: Optional[list[dict[str, Any]]] = None,
    ) -> DebateResult:
        """
        Run a complete multi-model debate.

        Flow: Create session → Round 1 (parallel) → Round 2 (parallel) → Synthesis.
        In MVP, Round 2 fires immediately after Round 1 (no context enrichment).

        Returns:
            DebateResult with all responses, synthesis, and metadata.
        """
        dc = debate_config or DebateConfig()
        trace_id = str(uuid.uuid4())
        timing = {"round1_ms": 0, "round2_ms": 0, "synthesis_ms": 0}

        # Create session
        session = await self.session_manager.create_session(
            task_type=task_type,
            model_configs=model_configs,
            debate_config=dc,
        )
        session.trace_id = trace_id
        session.shared_context.original_prompt = user_prompt
        session.shared_context.task_specific_prompt = system_prompt

        runtimes = self.session_manager.get_all_worker_runtimes(session.id)

        # Initialize each worker's messages with system prompt
        for _alias, runtime in runtimes.items():
            runtime.messages = [{"role": "system", "content": system_prompt}]

        # Build guarded provider call (rate limit + circuit breaker)
        guarded_call = self._build_guarded_call(model_configs, provider_call_fn)

        # Session cleanup on failure (fixes medium issue #8)
        try:
            return await self._execute_debate_rounds(
                session=session,
                dc=dc,
                trace_id=trace_id,
                timing=timing,
                runtimes=runtimes,
                guarded_call=guarded_call,
                user_prompt=user_prompt,
                model_configs=model_configs,
                provider_call_fn=provider_call_fn,
                available_models=available_models,
            )
        except Exception:
            session.status = SessionStatus.EXPIRED
            await self.session_manager.update_session(session)
            raise

    async def _execute_debate_rounds(
        self,
        session: DebateSession,
        dc: DebateConfig,
        trace_id: str,
        timing: dict,
        runtimes: dict,
        guarded_call,
        user_prompt: str,
        model_configs: list[dict[str, Any]],
        provider_call_fn,
        available_models,
    ) -> DebateResult:
        """Execute the actual debate rounds. Extracted for try/finally in run_debate."""

        # ── Round 1: Independent Analysis (parallel) ──
        round1_start = time.monotonic()
        session.round = 1

        r1_user_content = user_prompt
        if dc.enable_context_requests:
            r1_user_content += build_context_request_instruction()

        # Dispatch Round 1 to all models in parallel
        r1_tasks = {
            alias: _execute_round_for_model(
                runtime=runtimes[alias],
                model_state=session.models[alias],
                provider_call_fn=guarded_call,
                user_content=r1_user_content,
                timeout_ms=dc.per_model_timeout_ms,
                round_num=1,
            )
            for alias in runtimes
        }
        r1_results = {}
        gathered = await asyncio.gather(
            *[r1_tasks[a] for a in r1_tasks],
            return_exceptions=True,
        )
        for alias, result in zip(r1_tasks.keys(), gathered):
            if isinstance(result, Exception):
                r1_results[alias] = {
                    "content": "",
                    "status": "error",
                    "error": str(result),
                    "latency_ms": 0,
                    "tokens": {"input": 0, "output": 0},
                }
            else:
                r1_results[alias] = result

        timing["round1_ms"] = int((time.monotonic() - round1_start) * 1000)

        # Collect Round 1 successes/failures
        round1_ok: dict[str, str] = {}
        round1_failed: dict[str, str] = {}
        warnings: list[DebateWarning] = []

        for alias, r in r1_results.items():
            if r["status"] == "success":
                round1_ok[alias] = r["content"]
            else:
                round1_failed[alias] = r.get("error", r["status"])
                warnings.append(
                    DebateWarning(
                        alias=alias,
                        model=session.models[alias].model_id,
                        error=r["status"],
                        message=r.get("error", ""),
                    )
                )

        session.shared_context.round1_responses = round1_ok

        # Log Round 1 results to evaluation (T050)
        for alias, r in r1_results.items():
            ms = session.models[alias]
            await self.eval_logger.log_event(
                build_evaluation_record(
                    event="debate_round",
                    session_id=session.id,
                    trace_id=trace_id,
                    alias=alias,
                    model=ms.model_id,
                    provider=ms.provider_name,
                    task_type=session.task_type,
                    round_num=1,
                    input_tokens=r.get("tokens", {}).get("input", 0),
                    output_tokens=r.get("tokens", {}).get("output", 0),
                    latency_ms=r.get("latency_ms", 0),
                    status=r.get("status", "error"),
                    error_message=r.get("error"),
                )
            )

        # Parse context requests from Round 1 responses (T040)
        all_context_requests = []
        if dc.enable_context_requests:
            for alias, content in round1_ok.items():
                reqs = parse_context_requests(content, requested_by=alias)
                all_context_requests.extend(reqs)
            all_context_requests = deduplicate_requests(all_context_requests)

        # Participation reporting (T024)
        participation = self._format_participation(len(round1_ok), len(model_configs), round1_failed)

        # ── Round 2: Adversarial Critique (parallel) ──
        round2_participation = ""
        round2_results: dict[str, dict] = {}

        if dc.max_round >= 2 and len(round1_ok) >= 2:
            round2_start = time.monotonic()
            session.round = 2

            r2_tasks = {}
            for alias in round1_ok:
                # Each model sees all OTHER models' Round 1 responses
                other_responses = {a: c for a, c in round1_ok.items() if a != alias}
                r2_prompt = build_round2_prompt(
                    original_prompt=user_prompt,
                    round1_responses=other_responses,
                    failed_aliases=round1_failed or None,
                )
                r2_tasks[alias] = _execute_round_for_model(
                    runtime=runtimes[alias],
                    model_state=session.models[alias],
                    provider_call_fn=guarded_call,
                    user_content=r2_prompt,
                    timeout_ms=dc.per_model_timeout_ms,
                    round_num=2,
                )

            gathered2 = await asyncio.gather(
                *[r2_tasks[a] for a in r2_tasks],
                return_exceptions=True,
            )
            for alias, result in zip(r2_tasks.keys(), gathered2):
                if isinstance(result, Exception):
                    round2_results[alias] = {
                        "content": "",
                        "status": "error",
                        "error": str(result),
                        "latency_ms": 0,
                        "tokens": {"input": 0, "output": 0},
                    }
                else:
                    round2_results[alias] = result

            timing["round2_ms"] = int((time.monotonic() - round2_start) * 1000)

            # Log Round 2 results to evaluation (fix #2)
            for alias, r in round2_results.items():
                ms = session.models[alias]
                await self.eval_logger.log_event(
                    build_evaluation_record(
                        event="debate_round",
                        session_id=session.id,
                        trace_id=trace_id,
                        alias=alias,
                        model=ms.model_id,
                        provider=ms.provider_name,
                        task_type=session.task_type,
                        round_num=2,
                        input_tokens=r.get("tokens", {}).get("input", 0),
                        output_tokens=r.get("tokens", {}).get("output", 0),
                        latency_ms=r.get("latency_ms", 0),
                        status=r.get("status", "error"),
                        error_message=r.get("error"),
                    )
                )

            r2_ok = {a for a, r in round2_results.items() if r["status"] == "success"}
            r2_failed = {a: r.get("error", r["status"]) for a, r in round2_results.items() if r["status"] != "success"}
            round2_participation = self._format_participation(len(r2_ok), len(round1_ok), r2_failed)

            # Add Round 2 failures to warnings
            for alias, reason in r2_failed.items():
                warnings.append(
                    DebateWarning(
                        alias=alias,
                        model=session.models[alias].model_id,
                        error="round2_" + round2_results[alias]["status"],
                        message=reason,
                    )
                )
        elif dc.max_round < 2:
            round2_participation = "skipped (max_rounds=1)"
        else:
            round2_participation = "skipped (insufficient Round 1 responses)"

        # Build ModelDebateResponse list (fixes medium #10: partial status)
        responses = self._build_responses(model_configs, r1_results, round2_results)

        # ── Synthesis ──
        synthesis_result = None
        if len(round1_ok) >= 1 and provider_call_fn:
            session.status = SessionStatus.SYNTHESIZING
            synthesis_start = time.monotonic()

            synthesis_result = await self._run_synthesis(
                dc=dc,
                user_prompt=user_prompt,
                round1_ok=round1_ok,
                round2_results=round2_results,
                model_configs=model_configs,
                provider_call_fn=provider_call_fn,
                available_models=available_models,
                warnings=warnings,
            )

            timing["synthesis_ms"] = int((time.monotonic() - synthesis_start) * 1000)

            # Log synthesis to evaluation (fix #2)
            synth_model_name = synthesis_result.synthesizer_model if synthesis_result else "unknown"
            await self.eval_logger.log_event(
                build_evaluation_record(
                    event="synthesis",
                    session_id=session.id,
                    trace_id=trace_id,
                    alias="synthesizer",
                    model=synth_model_name,
                    provider="auto",
                    task_type=session.task_type,
                    round_num=0,
                    latency_ms=timing["synthesis_ms"],
                    status="success" if synthesis_result else "error",
                )
            )

        # Finalize
        session.status = SessionStatus.COMPLETED
        await self.session_manager.update_session(session)

        return DebateResult(
            session_id=session.id,
            trace_id=trace_id,
            responses=responses,
            context_requests=[r.model_dump() for r in all_context_requests],
            synthesis=synthesis_result,
            warnings=warnings,
            participation=participation,
            round2_participation=round2_participation,
            timing=timing,
        )

    # ─────────────────────────────────────────────────────────────
    # Context Enrichment (T040)
    # ─────────────────────────────────────────────────────────────

    async def accept_gathered_artifacts(
        self,
        session_id: str,
        artifacts: list[dict[str, Any]],
    ) -> None:
        """
        Accept gathered artifacts from the caller between Round 1 and Round 2.

        Called after the caller receives context_requests from DebateResult,
        gathers the files, and provides them back. Populates SharedContext.

        Args:
            session_id: The debate session ID.
            artifacts: List of {path, content} dicts.
        """
        from sessions.types import Attachment

        session = await self.session_manager.get_session(session_id)
        if not session:
            from debate.errors import SessionNotFoundError

            raise SessionNotFoundError(session_id)

        session.shared_context.gathered_artifacts = [
            Attachment(
                path=a.get("path", ""),
                content=a.get("content", ""),
                token_count=len(a.get("content", "")) // 4,
                source="gathered",
            )
            for a in artifacts
        ]
        await self.session_manager.update_session(session)
        logger.info(f"Session {session_id}: accepted {len(artifacts)} gathered artifacts")

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _build_guarded_call(
        self,
        model_configs: list[dict[str, Any]],
        provider_call_fn: Callable,
    ) -> Callable:
        """Wrap provider call with rate limiting and circuit breaking."""
        model_provider_map = {mc["model"]: mc.get("provider_name") for mc in model_configs}

        async def _guarded(messages, model_id):
            provider_name = model_provider_map.get(model_id)

            if provider_name and provider_name in self.rate_limiters:
                await self.rate_limiters[provider_name].acquire()
            if provider_name and provider_name in self.circuit_breakers:
                await self.circuit_breakers[provider_name].check()

            try:
                result = await asyncio.get_running_loop().run_in_executor(
                    self.session_manager.executor,
                    provider_call_fn,
                    messages,
                    model_id,
                )
                if provider_name and provider_name in self.circuit_breakers:
                    await self.circuit_breakers[provider_name].record_success()
                return result
            except Exception:
                if provider_name and provider_name in self.circuit_breakers:
                    await self.circuit_breakers[provider_name].record_failure()
                # Refund rate limit token on failure (medium issue #9)
                if provider_name and provider_name in self.rate_limiters:
                    await self.rate_limiters[provider_name].release()
                raise

        return _guarded

    @staticmethod
    def _format_participation(
        ok_count: int,
        total: int,
        failed: dict[str, str],
    ) -> str:
        """Format participation string: '3/3' or '2/3 — alpha: timeout'."""
        s = f"{ok_count}/{total}"
        if failed:
            details = ", ".join(f"{a}: {r}" for a, r in failed.items())
            s += f" — {details}"
        return s

    @staticmethod
    def _build_responses(
        model_configs: list[dict[str, Any]],
        r1_results: dict[str, dict],
        r2_results: dict[str, dict],
    ) -> list[ModelDebateResponse]:
        """Build the list of per-model debate responses."""
        responses = []
        for mc in model_configs:
            alias = mc["alias"]
            r1 = r1_results.get(alias, {})
            r2 = r2_results.get(alias, {})

            r1_tokens = r1.get("tokens", {"input": 0, "output": 0})
            r2_tokens = r2.get("tokens", {"input": 0, "output": 0})

            # Determine composite status (fixes medium issue #10)
            r1_status = r1.get("status", "failed")
            r2_status = r2.get("status") if r2 else None
            if r1_status == "success" and r2_status and r2_status != "success":
                composite_status = "partial"  # R1 ok but R2 failed
            else:
                composite_status = r1_status

            responses.append(
                ModelDebateResponse(
                    alias=alias,
                    model=mc["model"],
                    provider=mc.get("provider_name", "unknown"),
                    round1_content=r1.get("content", ""),
                    round2_content=r2.get("content") if r2 else None,
                    latency_ms=r1.get("latency_ms", 0) + r2.get("latency_ms", 0),
                    tokens={
                        "input": r1_tokens.get("input", 0) + r2_tokens.get("input", 0),
                        "output": r1_tokens.get("output", 0) + r2_tokens.get("output", 0),
                    },
                    status=composite_status,
                )
            )
        return responses

    async def _run_synthesis(
        self,
        dc: DebateConfig,
        user_prompt: str,
        round1_ok: dict[str, str],
        round2_results: dict[str, dict],
        model_configs: list[dict[str, Any]],
        provider_call_fn: Callable,
        available_models: Optional[list[dict[str, Any]]],
        warnings: list[DebateWarning],
    ):
        """Run synthesis (synthesize or select_best mode)."""
        debate_roster = [mc["model"] for mc in model_configs]
        synth_model = select_synthesis_model(
            debate_roster=debate_roster,
            override=dc.synthesis_model,
            available_models=available_models,
        )
        # Fallback: if no synthesis model selected, use the first successful model
        if not synth_model and round1_ok:
            first_alias = next(iter(round1_ok))
            for mc in model_configs:
                if mc["alias"] == first_alias:
                    synth_model = mc["model"]
                    break
        if not synth_model and model_configs:
            synth_model = model_configs[0]["model"]

        async def synth_call(prompt, model):
            msgs = [
                {"role": "system", "content": "You are an expert analyst synthesizing a multi-model debate."},
                {"role": "user", "content": prompt},
            ]
            result = await asyncio.get_running_loop().run_in_executor(
                self.session_manager.executor,
                provider_call_fn,
                msgs,
                model,
            )
            return result.get("content", "")

        try:
            round2_ok = {
                a: r["content"] for a, r in round2_results.items() if r.get("status") == "success" and r.get("content")
            }

            if dc.synthesis_mode == "select_best":
                best_responses = round2_ok if round2_ok else round1_ok
                return await select_best(
                    original_prompt=user_prompt,
                    responses=best_responses,
                    provider_call_fn=synth_call,
                    synthesis_model=synth_model,
                )
            else:
                return await synthesize(
                    original_prompt=user_prompt,
                    round1_responses=round1_ok,
                    round2_responses=round2_ok or round1_ok,
                    provider_call_fn=synth_call,
                    synthesis_model=synth_model,
                )
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            warnings.append(
                DebateWarning(
                    alias="synthesizer",
                    model=synth_model or "unknown",
                    error="synthesis_failed",
                    message=str(e),
                )
            )
            return None
