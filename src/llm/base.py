"""
LLM abstraction. Every backend implements `generate(prompt, system=None) -> str`
and optionally `generate_stream(prompt, system=None) -> Iterator[str]`
so the RAG pipeline never needs to know which backend is active.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Optional


@dataclass
class LLMResponse:
    text: str
    model_name: str
    backend: str
    latency_ms: float
    usage: Optional[dict] = None


class BaseLLM(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: str = None, max_tokens: int = 700,
                 timeout: Optional[float] = None) -> LLMResponse:
        ...

    def generate_stream(self, prompt: str, system: str = None, max_tokens: int = 700) -> Iterator[str]:
        """Optional streaming interface. Yields text chunks.
        Default implementation falls back to non-streaming generate().
        """
        response = self.generate(prompt, system, max_tokens)
        # Yield the full response as a single chunk for backends that don't support streaming
        yield response.text
