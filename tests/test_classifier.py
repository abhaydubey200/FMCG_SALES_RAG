from src.rag.query_classifier import classify


def test_analytical_question_classified_correctly():
    result = classify("Which product generated the highest revenue?")
    assert result.query_type == "analytical"


def test_knowledge_question_classified_correctly():
    result = classify("What is the recommended strategy for high-value customers?")
    assert result.query_type == "knowledge"


def test_hybrid_question_classified_correctly():
    result = classify(
        "Which products generated the highest revenue, and what marketing strategy "
        "does the company recommend for those products?"
    )
    assert result.query_type == "hybrid"


def test_diagnostic_question_classified_correctly():
    result = classify("Aurora Pro Wireless Earbuds sales declined in Q2. What are the likely reasons?")
    assert result.query_type == "diagnostic"
    assert result.resolved_product is not None
    assert result.resolved_product["product_id"] == "P0001"


def test_future_question_is_unanswerable():
    result = classify("What will Amazon's sales be in 2030?")
    assert result.query_type == "unanswerable"


def test_competitor_question_is_unanswerable():
    result = classify("What is our main competitor's pricing strategy?")
    assert result.query_type == "unanswerable"


def test_vague_decline_question_is_ambiguous():
    result = classify("Why did sales decline?")
    assert result.query_type == "ambiguous"


def test_category_resolution_electronics_not_falsely_flagged_analytical_by_ctr_substring():
    """Regression test: 'Electronics' contains the substring 'ctr' (elec-CTR-onics).
    A naive substring keyword match previously misfired on this. See
    query_classifier._keyword_hit docstring."""
    result = classify("How should Electronics products be positioned?")
    assert result.query_type == "knowledge"
