import logging

from src import config
from src.llm.base import BaseLLM

logger = logging.getLogger("llm_factory")


def get_llm() -> BaseLLM:
    backend = config.LLM_BACKEND

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
