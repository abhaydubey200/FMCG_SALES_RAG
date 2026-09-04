"""
Retrieval tests (legacy V1 pipeline primitives).

These exercise the deterministic retrieval primitives shared with the V2
runtime: vector store, keyword index, hybrid retriever, conflict detection
(unit-tested with synthetic chunks — the certified KB corpus no longer
contains the V1-era "Marketing Strategy" doc name), and the LRU answer-cache
contract (normalized keys + reindex invalidation).

LLM-dependent assertions were removed: exact wording of an LLM answer and
live rate-limit availability are not deterministic test inputs. The V2
orchestrator's grounded/unanswerable behavior is covered by the e2e suite
(tests/e2e/test_revenue_ground_truth.py, tests/e2e/test_workspace_isolation.py).
"""
from src.rag.pipeline import get_pipeline, QueryResult


def test_vector_store_returns_relevant_chunk_for_discount_query():
    pipeline = get_pipeline()
    results = pipeline.vector_store.search("What discount is recommended for campaigns?", top_k=5)
    assert len(results) > 0
    # Verify results have meaningful scores
    scores = [r.score for r in results]
    assert any(s > 0 for s in scores)


def test_keyword_index_returns_exact_term_match():
    pipeline = get_pipeline()
    results = pipeline.keyword_index.search("trade promotion limit", top_k=5)
    assert len(results) > 0


def test_hybrid_retriever_returns_ranked_results():
    pipeline = get_pipeline()
    results = pipeline.retriever.retrieve("What is the recommended strategy for high-value customers?")
    assert len(results) > 0
    scores = [r.rerank_score for r in results]
    assert scores == sorted(scores, reverse=True)


def _chunk(doc_name, text):
    """Build a RetrievedChunk-shaped object for a synthetic document chunk."""
    from src.retrieval.hybrid_retriever import RetrievedChunk

    class _Chunk:
        def __init__(self):
            self.document_name = doc_name
            self.text = text

    rc = RetrievedChunk.__new__(RetrievedChunk)
    rc.chunk = _Chunk()
    rc.vector_score = 1.0
    rc.keyword_score = 1.0
    rc.fused_score = 1.0
    rc.rerank_score = 1.0
    return rc


def test_conflict_detection_surfaces_both_documents():
    """The discount conflict detector must report both documents when a
    recommended campaign discount and a pricing ceiling are both retrieved.
    Unit-tested with synthetic chunks because the certified KB corpus does not
    contain the V1-era 'Marketing Strategy' document name."""
    from src.rag.context_builder import _detect_discount_conflict
    chunks = [
        _chunk("Marketing Strategy", "Recommended default campaign discount target is 10%."),
        _chunk("Pricing Policy", "Maximum allowable off-invoice discount is 15%."),
    ]
    conflict = _detect_discount_conflict(chunks)
    assert conflict is not None
    assert conflict["conflict"] is True
    assert 10 in conflict["marketing_strategy_values"]
    assert 15 in conflict["pricing_policy_values"]


def test_conflict_detector_silent_when_single_document_retrieved():
    from src.rag.context_builder import _detect_discount_conflict
    chunks = [_chunk("Pricing Policy", "Maximum allowable off-invoice discount is 15%.")]
    assert _detect_discount_conflict(chunks) is None


def test_unanswerable_question_is_classified_not_analytical():
    """2030 predictions are classified unanswerable (deterministic) — the
    V2 refusal behavior (no fabricated answer) is covered end-to-end by the
    e2e unsupported-question checks."""
    from src.rag.query_classifier import classify
    result = classify("What will Amazon's sales be in 2030?")
    assert result.query_type == "unanswerable"


def test_repeated_question_is_served_from_cache():
    pipeline = get_pipeline()
    pipeline._cache.clear()
    q = "Which campaign had the highest ROAS?"
    result = QueryResult(answer="stub", query_type="analytical", metrics={})
    pipeline._cache.put(q, result)
    assert pipeline._cache.get(q) is result


def test_cache_key_is_normalized_for_whitespace_and_case():
    pipeline = get_pipeline()
    pipeline._cache.clear()
    result = QueryResult(answer="stub", query_type="analytical", metrics={})
    pipeline._cache.put("Which campaign had the highest ROAS?", result)
    second = pipeline._cache.get("  which campaign   had the highest roas?  ")
    assert second is result


def test_reindex_clears_the_answer_cache():
    pipeline = get_pipeline()
    pipeline._cache.clear()
    result = QueryResult(answer="stub", query_type="analytical", metrics={})
    pipeline._cache.put("Which campaign had the highest ROAS?", result)
    assert len(pipeline._cache) > 0
    pipeline.reindex()
    assert len(pipeline._cache) == 0
