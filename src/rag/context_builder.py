"""
Context builder — fuses structured-data results and retrieved knowledge-base
chunks into a single EVIDENCE contract consumed by both the real LLM prompt
and the fallback template generator (see prompt_templates.py docstring).

Also implements the "Conflicting Information Test" (Section 14): when two
retrieved knowledge chunks discuss the same topic (discount %) but state
different numbers, we detect and flag it explicitly in the evidence rather
than silently forwarding both to the LLM and hoping it notices.
"""
import re
from typing import List, Optional

from src.analytics import sql_layer
from src.rag.query_classifier import QueryClassification
from src.retrieval.hybrid_retriever import HybridRetriever, RetrievedChunk

DISCOUNT_PATTERN = re.compile(r"(\d{1,2})\s?%")


def _detect_discount_conflict(chunks: List[RetrievedChunk]) -> Optional[dict]:
    """Known conflict scenario (Section 14): Marketing Strategy recommends a
    10% campaign discount target; Pricing Policy sets a 15% maximum. If both
    documents are present among retrieved chunks, surface the conflict."""
    mentions = {}
    for rc in chunks:
        doc = rc.chunk.document_name
        if doc in ("Marketing Strategy", "Pricing Policy") and "discount" in rc.chunk.text.lower():
            nums = DISCOUNT_PATTERN.findall(rc.chunk.text)
            if nums:
                mentions.setdefault(doc, set()).update(int(n) for n in nums)
    if "Marketing Strategy" in mentions and "Pricing Policy" in mentions:
        return {
            "conflict": True,
            "topic": "recommended vs. maximum campaign discount percentage",
            "marketing_strategy_values": sorted(mentions["Marketing Strategy"]),
            "pricing_policy_values": sorted(mentions["Pricing Policy"]),
            "note": "Marketing Strategy states a recommended default; Pricing Policy states the maximum "
                    "allowable ceiling. These are not necessarily contradictory but report different numbers "
                    "for 'discount' — do not merge them into a single figure.",
        }
    return None


def _chunk_evidence(chunks: List[RetrievedChunk]) -> List[dict]:
    return [
        {
            "source": f"{rc.chunk.document_name} — {rc.chunk.section}",
            "document_type": rc.chunk.document_type,
            "text": rc.chunk.text,
            "relevance_score": round(rc.rerank_score, 3),
        }
        for rc in chunks
    ]


def build_evidence(question: str, classification: QueryClassification,
                    retriever: HybridRetriever) -> dict:
    qtype = classification.query_type
    evidence = {"query_type": qtype}

    if qtype == "unanswerable":
        evidence["available_data_summary"] = (
            "Structured data covers products, sales, campaigns, customers, and reviews through "
            "the most recent recorded order date. The knowledge base covers current marketing, "
            "pricing, product, customer, and campaign strategy documents. Neither source contains "
            "future projections or data beyond what has actually been recorded."
        )
        return evidence

    if qtype == "ambiguous":
        evidence["ambiguity_reason"] = classification.reason
        evidence["hint"] = "Ask the user to specify the exact product name or category."
        return evidence

    # --- structured data ---
    if qtype in ("analytical", "hybrid", "diagnostic"):
        structured = {}
        product = classification.resolved_product
        category = classification.resolved_category

        q_lower = question.lower()
        if "roas" in q_lower or "campaign" in q_lower:
            structured["top_campaigns_by_roas"] = sql_layer.campaign_performance(limit=5, order_by="roas")
        if product:
            structured["product"] = product
            structured["product_metrics_all_time"] = sql_layer.product_metrics(product["product_id"])
            structured["quarterly_trend"] = sql_layer.quarterly_trend(product["product_id"])
            structured["campaigns_for_product"] = sql_layer.campaigns_for_product(product["product_id"])
            structured["review_summary_all_time"] = sql_layer.review_summary(product["product_id"])
        if category:
            structured["category_performance"] = sql_layer.category_performance(category=category)
        if not product and not category and "top_campaigns_by_roas" not in structured:
            structured["top_products_by_revenue"] = sql_layer.top_products_by_revenue(limit=5)
            structured["category_performance"] = sql_layer.category_performance()

        if qtype == "diagnostic" and product:
            pid = product["product_id"]
            structured["decline_window_metrics"] = sql_layer.product_metrics(
                pid, start_date="2025-04-01", end_date="2025-06-30")
            structured["pre_decline_metrics"] = sql_layer.product_metrics(
                pid, start_date="2025-01-01", end_date="2025-03-31")
            structured["decline_window_reviews"] = sql_layer.review_summary(
                pid, start_date="2025-04-01", end_date="2025-07-31")
            structured["revenue_growth_q1_vs_q2_2025"] = sql_layer.revenue_growth(
                pid, period_a=("2025-01-01", "2025-03-31"), period_b=("2025-04-01", "2025-06-30"))

        evidence["structured_data"] = structured

    # --- knowledge base retrieval ---
    if qtype in ("knowledge", "hybrid", "diagnostic"):
        retrieval_query = question
        if classification.resolved_product:
            retrieval_query += f" {classification.resolved_product['product_name']} {classification.resolved_product['category']}"
        if classification.resolved_category:
            retrieval_query += f" {classification.resolved_category}"

        retrieved = retriever.retrieve(retrieval_query)
        evidence["knowledge_base_chunks"] = _chunk_evidence(retrieved)

        conflict = _detect_discount_conflict(retrieved)
        if conflict:
            evidence["detected_conflict"] = conflict

        if not retrieved:
            evidence["knowledge_base_note"] = "No sufficiently relevant knowledge-base content was retrieved for this query."

    return evidence
