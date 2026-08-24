"""
NVIDIA LLM adapter via NVIDIA AI Foundation Endpoints (OpenAI-compatible API).

Model: nvidia/nemotron-3.5-lightning-30b-a3b (default; configurable via LLM_MODEL)
Base URL: https://integrate.api.nvidia.com/v1

The NVIDIA API uses the OpenAI chat completions format, so this adapter
sends a standard /v1/chat/completions request with the NVIDIA API key
as a Bearer token.
"""
import time

import requests

from src import config
from src.llm.base import BaseLLM, LLMResponse


class NVIDIALLM(BaseLLM):
    def __init__(self, model: str = None, base_url: str = None, api_key: str = None):
        self.model = model or config.LLM_MODEL
        self.base_url = (base_url or config.LLM_BASE_URL).rstrip("/")
        self.api_key = api_key or config.LLM_API_KEY

    def generate(self, prompt: str, system: str = None, max_tokens: int = 2048) -> LLMResponse:
        start = time.time()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
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
            json=payload,
            headers=headers,
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.time() - start) * 1000

        text = data["choices"][0]["message"]["content"].strip()
        model_used = data.get("model", self.model)

        return LLMResponse(
            text=text,
            model_name=model_used,
            backend="nvidia",
            latency_ms=latency_ms,
        )
