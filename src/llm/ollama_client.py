"""
Real open-weight LLM connector via Ollama (assignment Section 3 constraint:
free/open or locally runnable model — Qwen/Llama/Gemma).

Model choice (documented for README "Model name / version / why selected"):
  Model: qwen2.5:7b-instruct (default; configurable via OLLAMA_MODEL)
  Why: strong instruction-following and grounded-answer quality at 7B,
  runs comfortably on a single consumer GPU (8-12GB VRAM) or CPU-only with
  acceptable latency for an internal analyst tool, Apache-2.0-family
  licensing, and good multilingual/number-handling which matters for a
  metrics-heavy assistant. Gemma2:9b or Llama-3.1:8b are documented
  drop-in alternatives (just change OLLAMA_MODEL).
  Hardware: ~5GB disk for the 4-bit quantized weights, ~6-8GB RAM/VRAM to
  run comfortably, CPU inference works but expect 5-20s latency per answer.
  Limitations: 7B-class models can still misread numeric context if the
  prompt is poorly structured, which is why grounding/citation is enforced
  by our prompt template and a post-hoc "did the LLM only use provided
  numbers" pattern, not trusted on faith.

This class is NOT used in the sandbox this was built in (no local Ollama
server available there) — it is provided complete and ready to run
anywhere Ollama is installed. Set LLM_BACKEND=ollama in .env to activate.
"""
import time

import requests

from src import config
from src.llm.base import BaseLLM, LLMResponse


class OllamaLLM(BaseLLM):
    def __init__(self, model: str = None, base_url: str = None):
        self.model = model or config.OLLAMA_MODEL
        self.base_url = base_url or config.OLLAMA_BASE_URL

    def generate(self, prompt: str, system: str = None, max_tokens: int = 700) -> LLMResponse:
        start = time.time()
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system or "",
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.1},
        }
        resp = requests.post(f"{self.base_url}/api/generate", json=payload,
                              timeout=config.LLM_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.time() - start) * 1000
        return LLMResponse(text=data.get("response", "").strip(), model_name=self.model,
                            backend="ollama", latency_ms=latency_ms)

    def generate_stream(self, prompt: str, system: str = None, max_tokens: int = 700):
        """Stream response tokens from Ollama using SSE."""
        import json as _json
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system or "",
            "stream": True,
            "options": {"num_predict": max_tokens, "temperature": 0.1},
        }
        try:
            resp = requests.post(f"{self.base_url}/api/generate", json=payload,
                                  timeout=config.LLM_TIMEOUT_SECONDS, stream=True)
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = _json.loads(line.decode("utf-8", errors="replace"))
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break
                except _json.JSONDecodeError:
                    continue
        except Exception:
            response = self.generate(prompt, system, max_tokens)
            yield response.text
