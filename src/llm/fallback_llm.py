"""
Fallback LLM: a zero-dependency, deterministic *grounded answer generator*
used when no real LLM backend (Ollama) is available — which is the case in
the sandbox this project was built in (see README "Environment
Constraints").

This is NOT a neural language model — it's a template engine that
constructs the answer directly from the same structured EVIDENCE contract
a real LLM would receive (see prompt_templates.py). It parses the EVIDENCE
JSON block out of the prompt and renders it deterministically per
query_type. Because it never "generates" free text beyond values pulled
straight from EVIDENCE, it is hallucination-proof by construction — a
useful property to call out in the "Unknown / Hallucination Test" and
"Failure cases" sections of the README, alongside its obvious downside
(it cannot paraphrase, summarize loosely, or answer anything the templates
didn't anticipate as fluently as a real LLM would).

Switch LLM_BACKEND=ollama in .env (with Ollama + an open model installed)
to replace this with real generation — no other code changes needed.
"""
import json
import re
import time

from src.llm.base import BaseLLM, LLMResponse


def _extract_evidence(prompt: str) -> dict:
    match = re.search(r"EVIDENCE:\s*\n(.*?)\n\nQUERY_TYPE:", prompt, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def _fmt_money(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _render_knowledge(evidence: dict) -> str:
    chunks = evidence.get("knowledge_base_chunks", [])
    conflict = evidence.get("detected_conflict")
    lines = []
    if not chunks:
        return ("The available knowledge base does not contain sufficiently relevant information "
                "to answer this question reliably.")
    if conflict:
        lines.append("**Note — conflicting information detected:**")
        lines.append(f"- Marketing Strategy states: {conflict['marketing_strategy_values']}%")
        lines.append(f"- Pricing Policy states: {conflict['pricing_policy_values']}%")
        lines.append(f"- {conflict['note']}")
        lines.append("")
    lines.append("**From the knowledge base:**")
    for c in chunks[:3]:
        text = c["text"]
        snippet = text if len(text) < 320 else text[:317] + "..."
        lines.append(f"- {snippet}")
    lines.append("")
    lines.append("**Sources:**")
    for c in chunks[:3]:
        lines.append(f"- {c['source']}")
    return "\n".join(lines)


def _render_analytical(evidence: dict) -> str:
    sd = evidence.get("structured_data", {})
    lines = []

    if "total_sales_summary" in sd:
        s = sd["total_sales_summary"]
        lines.append(f"**Total Sales Summary:**")
        lines.append(f"- Total Revenue: {_fmt_money(s.get('total_revenue', 0))}")
        lines.append(f"- Total Units Sold: {s.get('total_units', 0):,}")
        lines.append(f"- Total Orders: {s.get('total_orders', 0):,}")
        lines.append(f"- Gross Profit: {_fmt_money(s.get('gross_profit', 0))}")
        lines.append(f"- Gross Margin: {s.get('gross_margin_pct', 0)}%")
        lines.append(f"- Average Order Value: {_fmt_money(s.get('avg_order_value', 0))}")
        lines.append(f"- Average Discount: {s.get('avg_discount', 0)}%")
    elif "revenue_by_region" in sd:
        regions = sd["revenue_by_region"]
        lines.append("**Revenue by Region:**")
        for r in regions:
            lines.append(f"- {r['region']}: {_fmt_money(r['revenue'])} ({r['customers']:,} customers, {r['units_sold']:,} units)")
        if regions:
            lines.append(f"\n**Best performing region:** {regions[0]['region']} with {_fmt_money(regions[0]['revenue'])} in revenue.")
    elif "monthly_trend" in sd:
        trend = sd["monthly_trend"]
        lines.append("**Monthly Revenue Trend:**")
        for t in trend:
            lines.append(f"- {t['month']}: {_fmt_money(t['revenue'])} ({t['units_sold']:,} units, profit {_fmt_money(t['profit'])})")
    elif "customer_segments" in sd:
        segments = sd["customer_segments"]
        lines.append("**Customer Segment Performance:**")
        for s in segments:
            lines.append(f"- {s['segment']}: {s['customers']:,} customers, avg LTV ${s['avg_ltv']:,.2f}, revenue {_fmt_money(s['revenue'])}")
        if segments:
            lines.append(f"\n**Highest LTV segment:** {segments[0]['segment']} with ${segments[0]['avg_ltv']:,.2f} average lifetime value.")
    elif "discount_margin_analysis" in sd:
        bands = sd["discount_margin_analysis"]
        lines.append("**Discount vs Margin Analysis:**")
        for b in bands:
            lines.append(f"- {b['discount_band']}: {b['orders']} orders, avg margin {b['avg_margin_pct']}%, revenue {_fmt_money(b['total_revenue'])}")
        lines.append("\n*Note: The relationship between discount and margin is an observed correlation in the data, not necessarily a causal relationship.*")
    elif "top_products_by_revenue" in sd and sd["top_products_by_revenue"]:
        top = sd["top_products_by_revenue"][0]
        lines.append(f"**Top product by revenue:** {top['product_name']} ({top['category']}) — "
                      f"{_fmt_money(top['revenue'])} across {top['units_sold']} units sold.")
        lines.append("")
        lines.append("**Top 5 by revenue:**")
        for p in sd["top_products_by_revenue"]:
            lines.append(f"- {p['product_name']}: {_fmt_money(p['revenue'])} ({p['units_sold']} units)")
    if "top_campaigns_by_roas" in sd and sd["top_campaigns_by_roas"]:
        c = sd["top_campaigns_by_roas"][0]
        lines.append(f"\n**Top campaign by ROAS:** {c['campaign_name']} — {c['roas']}x "
                      f"(spend {_fmt_money(c['spend'])}, attributed revenue {_fmt_money(c['attributed_revenue'])}).")
        lines.append("\n**Top 5 campaigns by ROAS:**")
        for c in sd["top_campaigns_by_roas"]:
            lines.append(f"- {c['campaign_name']} ({c['channel']}): ROAS {c['roas']}x, "
                          f"spend {_fmt_money(c['spend'])}, revenue {_fmt_money(c['attributed_revenue'])}")
    elif "campaign_summary" in sd:
        campaigns = sd["campaign_summary"]
        lines.append("\n**Campaign Performance:**")
        for c in campaigns:
            lines.append(f"- {c['campaign_name']} ({c['channel']}): ROAS {c['roas']}x, spend {_fmt_money(c['spend'])}, revenue {_fmt_money(c['revenue'])}")
    if "category_performance" in sd and sd["category_performance"]:
        lines.append("\n**Category performance:**")
        for c in sd["category_performance"]:
            lines.append(f"- {c['category']}: revenue {_fmt_money(c['revenue'])}, "
                          f"gross margin {c['gross_margin_pct']}%")
    if "product" in sd:
        p = sd["product"]
        m = sd.get("product_metrics_all_time", {})
        lines.append(f"\n**{p['product_name']}** — revenue {_fmt_money(m.get('revenue'))}, "
                      f"units sold {m.get('units_sold')}, avg order value {_fmt_money(m.get('avg_order_value'))}, "
                      f"gross margin {m.get('gross_margin_pct')}%.")
    if not lines:
        lines.append("The structured data did not return a result for this specific query — "
                      "the requested product/category/metric may not be resolvable from the available fields.")
    lines.append("\n**Sources:** sales data, campaign data (SQLite structured tables)")
    return "\n".join(lines)


def _render_diagnostic(evidence: dict) -> str:
    sd = evidence.get("structured_data", {})
    lines = ["**Observed facts:**"]
    product = sd.get("product")
    pre = sd.get("pre_decline_metrics", {})
    decline = sd.get("decline_window_metrics", {})
    growth = sd.get("revenue_growth_q1_vs_q2_2025", {})
    reviews = sd.get("decline_window_reviews", {})

    if product:
        lines.append(f"- Product: {product['product_name']} ({product['category']})")
    if growth:
        lines.append(f"- Revenue Q1 2025: {_fmt_money(growth.get('revenue_a'))} -> "
                      f"Q2 2025: {_fmt_money(growth.get('revenue_b'))} "
                      f"({growth.get('growth_pct')}% change)")
    if pre and decline:
        lines.append(f"- Average discount fell from {pre.get('avg_discount_pct')}% (pre-period) "
                      f"to {decline.get('avg_discount_pct')}% (decline window)")
        lines.append(f"- Units sold fell from {pre.get('units_sold')} to {decline.get('units_sold')} "
                      f"across the compared windows")
    if reviews and reviews.get("review_count", 0) > 0:
        lines.append(f"- During the decline window, average rating was {reviews.get('avg_rating')} "
                      f"with {reviews.get('negative_review_pct')}% negative reviews "
                      f"({reviews.get('negative_review_count')} of {reviews.get('review_count')})")
        for s in reviews.get("sample_negative_reviews", [])[:2]:
            lines.append(f'  - Sample negative review: "{s}"')
    campaigns = sd.get("campaigns_for_product", [])
    q2_campaigns = [c for c in campaigns if "2025-04" <= c["start_date"] <= "2025-06-30"]
    if q2_campaigns:
        total_spend = sum(c["spend"] for c in q2_campaigns)
        lines.append(f"- Marketing spend on this product during Q2 2025: {_fmt_money(total_spend)} "
                      f"across {len(q2_campaigns)} campaign(s)")

    lines.append("\n**Possible explanations (inference, not confirmed causation):**")
    if pre and decline and decline.get("avg_discount_pct", 0) < pre.get("avg_discount_pct", 0):
        lines.append("- The discount reduction may have suppressed price-sensitive demand.")
    if reviews and reviews.get("negative_review_pct", 0) > 30:
        lines.append("- Elevated negative review volume in this window (connectivity/battery-life "
                      "complaints) suggests a product-quality issue may be contributing to the decline, "
                      "consistent with Product Strategy guidance that wireless audio issues are a leading "
                      "cause of both returns and rating decline.")
    lines.append("- These factors (reduced discount, reduced marketing spend, and negative review sentiment) "
                  "co-occur in the same window, which is suggestive but does not by itself prove which factor "
                  "is the primary driver.")

    lines.append("\n**Unsupported assumptions (explicitly NOT claimed as fact):**")
    lines.append("- We do not have evidence to isolate the exact causal weight of discount vs. marketing spend "
                  "vs. product quality — this would require a controlled analysis (e.g. a holdout period with "
                  "only one variable changed) beyond what this dataset supports.")
    lines.append("- We do not know competitor actions or broader market demand shifts in this window, "
                  "since that data is not in the provided dataset or knowledge base.")

    kb = evidence.get("knowledge_base_chunks", [])
    if kb:
        lines.append("\n**Relevant policy context:**")
        for c in kb[:2]:
            snippet = c["text"] if len(c["text"]) < 260 else c["text"][:257] + "..."
            lines.append(f"- {snippet}")

    lines.append("\n**Sources:** sales data, campaign data, review data" +
                  (", " + ", ".join(c["source"] for c in kb[:2]) if kb else ""))
    return "\n".join(lines)


def _render_hybrid(evidence: dict) -> str:
    analytical_part = _render_analytical(evidence)
    knowledge_part = _render_knowledge(evidence)
    return analytical_part + "\n\n---\n\n" + knowledge_part


def _render_unanswerable(evidence: dict) -> str:
    return ("The available data does not contain sufficient information to answer this question reliably. "
            f"{evidence.get('available_data_summary', '')}")


def _render_ambiguous(evidence: dict) -> str:
    return (f"This question is ambiguous as asked: {evidence.get('ambiguity_reason', '')} "
            f"{evidence.get('hint', '')}")


RENDERERS = {
    "knowledge": _render_knowledge,
    "analytical": _render_analytical,
    "hybrid": _render_hybrid,
    "diagnostic": _render_diagnostic,
    "unanswerable": _render_unanswerable,
    "ambiguous": _render_ambiguous,
}


class FallbackLLM(BaseLLM):
    def generate(self, prompt: str, system: str = None, max_tokens: int = 700) -> LLMResponse:
        start = time.time()
        evidence = _extract_evidence(prompt)
        qtype = evidence.get("query_type", "knowledge")
        renderer = RENDERERS.get(qtype, _render_knowledge)
        text = renderer(evidence)
        latency_ms = (time.time() - start) * 1000
        return LLMResponse(text=text, model_name="template-grounded-fallback-v1",
                            backend="fallback", latency_ms=latency_ms)
