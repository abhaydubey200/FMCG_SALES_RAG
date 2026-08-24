"""
Visualization planner — generates structured chart/table specs from evidence data.

The LLM does NOT generate chart data. This module inspects the evidence
returned by the analytics pipeline and creates frontend-ready visualization
specifications with real data. The frontend renders these specs using
trusted React components (recharts).
"""
from typing import Optional


def plan_visualization(question: str, evidence: dict, query_type: str) -> dict:
    """Analyze the evidence and produce visualization specs.
    
    Returns a dict with:
        - kpis: list of {label, value, delta?, format?} for KPI cards
        - charts: list of chart specs {type, title, data, x_key, y_keys, ...}
        - tables: list of table specs {title, columns, rows}
        - sql_hint: optional human-readable SQL description
        - follow_ups: list of suggested follow-up questions
    """
    structured = evidence.get("structured_data", {})
    viz = {"kpis": [], "charts": [], "tables": [], "follow_ups": []}

    if query_type in ("unanswerable", "ambiguous"):
        return viz

    # --- KPI extraction ---
    viz["kpis"] = _extract_kpis(structured, question)

    # --- Chart generation ---
    viz["charts"] = _extract_charts(structured, question)

    # --- Table generation ---
    viz["tables"] = _extract_tables(structured, question)

    # --- Follow-up questions ---
    viz["follow_ups"] = _generate_follow_ups(question, structured, evidence, query_type)

    return viz


def _extract_kpis(structured: dict, question: str) -> list:
    """Extract KPI cards from structured data."""
    kpis = []
    q_lower = question.lower()

    # Total sales summary
    summary = structured.get("total_sales_summary")
    if summary:
        kpis.append({
            "label": "Total Revenue",
            "value": _fmt_currency(summary.get("total_revenue")),
            "format": "currency",
        })
        kpis.append({
            "label": "Total Orders",
            "value": _fmt_number(summary.get("total_orders")),
            "format": "number",
        })
        kpis.append({
            "label": "Avg Order Value",
            "value": _fmt_currency(summary.get("avg_order_value")),
            "format": "currency",
        })
        if summary.get("gross_margin_pct") is not None:
            kpis.append({
                "label": "Gross Margin",
                "value": f"{summary['gross_margin_pct']:.1f}%",
                "format": "percent",
            })

    # Revenue by region
    regions = structured.get("revenue_by_region")
    if regions and isinstance(regions, list):
        best = max(regions, key=lambda r: r.get("revenue", 0))
        worst = min(regions, key=lambda r: r.get("revenue", 0))
        kpis.append({
            "label": "Top Region",
            "value": best.get("region", "N/A"),
            "format": "text",
        })
        kpis.append({
            "label": "Lowest Region",
            "value": worst.get("region", "N/A"),
            "format": "text",
        })

    # Product metrics
    pm = structured.get("product_metrics_all_time")
    if pm:
        kpis.append({
            "label": "Revenue",
            "value": _fmt_currency(pm.get("revenue")),
            "format": "currency",
        })
        kpis.append({
            "label": "Units Sold",
            "value": _fmt_number(pm.get("units_sold")),
            "format": "number",
        })
        if pm.get("gross_margin_pct") is not None:
            kpis.append({
                "label": "Margin",
                "value": f"{pm['gross_margin_pct']:.1f}%",
                "format": "percent",
            })

    # Campaign performance
    campaigns = structured.get("top_campaigns_by_roas")
    if campaigns and isinstance(campaigns, list) and len(campaigns) > 0:
        top = campaigns[0]
        kpis.append({
            "label": "Best Campaign ROAS",
            "value": f"{top.get('roas', 0):.2f}x",
            "format": "roas",
        })

    # Customer segments
    segments = structured.get("customer_segments")
    if segments and isinstance(segments, list):
        best_seg = max(segments, key=lambda s: s.get("revenue", 0))
        kpis.append({
            "label": "Top Segment",
            "value": best_seg.get("segment", "N/A"),
            "format": "text",
        })

    # Discount analysis
    discount = structured.get("discount_margin_analysis")
    if discount and isinstance(discount, list):
        # Find the band with highest revenue
        best_band = max(discount, key=lambda d: d.get("total_revenue", 0))
        kpis.append({
            "label": "Best Revenue Band",
            "value": best_band.get("discount_band", "N/A"),
            "format": "text",
        })

    return kpis


