"""
NVIDIA LLM adapter via NVIDIA AI Foundation Endpoints (OpenAI-compatible API).

Model: nvidia/nemotron-3.5-lightning-30b-a3b (default; configurable via LLM_MODEL)
Base URL: https://integrate.api.nvidia.com/v1

The NVIDIA API uses the OpenAI chat completions format, so this adapter
sends a standard /v1/chat/completions request with the NVIDIA API key
as a Bearer token.
"""
import json
import time
from typing import Iterator

import requests

from src import config
from src.llm.base import BaseLLM, LLMResponse


class NVIDIALLM(BaseLLM):
    def __init__(self, model: str = None, base_url: str = None, api_key: str = None):
        self.model = model or config.LLM_MODEL
        self.base_url = (base_url or config.LLM_BASE_URL).rstrip("/")
        self.api_key = api_key or config.LLM_API_KEY

    def _build_messages(self, prompt: str, system: str = None) -> list:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def generate(self, prompt: str, system: str = None, max_tokens: int = 2048) -> LLMResponse:
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
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload, headers=headers,
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.time() - start) * 1000
        text = data["choices"][0]["message"]["content"].strip()
        model_used = data.get("model", self.model)
        return LLMResponse(text=text, model_name=model_used,
                            backend="nvidia", latency_ms=latency_ms)

    def generate_stream(self, prompt: str, system: str = None, max_tokens: int = 2048) -> Iterator[str]:
        """Stream response tokens from NVIDIA API using SSE."""
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
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload, headers=headers,
                timeout=config.LLM_TIMEOUT_SECONDS,
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
            response = self.generate(prompt, system, max_tokens)
            yield response.text
