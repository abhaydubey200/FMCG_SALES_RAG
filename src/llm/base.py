"""
LLM abstraction. Every backend implements `generate(prompt, system=None) -> str`
so the RAG pipeline never needs to know which backend is active.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    model_name: str
    backend: str
    latency_ms: float


class BaseLLM(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: str = None, max_tokens: int = 700) -> LLMResponse:
        ...