def _extract_charts(structured: dict, question: str) -> list:
    """Generate chart specifications from structured data."""
    charts = []
    q_lower = question.lower()

    # Monthly trend -> line chart
    trend = structured.get("monthly_trend")
    if trend and isinstance(trend, list) and len(trend) > 1:
        charts.append({
            "type": "line",
            "title": "Monthly Revenue Trend",
            "data": [
                {"month": t.get("month", ""), "revenue": t.get("revenue", 0), "profit": t.get("profit", 0)}
                for t in trend
            ],
            "x_key": "month",
            "y_keys": ["revenue"],
            "y_labels": ["Revenue"],
            "colors": ["#4f46e5"],
        })

    # Revenue by region -> bar chart
    regions = structured.get("revenue_by_region")
    if regions and isinstance(regions, list):
        charts.append({
            "type": "bar",
            "title": "Revenue by Region",
            "data": [
                {"region": r.get("region", ""), "revenue": r.get("revenue", 0), "customers": r.get("customers", 0)}
                for r in regions
            ],
            "x_key": "region",
            "y_keys": ["revenue"],
            "y_labels": ["Revenue"],
            "colors": ["#4f46e5"],
        })

    # Category performance -> grouped bar chart
    cat_perf = structured.get("category_performance")
    if cat_perf and isinstance(cat_perf, list):
        charts.append({
            "type": "bar",
            "title": "Category Performance",
            "data": [
                {"category": c.get("category", ""), "revenue": c.get("revenue", 0), "profit": c.get("gross_profit", 0)}
                for c in cat_perf
            ],
            "x_key": "category",
            "y_keys": ["revenue", "profit"],
            "y_labels": ["Revenue", "Gross Profit"],
            "colors": ["#4f46e5", "#059669"],
        })

    # Quarterly trend -> line chart
    quarterly = structured.get("quarterly_trend")
    if quarterly and isinstance(quarterly, list) and len(quarterly) > 1:
        charts.append({
            "type": "line",
            "title": "Quarterly Trend",
            "data": [
                {"quarter": q.get("quarter", ""), "revenue": q.get("revenue", 0), "units_sold": q.get("units_sold", 0)}
                for q in quarterly
            ],
            "x_key": "quarter",
            "y_keys": ["revenue"],
            "y_labels": ["Revenue"],
            "colors": ["#4f46e5"],
        })

    # Customer segments -> bar chart
    segments = structured.get("customer_segments")
    if segments and isinstance(segments, list):
        charts.append({
            "type": "bar",
            "title": "Revenue by Customer Segment",
            "data": [
                {"segment": s.get("segment", ""), "revenue": s.get("revenue", 0), "customers": s.get("customers", 0)}
                for s in segments
            ],
            "x_key": "segment",
            "y_keys": ["revenue"],
            "y_labels": ["Revenue"],
            "colors": ["#7c3aed"],
        })

    # Discount margin analysis -> bar chart
    discount = structured.get("discount_margin_analysis")
    if discount and isinstance(discount, list):
        charts.append({
            "type": "bar",
            "title": "Revenue by Discount Band",
            "data": [
                {"band": d.get("discount_band", ""), "revenue": d.get("total_revenue", 0), "orders": d.get("orders", 0)}
                for d in discount
            ],
            "x_key": "band",
            "y_keys": ["revenue"],
            "y_labels": ["Revenue"],
            "colors": ["#d97706"],
        })

    # Campaign summary -> bar chart
    campaign_summary = structured.get("campaign_summary")
    if campaign_summary and isinstance(campaign_summary, list):
        charts.append({
            "type": "bar",
            "title": "Campaign Performance (ROAS)",
            "data": [
                {"campaign": c.get("campaign_name", "")[:30], "roas": c.get("roas", 0), "revenue": c.get("revenue", 0)}
                for c in campaign_summary
            ],
            "x_key": "campaign",
            "y_keys": ["roas"],
            "y_labels": ["ROAS"],
            "colors": ["#059669"],
        })

    return charts


