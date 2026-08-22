from src.rag.pipeline import get_pipeline


def test_vector_store_returns_relevant_chunk_for_discount_query():
    pipeline = get_pipeline()
    results = pipeline.vector_store.search("What discount is recommended for campaigns?", top_k=5)
    assert len(results) > 0
    doc_names = [r.chunk.document_name for r in results]
    assert "Marketing Strategy" in doc_names or "Pricing Policy" in doc_names


def test_keyword_index_returns_exact_term_match():
    pipeline = get_pipeline()
    results = pipeline.keyword_index.search("ROAS minimum 3.0x", top_k=5)
    assert len(results) > 0


def test_hybrid_retriever_returns_ranked_results():
    pipeline = get_pipeline()
    results = pipeline.retriever.retrieve("What is the recommended strategy for high-value customers?")
    assert len(results) > 0
    scores = [r.rerank_score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_conflict_detection_surfaces_both_documents():
    from src.rag.context_builder import _detect_discount_conflict
    pipeline = get_pipeline()
    chunks = pipeline.retriever.retrieve("What discount is recommended for campaigns?", top_k=8)
    conflict = _detect_discount_conflict(chunks)
    assert conflict is not None
    assert conflict["conflict"] is True


def test_end_to_end_pipeline_returns_grounded_answer():
    pipeline = get_pipeline()
    result = pipeline.answer("Which campaign had the highest ROAS?")
    assert result.query_type == "analytical"
    assert len(result.answer) > 0
    assert len(result.sources) > 0


def test_unanswerable_question_does_not_fabricate():
    pipeline = get_pipeline()
    result = pipeline.answer("What will Amazon's sales be in 2030?")
    assert result.query_type == "unanswerable"
    assert "does not contain sufficient information" in result.answer.lower()


def test_repeated_question_is_served_from_cache():
    pipeline = get_pipeline()
    pipeline._cache.clear()
    q = "Which campaign had the highest ROAS?"

    first = pipeline.answer(q)
    assert first.metrics["cache_hit"] is False

    second = pipeline.answer(q)
    assert second.metrics["cache_hit"] is True
    assert second.answer == first.answer
    assert second.query_type == first.query_type


def test_cache_key_is_normalized_for_whitespace_and_case():
    pipeline = get_pipeline()
    pipeline._cache.clear()
    pipeline.answer("Which campaign had the highest ROAS?")
    second = pipeline.answer("  which campaign   had the highest roas?  ")
    assert second.metrics["cache_hit"] is True


def test_reindex_clears_the_answer_cache():
    pipeline = get_pipeline()
    pipeline.answer("Which campaign had the highest ROAS?")
    assert len(pipeline._cache) > 0
    pipeline.reindex()
    assert len(pipeline._cache) == 0
