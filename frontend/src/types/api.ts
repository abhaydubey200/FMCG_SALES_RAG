export interface QueryRequest {
  question: string;
}

export interface SourceItem {
  type: string;
  source: string;
}

export interface QueryResponse {
  answer: string;
  query_type: string;
  sources: SourceItem[];
  metrics: Record<string, unknown>;
  evidence: {
    knowledge_base_chunks?: Array<{
      source: string;
      text: string;
      relevance_score: number;
    }>;
    structured_data?: Record<string, unknown>;
    detected_conflict?: { note: string };
  };
}

export interface DocumentInfo {
  document_id: string;
  document_name: string;
  document_type: string;
  chunk_count: number;
  source_path: string;
}

export interface UploadResponse {
  document_id: string;
  document_name: string;
  chunks_created: number;
  message: string;
}

export interface DeleteResponse {
  document_id: string;
  deleted: boolean;
  message: string;
}

export interface DashboardResponse {
  total_products: number;
  total_revenue: number;
  total_marketing_spend: number;
  avg_roas: number | null;
  top_category: string | null;
  total_customers: number;
  total_reviews: number;
}

export interface OverviewKPI {
  total_revenue: number;
  total_units_sold: number;
  gross_margin_pct: number | null;
  total_marketing_spend: number;
  avg_roas: number | null;
  total_customers: number;
  revenue_growth_pct: number | null;
  units_growth_pct: number | null;
  margin_growth_pct: number | null;
  spend_growth_pct: number | null;
  roas_growth_pct: number | null;
  customer_growth_pct: number | null;
}

export interface MonthlyRevenueTrend {
  month: string;
  revenue: number;
  units_sold: number;
  profit: number;
}

export interface CategoryPerformance {
  category: string;
  revenue: number;
  units_sold: number;
  gross_profit: number;
  gross_margin_pct: number | null;
  avg_discount_pct: number | null;
  campaign_count: number;
  total_spend: number;
  total_roas: number | null;
}

export interface CampaignListItem {
  campaign_id: string;
  campaign_name: string;
  product_id: string;
  channel: string;
  start_date: string;
  end_date: string;
  impressions: number;
  clicks: number;
  spend: number;
  conversions: number;
  attributed_revenue: number;
  ctr: number | null;
  conversion_rate: number | null;
  cpc: number | null;
  cpa: number | null;
  roas: number | null;
}

export interface ProductListItem {
  product_id: string;
  product_name: string;
  category: string;
  subcategory: string;
  price: number;
  cost: number;
  rating: number | null;
  review_count: number;
  total_revenue: number;
  total_units_sold: number;
  gross_margin_pct: number | null;
  avg_discount_pct: number | null;
  total_marketing_spend: number;
  product_roas: number | null;
}

export interface CustomerSegment {
  segment: string;
  customers: number;
  revenue: number;
  avg_ltv: number;
  repeat_purchase_rate: number | null;
  avg_order_value: number | null;
}

export interface EvaluationResult {
  total_cases: number;
  query_type_accuracy: number;
  retrieval_recall_at_k: number;
  avg_end_to_end_latency_ms: number;
  p95_end_to_end_latency_ms: number;
  by_bucket: Record<string, unknown>;
  test_cases: Array<Record<string, unknown>>;
}

export interface DataAsset {
  id: string;
  name: string;
  type: "structured" | "unstructured";
  category: string;
  source: string;
  status: string;
  row_count?: number;
  chunk_count?: number;
  metadata?: Record<string, unknown>;
}

export interface DataCenterResponse {
  assets: DataAsset[];
  total: number;
  structured_count: number;
  unstructured_count: number;
}

export interface Conversation {
  id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  role: "user" | "assistant";
  content: string;
  result?: QueryResponse;
}

export interface ConversationDetail {
  id: string;
  messages: ConversationMessage[];
  created_at: string;
  updated_at: string;
}

