"""
Full pipeline orchestration (assignment Section 27 "Final Success
Criterion" diagram, implemented literally):

  Question -> Query Understanding (classify) -> route to RAG / SQL / Hybrid
           -> Evidence Fusion (context_builder) -> Grounded LLM (llm/factory)
           -> Answer + Metrics + Source Citations -> (evaluation, separately)
"""
import copy
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from src import config
from src.ingestion.document_loader import load_knowledge_base
from src.llm.factory import get_llm
from src.rag import prompt_templates
from src.rag import query_classifier
from src.rag.context_builder import build_evidence
from src.rag.query_classifier import classify
from src.retrieval.hybrid_retriever import HybridRetriever
from src.retrieval.keyword_search import KeywordIndex
from src.retrieval.vector_store import VectorStore


@dataclass
class QueryResult:
    answer: str
    query_type: str
    sources: List[dict] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)


class _LRUCache:
    """Small bounded LRU cache for repeated/duplicate question answers.

    Why this matters (README "LLM cost control" already flagged this as a
    production must-have): in a real analyst tool, a handful of questions
    ("which product generated the highest revenue?") get asked repeatedly
    by different people. Before this change, every single request re-ran
    classification, retrieval, SQL, *and* generation from scratch even for
    an identical question asked seconds apart. Caching on normalized
    question text turns a repeat question into an O(1) dict lookup.

    Not a cache of raw LLM output only — it caches the full QueryResult,
    since with LLM_BACKEND=ollama, generation (not retrieval) is the
    dominant cost, and skipping it entirely for a repeat question is the
    actual win.
    """

    def __init__(self, max_size: int = 256):
        self.max_size = max_size
        self._store: "OrderedDict[str, QueryResult]" = OrderedDict()

    @staticmethod
    def _key(question: str) -> str:
        return " ".join(question.strip().lower().split())

    def get(self, question: str):
        key = self._key(question)
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, question: str, result: QueryResult):
        key = self._key(question)
        self._store[key] = result
        self._store.move_to_end(key)
        if len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def clear(self):
        self._store.clear()

    def __len__(self):
        return len(self._store)


class RAGPipeline:
    """
    Loaded once at API startup. Holds the vector store, keyword index, and
    retriever in memory; the LLM is instantiated per-call from config (cheap)
    so LLM_BACKEND can even be swapped without a full restart in dev.
    """

    def __init__(self):
        self.vector_store = VectorStore()
        self.keyword_index = KeywordIndex()
        self._load_or_build_indexes()
        self.retriever = HybridRetriever(self.vector_store, self.keyword_index)
        self._cache = _LRUCache(max_size=256)

    def _load_or_build_indexes(self):
        if Path(config.VECTOR_STORE_PATH).exists():
            self.vector_store.load()
        else:
            chunks = load_knowledge_base()
            self.vector_store.build(chunks)
            self.vector_store.save()
        self.keyword_index.build(self.vector_store.chunks)

    def reindex(self):
        """Re-run ingestion for the knowledge base (used after document upload/delete)."""
        chunks = load_knowledge_base()
        self.vector_store.build(chunks)
        self.vector_store.save()
        self.keyword_index.build(chunks)
        # Cached answers may cite knowledge-base chunks that no longer exist
        # (or miss new ones) after a reindex — invalidate rather than serve stale evidence.
        self._cache.clear()
        query_classifier.invalidate_entity_cache()

    def answer(self, question: str) -> QueryResult:
        t0 = time.time()

        cached = self._cache.get(question)
        if cached is not None:
            result = copy.deepcopy(cached)
            result.metrics = dict(result.metrics)
            result.metrics["cache_hit"] = True
            result.metrics["end_to_end_latency_ms"] = round((time.time() - t0) * 1000, 2)
            result.metrics["retrieval_latency_ms"] = 0.0
            result.metrics["generation_latency_ms"] = 0.0
            return result

        classification = classify(question)
        t_classify = time.time()

        evidence = build_evidence(question, classification, self.retriever)
        t_retrieve = time.time()

        prompt = prompt_templates.build_prompt(question, classification.query_type, evidence)
        llm = get_llm()
        llm_response = llm.generate(prompt, system=prompt_templates.SYSTEM_INSTRUCTION)
        t_generate = time.time()

        sources = self._extract_sources(evidence)

        metrics = {
            "query_type": classification.query_type,
            "classification_reason": classification.reason,
            "retrieval_latency_ms": round((t_retrieve - t_classify) * 1000, 1),
            "generation_latency_ms": round((t_generate - t_retrieve) * 1000, 1),
            "end_to_end_latency_ms": round((t_generate - t0) * 1000, 1),
            "llm_backend": llm_response.backend,
            "llm_model": llm_response.model_name,
            "cache_hit": False,
        }

        result = QueryResult(
            answer=llm_response.text,
            query_type=classification.query_type,
            sources=sources,
            evidence=evidence,
            metrics=metrics,
        )
        # Diagnostic/analytical answers are computed from a point-in-time
        # snapshot of the warehouse; caching is safe here because this
        # dataset is static within a run. A production version with a live-
        # updating warehouse would additionally need a short TTL (e.g. 60s)
        # rather than an unbounded cache entry — noted here rather than
        # silently assumed away.
        self._cache.put(question, result)
        return result

    @staticmethod
    def _extract_sources(evidence: dict) -> List[dict]:
        sources = []
        sd = evidence.get("structured_data")
        if sd:
            for key in sd.keys():
                sources.append({"type": "structured_data", "source": key})
        for c in evidence.get("knowledge_base_chunks", []):
            sources.append({"type": "knowledge_base", "source": c["source"]})
        return sources


_pipeline_singleton = None


def get_pipeline() -> RAGPipeline:
    global _pipeline_singleton
    if _pipeline_singleton is None:
        _pipeline_singleton = RAGPipeline()
    return _pipeline_singleton

