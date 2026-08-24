"""
Structured-data access layer.

This module now delegates to database.pg_layer for PostgreSQL support.
Kept for backward compatibility — all existing imports continue to work.
"""
from src.database.pg_layer import (
    get_conn,
    find_product_by_name,
    get_product,
    list_categories,
    top_products_by_revenue,
    category_performance,
    revenue_growth,
    product_metrics,
    quarterly_trend,
    campaign_performance,
    campaigns_for_product,
    marketing_spend_to_revenue,
    segment_revenue,
    repeat_purchase_rate,
    customer_acquisition_cost,
    top_customers_by_ltv,
    total_sales_summary,
    revenue_by_region,
    monthly_revenue_trend,
    customer_segment_summary,
    campaign_summary,
    discount_margin_analysis,
    review_summary,
)
