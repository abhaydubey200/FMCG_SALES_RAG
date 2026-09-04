"""
Provider Policy — explicit, bounded provider selection for LLM synthesis.

Policy classes:
    FAST      → 0 LLM (template/deterministic; handled by the orchestrator)
    STANDARD  → Groq (single call, ~100-500ms)
    COMPLEX   → Groq first; NVIDIA once, strictly time-boxed, only on Groq failure

Rules:
  - NEVER wait on both providers for one request (no sequential double wait).
  - Fallback is bounded: max one retry per provider, hard timeouts.
  - Structured logs: provider, model, purpose, latency_ms, success, tokens.
  - API keys are never logged.
"""
import json
import logging
import threading
import time
from typing import Any, Dict, Optional

from src import config

logger = logging.getLogger("llm.provider_policy")

_stats_lock = threading.Lock()
_stats = {"groq_calls": 0, "nvidia_calls": 0, "fallback_calls": 0,
          "groq_failures": 0, "nvidia_failures": 0}


def _log_call(purpose: str, provider: str, model: str, latency_ms: float,
              success: bool, usage: Optional[Dict] = None,
              fallback_reason: str = "", error: str = ""):
    """Structured LLM call log (no secrets)."""
    with _stats_lock:
        _stats[f"{provider}_calls"] += 1
        if not success:
            _stats[f"{provider}_failures"] += 1
    record = {
        "event": "llm_call",
        "provider": provider,
        "model": model,
        "purpose": purpose,
        "latency_ms": round(latency_ms, 1),
        "success": success,
    }
    if usage:
        record["input_tokens"] = usage.get("prompt_tokens")
        record["output_tokens"] = usage.get("completion_tokens")
    if fallback_reason:
        record["fallback_reason"] = fallback_reason
    if error:
        record["error"] = error[:200]
    logger.info(json.dumps(record))


def get_provider_stats() -> Dict[str, Any]:
    with _stats_lock:
        return dict(_stats)


def _groq_available() -> bool:
    return bool(config.GROQ_API_KEY)


def _nvidia_available() -> bool:
    return bool(config.LLM_API_KEY)


def _strip_thinking(text: str) -> str:
    """Strip reasoning/thinking blocks that some models prefix into content."""
    import re
    out = text or ""
    patterns = [
        r"<think>.*?</think>",
        r"Here'?s? (?:a |the )?thinking process[:\s]*(?:\n|\r).*?(?:\n\s*\n|$)",
        r"Let me (?:analyze|think|consider|work through).*?(?:\n\s*\n|$)",
        r"^\s*\n*\s*<think>.*",
        # Leading numbered reasoning steps some NVIDIA reasoning models emit, e.g.
        # "1. **Parse Question**: ...\n2. **Gather Evidence**: ...\n3. **Conclude**: ..."
        # Strip consecutive leading step blocks only (never mid-answer content).
        r"^(?:\s*\d+\.\s*\*+[A-Z][A-Za-z ]+\*+\s*:.*?\n)+\s*",
    ]
    for pat in patterns:
        out = re.sub(pat, "", out, flags=re.DOTALL | re.IGNORECASE)
    return out.strip()


# Streaming/prompt-relevant block for provider_policy.generate_with_policy
_EMPTY_RETRY_ONCE = True


def _groq_synthesis_timeout() -> float:
    """Bounded Groq timeout for synthesis calls.

    Config default is 30s (used for interactive/direct calls); synthesis must
    stay inside the <10s complex target, so Groq is capped at 8s and a slow
    Groq response degrades to the NVIDIA bounded fallback instead of blocking.
    A healthy Groq call (~1-2s) is unaffected by this cap.
    """
    configured = int(getattr(config, "GROQ_TIMEOUT_SECONDS", 30) or 30)
    return float(min(configured, 8))


