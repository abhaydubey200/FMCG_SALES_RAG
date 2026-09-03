import logging

from src import config
from src.llm.base import BaseLLM

logger = logging.getLogger("llm_factory")


def get_llm() -> BaseLLM:
    backend = config.LLM_BACKEND

    # Groq: ultra-fast LPU inference (~100-500ms vs 30-50s on GPU)
    if backend == "groq" and config.GROQ_API_KEY:
        try:
            from src.llm.groq_client import GroqLLM
            llm = GroqLLM()
            logger.info("LLM provider: Groq (%s)", config.GROQ_MODEL)
            return llm
        except Exception as e:
            logger.warning("Groq provider init failed (%s), falling back", e)

    if backend == "nvidia" and config.LLM_API_KEY:
        try:
            from src.llm.nvidia_client import NVIDIALLM
            llm = NVIDIALLM()
            logger.info("LLM provider: NVIDIA (%s)", config.LLM_MODEL)
            return llm
        except Exception as e:
            logger.warning("NVIDIA provider init failed (%s), falling back", e)

    if backend == "ollama":
        try:
            from src.llm.ollama_client import OllamaLLM
            llm = OllamaLLM()
            logger.info("LLM provider: Ollama (%s)", config.OLLAMA_MODEL)
            return llm
        except Exception as e:
            logger.warning("Ollama provider init failed (%s), falling back", e)

    logger.info("LLM provider: fallback (template-grounded)")
    from src.llm.fallback_llm import FallbackLLM
    return FallbackLLM()
