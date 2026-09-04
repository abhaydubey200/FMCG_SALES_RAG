"""
Groq LLM adapter — ultra-low-latency inference via Groq's LPU API.

Groq uses an OpenAI-compatible /v1/chat/completions endpoint but runs on
custom LPU hardware, delivering responses in ~100-500ms vs 30-50s on
standard GPU APIs. This is the primary latency optimization for the
orchestrator's LLM calls (intent classification, synthesis).

Model choice (configurable via GROQ_MODEL):
  - llama-3.3-70b-versatile: best quality, ~200-400ms
  - llama-3.1-8b-instant: fastest, ~50-150ms
  - mixtral-8x7b-32768: good middle ground

Set LLM_BACKEND=groq in .env to activate.
"""
import json
import time
from typing import Iterator

import requests

from src import config
from src.llm.base import BaseLLM, LLMResponse


class GroqLLM(BaseLLM):
    def __init__(self, model: str = None, base_url: str = None, api_key: str = None):
        self.model = model or getattr(config, "GROQ_MODEL", "llama-3.3-70b-versatile")
        self.base_url = (base_url or getattr(config, "GROQ_BASE_URL", "https://api.groq.com/openai/v1")).rstrip("/")
        self.api_key = api_key or getattr(config, "GROQ_API_KEY", "")

    def _build_messages(self, prompt: str, system: str = None) -> list:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def generate(self, prompt: str, system: str = None, max_tokens: int = 2048,
                 timeout: float = None) -> LLMResponse:
        start = time.time()
        payload = {
            "model": self.model,
            "messages": self._build_messages(prompt, system),
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "top_p": 0.9,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # Groq is fast — short bounded timeout
        if timeout is None:
            timeout = min(getattr(config, "LLM_TIMEOUT_SECONDS", 30), 30)
        timeout = min(float(timeout), 30)
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload, headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.time() - start) * 1000
        text = data["choices"][0]["message"]["content"].strip()
        model_used = data.get("model", self.model)
        usage = data.get("usage")
        return LLMResponse(text=text, model_name=model_used,
                            backend="groq", latency_ms=latency_ms, usage=usage)

    def generate_stream(self, prompt: str, system: str = None, max_tokens: int = 2048,
                        timeout: float = None) -> Iterator[str]:
        """Stream response tokens from Groq using SSE."""
        payload = {
            "model": self.model,
            "messages": self._build_messages(prompt, system),
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "top_p": 0.9,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if timeout is None:
            timeout = min(getattr(config, "LLM_TIMEOUT_SECONDS", 30), 30)
        timeout = min(float(timeout), 30)
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload, headers=headers,
                timeout=timeout,
                stream=True,
            )
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8", errors="replace")
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
        except Exception:
            # Fall back to non-streaming on error
            response = self.generate(prompt, system, max_tokens, timeout=timeout)
            yield response.text