def stream_with_policy(
    prompt: str,
    system: str = None,
    purpose: str = "synthesis",
    max_tokens: int = 700,
    complexity: str = "standard",
):
    """Stream exactly one bounded LLM response, yielding events:

      {"type": "chunk", "text": str}   → real generated text, as it arrives
      {"type": "done", "provider", "model", "ttft_ms", "latency_ms",
       "usage", "success": bool}       → final per-call metadata

    Policy: Groq streamed first (fast path); NVIDIA bounded non-streamed fallback
    (COMPLEX only / when Groq unavailable); empty "done" with success=False on
    total failure so callers can fall back to a deterministic answer.
    """
    t0 = time.time()
    ttft_ms = None

    # ── 1) Groq streaming fast path ──
    if _groq_available():
        try:
            from src.llm.groq_client import GroqLLM
            llm = GroqLLM()
            timeout = _groq_synthesis_timeout()
            pieces = []
            for piece in llm.generate_stream(prompt, system=system,
                                             max_tokens=max_tokens, timeout=timeout):
                if not piece:
                    continue
                if ttft_ms is None:
                    ttft_ms = (time.time() - t0) * 1000
                pieces.append(piece)
                yield {"type": "chunk", "text": piece}
            text = "".join(pieces).strip()
            latency = (time.time() - t0) * 1000
            if text:
                _log_call(purpose, "groq", llm.model, latency, True)
                yield {"type": "done", "provider": "groq", "model": llm.model,
                       "ttft_ms": round(ttft_ms or latency, 1),
                       "latency_ms": round(latency, 1),
                       "usage": None, "success": True}
                return
            logger.warning("Groq stream returned empty content (%.0fms)", latency)
        except Exception as e:
            latency = (time.time() - t0) * 1000
            _log_call(purpose, "groq", config.GROQ_MODEL, latency, False,
                      fallback_reason="groq_error", error=str(e))
            logger.warning("Groq stream failed (%.0fms): %s", latency, str(e)[:150])

    # ── 2) NVIDIA bounded fallback (non-streamed, single attempt) ──
    if _nvidia_available() and (complexity == "complex" or not _groq_available()):
        try:
            from src.llm.nvidia_client import NVIDIALLM
            llm = NVIDIALLM()
            timeout = min(int(getattr(config, "LLM_TIMEOUT_SECONDS", 60) or 60), 45)
            response = llm.generate(prompt, system=system,
                                    max_tokens=max(max_tokens, 600), timeout=timeout)
            text = _strip_thinking(response.text)
            latency = (time.time() - t0) * 1000
            if text:
                _log_call(purpose, "nvidia", response.model_name, latency, True,
                          response.usage,
                          fallback_reason="groq_fallback" if _groq_available() else "")
                yield {"type": "chunk", "text": text}
                yield {"type": "done", "provider": "nvidia", "model": response.model_name,
                       "ttft_ms": round(ttft_ms or latency, 1),
                       "latency_ms": round(latency, 1),
                       "usage": response.usage, "success": True}
                return
        except Exception as e:
            latency = (time.time() - t0) * 1000
            _log_call(purpose, "nvidia", config.LLM_MODEL, latency, False,
                      fallback_reason="nvidia_error", error=str(e))
            logger.warning("NVIDIA fallback failed (%.0fms): %s", latency, str(e)[:150])

    # ── 3) Total failure — caller degrades to deterministic answer ──
    yield {"type": "done", "provider": None, "model": None,
           "ttft_ms": None, "latency_ms": round((time.time() - t0) * 1000, 1),
           "usage": None, "success": False}


def generate_with_policy(
    prompt: str,
    system: str = None,
    purpose: str = "synthesis",
    max_tokens: int = 700,
    complexity: str = "standard",
) -> Dict[str, Any]:
    """Make exactly one bounded LLM call (or one bounded fallback).

    Returns {"text", "provider", "model", "latency_ms", "success", "usage"}.
    Raises on total failure so callers can degrade gracefully.
    """
    t0 = time.time()

    # ── 1) Groq fast path ──
    if _groq_available():
        try:
            from src.llm.groq_client import GroqLLM
            llm = GroqLLM()
            timeout = _groq_synthesis_timeout()
            response = llm.generate(prompt, system=system, max_tokens=max_tokens, timeout=timeout)
            text = _strip_thinking(response.text)
            # Reasoning-heavy models can exhaust the budget without content — retry
            # once, but ONLY when the first call was fast (<4s). A slow empty
            # response is NOT retried: the extra call would double an already
            # pathological latency; degrade to NVIDIA/fallback instead.
            if (not text and _EMPTY_RETRY_ONCE
                    and (time.time() - t0) < 4.0):
                response = llm.generate(prompt, system=system,
                                        max_tokens=max(max_tokens * 2, 512), timeout=timeout)
                text = _strip_thinking(response.text)
            latency = (time.time() - t0) * 1000
            _log_call(purpose, "groq", response.model_name, latency, True, response.usage)
            return {"text": text or "", "provider": "groq", "model": response.model_name,
                    "latency_ms": latency, "success": True, "usage": response.usage}
        except Exception as e:
            latency = (time.time() - t0) * 1000
            _log_call(purpose, "groq", config.GROQ_MODEL, latency, False,
                      fallback_reason="groq_error", error=str(e))
            logger.warning("Groq synthesis failed (%.0fms): %s", latency, str(e)[:150])
            # bounded fallback below only for COMPLEX synthesis
            if complexity != "complex":
                raise

    # ── 2) NVIDIA bounded fallback (COMPLEX only, max one attempt) ──
    if _nvidia_available() and (complexity == "complex" or not _groq_available()):
        try:
            from src.llm.nvidia_client import NVIDIALLM
            llm = NVIDIALLM()
            timeout = min(int(getattr(config, "LLM_TIMEOUT_SECONDS", 60) or 60), 45)
            # reasoning models spend tokens on a thinking block first
            response = llm.generate(prompt, system=system,
                                    max_tokens=max(max_tokens, 600), timeout=timeout)
            text = _strip_thinking(response.text)
            latency = (time.time() - t0) * 1000
            _log_call(purpose, "nvidia", response.model_name, latency, True, response.usage,
                      fallback_reason="groq_fallback" if _groq_available() else "")
            return {"text": text, "provider": "nvidia", "model": response.model_name,
                    "latency_ms": latency, "success": True, "usage": response.usage}
        except Exception as e:
            latency = (time.time() - t0) * 1000
            _log_call(purpose, "nvidia", config.LLM_MODEL, latency, False,
                      fallback_reason="nvidia_error", error=str(e))
            logger.warning("NVIDIA fallback failed (%.0fms): %s", latency, str(e)[:150])

    # ── 3) Last-resort deterministic fallback (never a 40s hang) ──
    from src.llm.fallback_llm import FallbackLLM
    try:
        response = FallbackLLM().generate(prompt, system=system, max_tokens=max_tokens)
        latency = (time.time() - t0) * 1000
        _log_call(purpose, "fallback", "template-grounded", latency, True)
        return {"text": response.text, "provider": "fallback", "model": "template-grounded",
                "latency_ms": latency, "success": True, "usage": None}
    except Exception as e:
        raise RuntimeError(f"All LLM providers failed: {e}") from e