export interface Insight {
  type: "warning" | "success" | "info";
  title: string;
  description: string;
  impact: string;
  confidence: string;
  evidence: string[];
}

export interface InvestigationBreakdown {
  by_category?: Array<{
    category: string;
    revenue: number;
    profit: number;
    orders?: number;
    margin_pct?: number;
  }>;
  by_channel?: Array<{
    channel: string;
    campaigns: number;
    spend: number;
    revenue: number;
    roas: number;
  }>;
  by_segment?: Array<{
    segment: string;
    customers: number;
    avg_ltv: number;
    total_ltv: number;
  }>;
  by_status?: Array<{
    status: string;
    count: number;
  }>;
}

export interface Investigation {
  metric: string;
  breakdowns: InvestigationBreakdown;
  trend: Array<{
    month?: string;
    revenue: number;
    units?: number;
    profit?: number;
  }>;
  top_entities: Array<Record<string, unknown>>;
}

export interface ExecutiveBriefSection {
  title: string;
  content: string;
}

export interface ExecutiveBrief {
  sections: ExecutiveBriefSection[];
  generated_at: string;
}

export interface DataQualityCheck {
  column: string;
  null_count: number;
  completeness: number;
  status: "pass" | "warn";
}

export interface DataQualityTable {
  total_rows: number;
  checks: DataQualityCheck[];
  duplicate_count: number;
}

export interface DataQualityReport {
  tables: Record<string, DataQualityTable>;
  overall_score: number;
  total_checks: number;
  passed_checks: number;
}

export interface SystemHealthCheck {
  status: string;
  latency_ms?: number;
  error?: string;
  message?: string;
  backend?: string;
  model?: string;
  chunks?: number;
}

export interface SemanticMetric {
  name: string;
  definition: string;
  formula: string;
  source: string;
  dimensions: string[];
}

export interface SemanticDimension {
  name: string;
  columns?: string[];
  values?: string[];
  source: string;
}

export interface DataStatusResponse {
  structured: Record<string, number>;
  knowledge: { documents: number; chunks: number };
  has_data: boolean;
  has_knowledge: boolean;
}

export interface ActionItem {
  id: string;
  title: string;
  description: string;
  owner: string;
  status: "open" | "in_progress" | "completed" | "dismissed";
  source_insight: string;
  expected_outcome: string;
  actual_outcome: string | null;
  created_at: string;
  updated_at: string;
}

export interface SearchResult {
  type: string;
  id: string;
  title: string;
  subtitle: string;
}

export interface ReviewOverview {
  total_reviews: number;
  avg_rating: number | null;
  negative_count: number;
  negative_pct: number;
  by_rating: Array<{ rating: number; count: number }>;
  top_negative_themes: Array<{ theme: string; count: number }>;
}

export interface DiscountAnalytics {
  overall_avg_discount: number;
  discount_bands: Array<{
    discount_band: string;
    orders: number;
    total_revenue: number;
    total_units: number;
    avg_selling_price: number;
    avg_profit: number;
  }>;
  margin_by_band: Array<{
    band: string;
    avg_margin_pct: number;
  }>;
}

export interface DataHubDataset {
  dataset_id: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  total_rows: number;
  total_columns: number;
  sheets: string[] | null;
  quality_score: number;
  uploaded_at: string;
  issue_count: number;
}

export interface DataHubUploadResponse {
  dataset_ids: string[];
  profiles: Array<{
    dataset_id: string;
    filename: string;
    file_type: string;
    file_size_bytes: number;
    row_count: number;
    col_count: number;
    duplicate_rows: number;
    quality_score: number;
    uploaded_at: string;
    sheet_name: string | null;
    columns: Array<{
      name: string;
      dtype: string;
      null_count: number;
      null_pct: number;
      unique_count: number;
      sample_values: string[];
      semantic_type: string;
    }>;
    issues: Array<{
      type: string;
      severity: string;
      column?: string;
      count: number;
      message: string;
    }>;
  }>;
  total_rows: number;
  total_columns: number;
}
