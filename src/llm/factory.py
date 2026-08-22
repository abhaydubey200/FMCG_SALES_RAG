from src import config
from src.llm.base import BaseLLM


def get_llm() -> BaseLLM:
    if config.LLM_BACKEND == "ollama":
        from src.llm.ollama_client import OllamaLLM
        return OllamaLLM()
    from src.llm.fallback_llm import FallbackLLM
    return FallbackLLM()