def _extract_tables(structured: dict, question: str) -> list:
    """Generate table specifications from structured data."""
    tables = []

    # Revenue by region table
    regions = structured.get("revenue_by_region")
    if regions and isinstance(regions, list):
        tables.append({
            "title": "Revenue by Region",
            "columns": [
                {"key": "region", "header": "Region", "sortable": True},
                {"key": "customers", "header": "Customers", "sortable": True, "align": "right"},
                {"key": "revenue", "header": "Revenue", "sortable": True, "align": "right", "format": "currency"},
                {"key": "units_sold", "header": "Units Sold", "sortable": True, "align": "right"},
                {"key": "avg_selling_price", "header": "Avg Price", "sortable": True, "align": "right", "format": "currency"},
            ],
            "rows": regions,
        })

    # Category performance table
    cat_perf = structured.get("category_performance")
    if cat_perf and isinstance(cat_perf, list):
        tables.append({
            "title": "Category Performance",
            "columns": [
                {"key": "category", "header": "Category", "sortable": True},
                {"key": "revenue", "header": "Revenue", "sortable": True, "align": "right", "format": "currency"},
                {"key": "units_sold", "header": "Units", "sortable": True, "align": "right"},
                {"key": "gross_profit", "header": "Profit", "sortable": True, "align": "right", "format": "currency"},
                {"key": "gross_margin_pct", "header": "Margin %", "sortable": True, "align": "right", "format": "percent"},
            ],
            "rows": cat_perf,
        })

    # Top products table
    top_products = structured.get("top_products_by_revenue")
    if top_products and isinstance(top_products, list):
        tables.append({
            "title": "Top Products by Revenue",
            "columns": [
                {"key": "product_name", "header": "Product", "sortable": True},
                {"key": "category", "header": "Category", "sortable": True},
                {"key": "revenue", "header": "Revenue", "sortable": True, "align": "right", "format": "currency"},
                {"key": "units_sold", "header": "Units", "sortable": True, "align": "right"},
                {"key": "avg_selling_price", "header": "Avg Price", "sortable": True, "align": "right", "format": "currency"},
            ],
            "rows": top_products,
        })

    # Campaign performance table
    campaigns = structured.get("top_campaigns_by_roas") or structured.get("campaign_summary")
    if campaigns and isinstance(campaigns, list):
        tables.append({
            "title": "Campaign Performance",
            "columns": [
                {"key": "campaign_name", "header": "Campaign", "sortable": True},
                {"key": "channel", "header": "Channel", "sortable": True},
                {"key": "spend", "header": "Spend", "sortable": True, "align": "right", "format": "currency"},
                {"key": "revenue", "header": "Revenue", "sortable": True, "align": "right", "format": "currency"},
                {"key": "roas", "header": "ROAS", "sortable": True, "align": "right", "format": "roas"},
            ],
            "rows": campaigns,
        })

    # Customer segments table
    segments = structured.get("customer_segments")
    if segments and isinstance(segments, list):
        tables.append({
            "title": "Customer Segments",
            "columns": [
                {"key": "segment", "header": "Segment", "sortable": True},
                {"key": "customers", "header": "Customers", "sortable": True, "align": "right"},
                {"key": "revenue", "header": "Revenue", "sortable": True, "align": "right", "format": "currency"},
                {"key": "avg_ltv", "header": "Avg LTV", "sortable": True, "align": "right", "format": "currency"},
            ],
            "rows": segments,
        })

    # Discount analysis table
    discount = structured.get("discount_margin_analysis")
    if discount and isinstance(discount, list):
        tables.append({
            "title": "Discount Band Analysis",
            "columns": [
                {"key": "discount_band", "header": "Discount Band", "sortable": True},
                {"key": "orders", "header": "Orders", "sortable": True, "align": "right"},
                {"key": "total_revenue", "header": "Revenue", "sortable": True, "align": "right", "format": "currency"},
                {"key": "avg_profit", "header": "Avg Profit", "sortable": True, "align": "right", "format": "currency"},
                {"key": "avg_margin_pct", "header": "Margin %", "sortable": True, "align": "right", "format": "percent"},
            ],
            "rows": discount,
        })

    return tables


def _generate_follow_ups(question: str, structured: dict, evidence: dict, query_type: str) -> list:
    """Generate contextual follow-up questions based on current analysis."""
    follow_ups = []
    q_lower = question.lower()
    has_kb = bool(evidence.get("knowledge_base_chunks"))
    has_structured = bool(structured)

    if "total sales" in q_lower or "total revenue" in q_lower:
        follow_ups.extend([
            "Show monthly sales trend",
            "Which product generated the highest revenue?",
            "Show revenue by region",
        ])
    elif "region" in q_lower:
        follow_ups.extend([
            "Why is the lowest region underperforming?",
            "Show category breakdown by region",
            "Compare top 2 regions in detail",
        ])
    elif "product" in q_lower or "highest revenue" in q_lower:
        follow_ups.extend([
            "Show the quarterly trend for this product",
            "What are the reviews saying about this product?",
            "Compare with other products in the same category",
        ])
    elif "trend" in q_lower or "monthly" in q_lower:
        follow_ups.extend([
            "Which month had the biggest decline?",
            "Show revenue by category over time",
            "Show the seasonal pattern",
        ])
    elif "campaign" in q_lower:
        follow_ups.extend([
            "Which campaign has the best ROAS?",
            "Show campaign spend vs revenue",
            "Compare campaigns across channels",
        ])
    elif "segment" in q_lower:
        follow_ups.extend([
            "Which segment has the highest LTV?",
            "Show repeat purchase rate by segment",
            "Compare segment revenue trends",
        ])
    elif "review" in q_lower or "rating" in q_lower:
        follow_ups.extend([
            "What are the main negative themes?",
            "Show products with lowest ratings",
            "Compare review scores by category",
        ])
    elif "discount" in q_lower or "margin" in q_lower:
        follow_ups.extend([
            "Show the discount-margin relationship",
            "Which category has the best margin?",
            "What is the optimal discount level?",
        ])

    # Add RAG follow-up if knowledge base is available
    if has_kb and not has_structured:
        follow_ups.append("How does this compare with our actual sales data?")
    elif has_structured and not has_kb:
        follow_ups.append("What does our marketing strategy say about this?")

    # Hybrid follow-up
    if has_structured and has_kb:
        follow_ups.append("Investigate this using both data and strategy documents")

    return follow_ups[:5]  # Limit to 5 suggestions


# --- Formatting helpers ---

def _fmt_currency(val) -> str:
    if val is None:
        return "N/A"
    if isinstance(val, str):
        try:
            val = float(val)
        except (ValueError, TypeError):
            return val
    if abs(val) >= 1_000_000:
        return f"${val / 1_000_000:.2f}M"
    if abs(val) >= 1_000:
        return f"${val / 1_000:.1f}K"
    return f"${val:,.0f}"


def _fmt_number(val) -> str:
    if val is None:
        return "N/A"
    return f"{val:,}"
