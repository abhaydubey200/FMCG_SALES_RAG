"""
Query / intent classifier (assignment Section 11 "RAG + Analytics
Integration" — the core evaluation area).

Why rule-based rather than an LLM call (documented for README "Query
routing"): routing decides *which systems even get invoked* (SQL vs
vector search vs both), so it sits upstream of both the analytics layer
and the RAG layer. Using the (potentially unavailable/slow/hallucination-
prone) LLM to make this decision would make the whole pipeline's
reliability depend on the weakest link before we've even retrieved
grounding evidence. A transparent, testable rule-based classifier
(keyword + entity signals) is faster, has zero hallucination risk, and is
easy to unit test exhaustively — which matters because misrouting is the
single biggest way this system could fail silently. In production this
could be upgraded to a small fine-tuned classifier or a constrained LLM
call *with the rule-based version kept as a fallback/sanity check*, not
replaced.

Categories (Section 9):
  A. knowledge     -> RAG only
  B. analytical    -> SQL / analytics layer only
  C. hybrid        -> SQL + RAG, fused
  D. diagnostic    -> SQL (multiple signals) + RAG (policy context), a
                       specialized hybrid subtype requiring multi-source
                       evidence assembly (Section 9D)
  (+) unanswerable  -> flagged when the question asks about data/time
                       periods the system has no way to have (Section 13)
  (+) ambiguous     -> flagged when required entities can't be resolved
                       confidently (Section 15 "3 Ambiguous Questions")
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from src.analytics import sql_layer

ANALYTICAL_KEYWORDS = [
    "revenue", "sales", "units sold", "roas", "ctr", "cpc", "cpa", "conversion rate",
    "conversions", "gross margin", "gross profit", "growth", "average order value", "aov",
    "lifetime value", "ltv", "repeat purchase", "acquisition cost", "cac",
    "highest", "lowest", "top", "best", "best-selling", "best selling", "most revenue",
    "how much", "how many", "total spend", "total sales", "total revenue",
    "spend to revenue", "spend", "budget",
    "impressions", "clicks", "average discount", "average rating",
    "region", "segment", "trend", "monthly", "discount", "margin",
    "performed", "performance", "which",
]
KNOWLEDGE_KEYWORDS = [
    "strategy", "policy", "guideline", "recommend", "recommended", "should we",
    "should receive", "should increase", "should decrease", "budget allocation",
    "objective", "target segment", "position", "lifecycle", "priorit",
    "approach", "guidance", "rule", "requirement", "principle", "expectation",
]
DIAGNOSTIC_PATTERNS = [
    r"why did .* decline", r"why (is|are|did|has|have) .* (drop|fall|decreas|decline)",
    r"what.*reasons? for", r"what.*(caused|driving).*decline", r"declined", r"dropped",
    r"underperform", r"went down", r"decreas(e|ed|ing)",
]
# Precompiled once at import time rather than re.search(p, text) compiling every
# pattern fresh on every single classify() call.
_DIAGNOSTIC_PATTERNS_COMPILED = [re.compile(p) for p in DIAGNOSTIC_PATTERNS]
FUTURE_KEYWORDS = [
    "2027", "2028", "2029", "2030", "2035", "2040", "2050",
    "next year", "next quarter", "will be", "will amazon",
    "predict", "forecast", "projection", "going to be", "future sales",
]
# Entities this system has no data source for at all (Section 13 hallucination
# test extends naturally to "unavailable", not just "future" — e.g. we have no
# competitor table or document, so a competitor question is unanswerable even
# though it's phrased in the present tense).
NO_DATA_SOURCE_KEYWORDS = ["competitor", "competitors", "ceo", "board of directors", "leadership team"]

CATEGORY_NAMES = ["electronics", "home & kitchen", "home and kitchen", "fashion", "beauty",
                   "sports & outdoors", "sports and outdoors", "toys & games", "toys and games",
                   "books", "grocery"]


def _keyword_hit(keywords: list, text: str) -> bool:
    """
    Word-boundary keyword match. A naive `kw in text` substring check causes
    real false positives here — e.g. the acronym keyword "ctr" is a substring
    of the word "ele-CTR-onics", so a plain `in` check would flag any question
    mentioning the Electronics category as an analytical/CTR question. \b
    word-boundary regex avoids matching inside unrelated words while still
    matching multi-word phrase keywords normally (spaces are boundaries too).

    Optimization: compiled once per keyword list and cached, instead of
    calling re.search() (which internally compiles+caches per-pattern
    anyway, but still costs N separate regex engine invocations) once per
    keyword on every single classify() call — a single alternation pattern
    is one engine invocation instead of ~15-30.
    """
    pattern = _compiled_keyword_pattern(id(keywords), keywords)
    return pattern.search(text) is not None


_compiled_keyword_cache = {}


def _compiled_keyword_pattern(cache_key, keywords: list) -> "re.Pattern":
    pattern = _compiled_keyword_cache.get(cache_key)
    if pattern is None:
        alternation = "|".join(re.escape(kw) for kw in keywords)
        pattern = re.compile(r"\b(?:" + alternation + r")")
        _compiled_keyword_cache[cache_key] = pattern
    return pattern


@dataclass
class QueryClassification:
    query_type: str  # "knowledge" | "analytical" | "hybrid" | "diagnostic" | "unanswerable" | "ambiguous"
    reason: str
    resolved_product: Optional[dict] = None
    resolved_category: Optional[str] = None
    signals: dict = field(default_factory=dict)


# --- In-memory entity cache (optimization) ---
# Profiling showed _resolve_product re-querying and re-lowercasing the
# full 120-row products table on every single classify() call (product
# names/categories change only when the dataset is regenerated, not per
# request), adding real overhead to every query including ones that never
# resolve a product at all. Cache once, lazily, at module import/first use;
# call invalidate_entity_cache() after regenerating the dataset.
_entity_cache = {"products": None, "categories": None}


def invalidate_entity_cache():
    _entity_cache["products"] = None
    _entity_cache["categories"] = None


def _cached_products() -> list:
    if _entity_cache["products"] is None:
        with sql_layer.get_conn() as conn:
            rows = [dict(r) for r in conn.execute("SELECT product_id, product_name FROM products")]
        for r in rows:
            r["_name_lower"] = r["product_name"].lower()
            r["_name_words"] = [w for w in r["_name_lower"].split() if len(w) > 3]
        _entity_cache["products"] = rows
    return _entity_cache["products"]


def _cached_categories() -> list:
    if _entity_cache["categories"] is None:
        _entity_cache["categories"] = sql_layer.list_categories()
    return _entity_cache["categories"]


def _resolve_product(query: str) -> Optional[dict]:
    rows = _cached_products()
    q_lower = query.lower()
    matches = [r for r in rows if r["_name_lower"] in q_lower]
    if len(matches) == 1:
        return sql_layer.get_product(matches[0]["product_id"])
    if len(matches) > 1:
        return None  # ambiguous — more than one product name found in query
    # fuzzy: try partial word overlap for named products (2+ significant words)
    for r in rows:
        if r["_name_words"] and all(w in q_lower for w in r["_name_words"]):
            return sql_layer.get_product(r["product_id"])
    return None


def _resolve_category(query: str) -> Optional[str]:
    q_lower = query.lower()
    for cat in _cached_categories():
        if cat.lower() in q_lower or cat.lower().replace(" & ", " and ") in q_lower:
            return cat
    return None


def classify(query: str) -> QueryClassification:
    q_lower = query.lower()

    # --- Unanswerable: future predictions the data cannot support ---
    if any(kw in q_lower for kw in FUTURE_KEYWORDS):
        return QueryClassification(
            query_type="unanswerable",
            reason="Query asks about a future time period or prediction not derivable from the available "
                   "dataset or knowledge base.",
        )

    # --- Unanswerable: entities with no corresponding data source at all ---
    if any(kw in q_lower for kw in NO_DATA_SOURCE_KEYWORDS):
        return QueryClassification(
            query_type="unanswerable",
            reason="Query references an entity (e.g. competitors, executives) that has no corresponding "
                   "table in the structured dataset or document in the knowledge base.",
        )

    product = _resolve_product(query)
    category = _resolve_category(query)

    is_diagnostic = any(p.search(q_lower) for p in _DIAGNOSTIC_PATTERNS_COMPILED)
    is_analytical = _keyword_hit(ANALYTICAL_KEYWORDS, q_lower)
    is_knowledge = _keyword_hit(KNOWLEDGE_KEYWORDS, q_lower)

    if is_diagnostic:
        if not product and not category:
            return QueryClassification(
                query_type="ambiguous",
                reason="Diagnostic question detected but no specific product or category could be resolved "
                       "from the query — need a named product/category to investigate.",
            )
        return QueryClassification(
            query_type="diagnostic", reason="Detected decline/drop/underperformance language requiring "
                                             "multi-source evidence (sales trend, discounts, marketing spend, reviews, strategy docs).",
            resolved_product=product, resolved_category=category,
            signals={"is_analytical": is_analytical, "is_knowledge": is_knowledge},
        )

    if is_analytical and is_knowledge:
        # If the question is primarily asking about a document/policy/strategy topic,
        # and does NOT ask for specific numeric metric answers, prefer knowledge routing.
        # E.g. 'What discount policy does the pricing policy specify?' => knowledge
        # But 'Which products had highest revenue AND what strategy is recommended?' => hybrid
        has_numeric_ask = any(w in q_lower for w in ["highest", "lowest", "top", "how much",
                                                     "how many", "total", "which product",
                                                     "which campaign", "which category"])
        doc_focus = any(kw in q_lower for kw in ["policy", "policies", "pricing policy",
                                                  "guideline", "guidelines"])
        if doc_focus and not has_numeric_ask:
            return QueryClassification(
                query_type="knowledge",
                reason="Query is asking about a document/policy topic; routing to knowledge retrieval.",
                resolved_product=product, resolved_category=category,
            )
        return QueryClassification(
            query_type="hybrid", reason="Query mixes an analytical/metric ask with a knowledge/strategy ask.",
            resolved_product=product, resolved_category=category,
        )
    if is_analytical:
        return QueryClassification(
            query_type="analytical", reason="Query asks for a computable metric from structured data.",
            resolved_product=product, resolved_category=category,
        )
    if is_knowledge:
        return QueryClassification(
            query_type="knowledge", reason="Query asks about strategy, policy, or recommended approach.",
            resolved_product=product, resolved_category=category,
        )

    # Fallback: if a product/category was named but intent unclear, treat as hybrid
    # so both structured facts and any related policy context are offered.
    if product or category:
        return QueryClassification(
            query_type="hybrid", reason="Product/category resolved but question intent is unclear; "
                                         "retrieving both structured facts and related knowledge as a safe default.",
            resolved_product=product, resolved_category=category,
        )

    # Generic "performance"-style questions with no resolvable product/category and
    # no strong keyword signal: default to a bounded analytical overview rather than
    # knowledge, since "how's X doing" in a sales/marketing tool is usually a metrics
    # ask. This is a heuristic default, not a confident classification — documented
    # in README "Failure cases" as a known source of misrouting for vague questions.
    if any(w in q_lower for w in ["performance", "doing", "how is", "how's", "overview"]):
        return QueryClassification(
            query_type="analytical",
            reason="Vague performance-style question with no resolvable entity; defaulting to a general "
                   "structured-data overview rather than knowledge retrieval.",
        )

    return QueryClassification(
        query_type="knowledge",
        reason="No structured-data signal detected; defaulting to knowledge-base retrieval.",
    )
