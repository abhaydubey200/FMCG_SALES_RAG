"""
Hybrid retrieval pipeline (assignment Section 8 "Preferred" architecture):

    Query -> Query Processing -> [Vector Search, Keyword Search]
          -> Candidate Pool -> Reranking -> Top Relevant Context

Why hybrid over vector-only (documented for README "Retrieval strategy"):
Our knowledge base is small (~20 policy documents) but dense with specific
numbers, thresholds, and named entities (15%, ROAS 3.0x, "Aurora Pro
Wireless Earbuds"). Vector search (even neural) is good at *topical*
similarity but can under-rank a chunk that contains the exact number/entity
asked about if its surrounding language differs from the query. BM25
keyword search is complementary: it excels at exact-term precision. Fusing
both and reranking gives better recall+precision than either alone, at
near-zero extra latency for a corpus this size.

Reranking: a real cross-encoder reranker (e.g. bge-reranker) needs a
downloaded model, unavailable in this sandbox. We implement a lightweight,
transparent reranker instead: score = fused_retrieval_score + a
term-overlap boost between the query and chunk text. This is documented as
a stand-in — the interface (`rerank(query, candidates)`) is exactly where
a cross-encoder call would be dropped in.
"""
import re
from dataclasses import dataclass
from typing import List

from src import config
from src.ingestion.document_loader import Chunk
from src.retrieval.keyword_search import KeywordIndex
from src.retrieval.vector_store import VectorStore


@dataclass
class RetrievedChunk:
    chunk: Chunk
    vector_score: float
    keyword_score: float
    fused_score: float
    rerank_score: float


def _normalize(scores: dict) -> dict:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


class HybridRetriever:
    def __init__(self, vector_store: VectorStore, keyword_index: KeywordIndex):
        self.vector_store = vector_store
        self.keyword_index = keyword_index

    def retrieve(self, query: str, top_k: int = None, filters: dict = None) -> List[RetrievedChunk]:
        top_k = top_k or config.TOP_K_FINAL

        vector_hits = self.vector_store.search(query, top_k=config.TOP_K_VECTOR)
        keyword_hits = self.keyword_index.search(query, top_k=config.TOP_K_KEYWORD)

        vec_scores = {vh.chunk.chunk_id: vh.score for vh in vector_hits}
        kw_scores = {kh.chunk.chunk_id: kh.score for kh in keyword_hits}
        vec_scores_n = _normalize(vec_scores)
        kw_scores_n = _normalize(kw_scores)

        chunks_by_id = {c.chunk.chunk_id: c.chunk for c in vector_hits}
        chunks_by_id.update({c.chunk.chunk_id: c.chunk for c in keyword_hits})

        # Metadata filtering (Section 24 bonus): e.g. {"document_type": "policy"}
        if filters:
            chunks_by_id = {
                cid: c for cid, c in chunks_by_id.items()
                if all(getattr(c, k, None) == v for k, v in filters.items())
            }

        candidates = []
        for cid, chunk in chunks_by_id.items():
            v = vec_scores_n.get(cid, 0.0)
            k = kw_scores_n.get(cid, 0.0)
            fused = config.VECTOR_WEIGHT * v + config.KEYWORD_WEIGHT * k
            candidates.append(RetrievedChunk(chunk=chunk, vector_score=v, keyword_score=k,
                                              fused_score=fused, rerank_score=fused))

        reranked = self._rerank(query, candidates)
        reranked = [c for c in reranked if c.rerank_score >= config.MIN_RELEVANCE_SCORE]
        reranked.sort(key=lambda c: -c.rerank_score)
        return reranked[:top_k]

    def _rerank(self, query: str, candidates: List[RetrievedChunk]) -> List[RetrievedChunk]:
        """Lightweight lexical-overlap reranker (documented cross-encoder stand-in)."""
        q_terms = set(re.findall(r"[a-z0-9%]+", query.lower()))
        for c in candidates:
            c_terms = set(re.findall(r"[a-z0-9%]+", c.chunk.text.lower()))
            overlap = len(q_terms & c_terms) / (len(q_terms) + 1e-9)
            c.rerank_score = 0.75 * c.fused_score + 0.25 * overlap
        return candidates
