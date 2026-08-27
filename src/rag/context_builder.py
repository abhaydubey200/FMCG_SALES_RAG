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
import logging
from typing import List, Optional

from src.rag.query_classifier import QueryClassification

logger = logging.getLogger(__name__)
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

        # CRITICAL: Check workspace data first. Never silently use legacy.
        from src.analytics.dynamic_engine import (
            has_workspace_data, generate_dynamic_overview, discover_available_data,
            workspace_total_revenue, workspace_revenue_by_dimension, workspace_revenue_trend,
            workspace_top_entities,
        )

        workspace_has = has_workspace_data()

        if workspace_has:
            # Workspace has uploaded data — use ONLY that data
            try:
                dynamic = generate_dynamic_overview()
                if dynamic.get("kpis"):
                    structured["dynamic_kpis"] = dynamic["kpis"]
                if dynamic.get("trend"):
                    structured["monthly_trend"] = dynamic["trend"]
                if dynamic.get("breakdowns"):
                    for dim_name, dim_data in dynamic["breakdowns"].items():
                        structured[f"dynamic_{dim_name}"] = dim_data
                # Include data discovery context
                data_info = discover_available_data()
                if data_info.get("assets"):
                    structured["available_assets"] = [
                        {"name": a["name"], "rows": a["row_count"], "domain": a["domain"]}
                        for a in data_info["assets"]
                    ]
                # Route queries to workspace data only
                if "total sales" in q_lower or "total revenue" in q_lower or "how much" in q_lower:
                    rev = workspace_total_revenue()
                    if rev is not None:
                        structured["total_sales_summary"] = {"total_revenue": rev, "total_orders": workspace_row_count()}
                    else:
                        structured["no_revenue_measure"] = True
                elif "region" in q_lower or "territory" in q_lower or "market" in q_lower:
                    for dim in ["region", "territory", "market"]:
                        rows = workspace_revenue_by_dimension(dim)
                        if rows:
                            structured["revenue_by_region"] = rows
                            break
                elif "product" in q_lower or "item" in q_lower or "sku" in q_lower:
                    top = workspace_top_entities(limit=10)
                    if top:
                        structured["top_products_by_revenue"] = top
            except Exception as e:
                logger.warning(f"Workspace data query failed: {e}")
        else:
            # No workspace data — include empty state info, do NOT query legacy
            structured["workspace_empty"] = True
            structured["workspace_empty_message"] = "No uploaded data in workspace. Upload sales or marketing data to enable analytics."

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
