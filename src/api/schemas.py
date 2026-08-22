from typing import List, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)


class SourceItem(BaseModel):
    type: str
    source: str


class QueryResponse(BaseModel):
    answer: str
    query_type: str
    sources: List[SourceItem]
    metrics: dict
    evidence: dict


class DocumentInfo(BaseModel):
    document_id: str
    document_name: str
    document_type: str
    chunk_count: int
    source_path: str


class UploadResponse(BaseModel):
    document_id: str
    document_name: str
    chunks_created: int
    message: str


class DeleteResponse(BaseModel):
    document_id: str
    deleted: bool
    message: str


class DashboardResponse(BaseModel):
    total_products: int
    total_revenue: float
    total_marketing_spend: float
    avg_roas: Optional[float]
    top_category: Optional[str]
    total_customers: int
    total_reviews: int


class OverviewKPI(BaseModel):
    total_revenue: float
    total_units_sold: int
    gross_margin_pct: Optional[float]
    total_marketing_spend: float
    avg_roas: Optional[float]
    total_customers: int
    revenue_growth_pct: Optional[float]
    units_growth_pct: Optional[float]
    margin_growth_pct: Optional[float]
    spend_growth_pct: Optional[float]
    roas_growth_pct: Optional[float]
    customer_growth_pct: Optional[float]


class MonthlyRevenueTrend(BaseModel):
    month: str
    revenue: float
    units_sold: int
    profit: float


class CategoryPerformance(BaseModel):
    category: str
    revenue: float
    units_sold: int
    gross_profit: float
    gross_margin_pct: Optional[float]
    avg_discount_pct: Optional[float]
    campaign_count: int
    total_spend: float
    total_roas: Optional[float]


class CampaignListItem(BaseModel):
    campaign_id: str
    campaign_name: str
    product_id: str
    channel: str
    start_date: str
    end_date: str
    impressions: int
    clicks: int
    spend: float
    conversions: int
    attributed_revenue: float
    ctr: Optional[float]
    conversion_rate: Optional[float]
    cpc: Optional[float]
    cpa: Optional[float]
    roas: Optional[float]


class ProductListItem(BaseModel):
    product_id: str
    product_name: str
    category: str
    subcategory: str
    price: float
    cost: float
    rating: Optional[float]
    review_count: int
    total_revenue: float
    total_units_sold: int
    gross_margin_pct: Optional[float]
    avg_discount_pct: Optional[float]
    total_marketing_spend: float
    product_roas: Optional[float]


class CustomerSegment(BaseModel):
    segment: str
    customers: int
    revenue: float
    avg_ltv: float
    repeat_purchase_rate: Optional[float]
    avg_order_value: Optional[float]


class EvaluationResult(BaseModel):
    total_cases: int
    query_type_accuracy: float
    retrieval_recall_at_k: float
    avg_end_to_end_latency_ms: float
    p95_end_to_end_latency_ms: float
    by_bucket: dict
    test_cases: List[dict]
