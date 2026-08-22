import pytest

from src.analytics import sql_layer


def test_top_products_by_revenue_returns_ranked_list():
    results = sql_layer.top_products_by_revenue(limit=5)
    assert len(results) == 5
    revenues = [r["revenue"] for r in results]
    assert revenues == sorted(revenues, reverse=True)


def test_category_performance_has_required_fields():
    results = sql_layer.category_performance()
    assert len(results) > 0
    row = results[0]
    for field in ("category", "revenue", "units_sold", "gross_profit", "gross_margin_pct", "avg_discount_pct"):
        assert field in row


def test_campaign_performance_roas_calculation():
    results = sql_layer.campaign_performance(limit=5, order_by="roas")
    for r in results:
        if r["spend"]:
            expected_roas = round(r["attributed_revenue"] / r["spend"], 2)
            assert abs(r["roas"] - expected_roas) < 0.01


def test_product_metrics_gross_margin_consistency():
    product = sql_layer.top_products_by_revenue(limit=1)[0]
    metrics = sql_layer.product_metrics(product["product_id"])
    assert metrics["revenue"] > 0
    computed_margin = round(100 * metrics["gross_profit"] / metrics["revenue"], 2)
    assert abs(metrics["gross_margin_pct"] - computed_margin) < 0.01


def test_revenue_growth_calculation():
    product = sql_layer.top_products_by_revenue(limit=1)[0]
    result = sql_layer.revenue_growth(
        product["product_id"],
        period_a=("2024-08-01", "2024-12-31"),
        period_b=("2025-01-01", "2025-06-30"),
    )
    assert "growth_pct" in result
    assert result["revenue_a"] >= 0
    assert result["revenue_b"] >= 0


def test_find_product_by_name():
    product = sql_layer.find_product_by_name("Aurora Pro Wireless Earbuds")
    assert product is not None
    assert product["product_id"] == "P0001"


def test_repeat_purchase_rate_bounds():
    result = sql_layer.repeat_purchase_rate()
    assert 0 <= result["repeat_purchase_rate_pct"] <= 100


def test_review_summary_negative_pct_bounds():
    summary = sql_layer.review_summary("P0001")
    if summary["review_count"] > 0:
        assert 0 <= summary["negative_review_pct"] <= 100
