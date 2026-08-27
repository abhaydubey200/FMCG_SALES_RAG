const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const errorBody = await res.text().catch(() => "");
    throw new Error(
      `API error ${res.status}: ${res.statusText}${errorBody ? ` - ${errorBody}` : ""}`
    );
  }

  return res.json();
}

async function uploadFile<T>(path: string, file: File): Promise<T> {
  const url = `${API_BASE}${path}`;
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(url, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const errorBody = await res.text().catch(() => "");
    throw new Error(
      `Upload error ${res.status}: ${res.statusText}${errorBody ? ` - ${errorBody}` : ""}`
    );
  }

  return res.json();
}

// Health
export const healthCheck = () => request<{ status: string; llm_backend: string; embedding_backend: string }>("/health");

// Query
export const sendQuery = (question: string) =>
  request<{
    answer: string;
    query_type: string;
    sources: Array<{ type: string; source: string }>;
    metrics: Record<string, unknown>;
    evidence: Record<string, unknown>;
    visualization?: {
      kpis?: Array<{ label: string; value: string; delta?: number | null }>;
      charts?: Array<{
        type: string;
        title: string;
        data: Record<string, unknown>[];
        x_key: string;
        y_keys: string[];
        y_labels?: string[];
        colors?: string[];
      }>;
      tables?: Array<{
        title: string;
        columns: Array<{
          key: string;
          header: string;
          sortable?: boolean;
          align?: string;
          format?: string;
        }>;
        rows: Record<string, unknown>[];
      }>;
      follow_ups?: string[];
    };
  }>("/query", {
    method: "POST",
    body: JSON.stringify({ question }),
  });

// Query (streaming)
export type StreamEvent =
  | { type: "metadata"; query_type: string; classification_reason: string; sources: Array<{ type: string; source: string }>; visualization: Record<string, unknown> }
  | { type: "token"; content: string }
  | { type: "done"; answer: string; metrics: Record<string, unknown>; visualization: Record<string, unknown> }
  | { type: "error"; error: string };

export async function* sendQueryStream(question: string): AsyncGenerator<StreamEvent> {
  const url = `${API_BASE}/query/stream`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  if (!res.ok) {
    const errorBody = await res.text().catch(() => "");
    throw new Error(`API error ${res.status}: ${res.statusText}${errorBody ? ` - ${errorBody}` : ""}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse SSE events from buffer
    const events = buffer.split("\n\n");
    buffer = events.pop() || ""; // keep incomplete event in buffer

    for (const eventBlock of events) {
      let eventType = "message";
      let data = "";

      for (const line of eventBlock.split("\n")) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          data = line.slice(6);
        }
      }

      if (!data) continue;

      try {
        const parsed = JSON.parse(data);
        yield { type: eventType, ...parsed } as StreamEvent;
      } catch {
        // skip malformed events
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Agentic AI — multi-specialist orchestrator endpoints
// ---------------------------------------------------------------------------

export const aiQuery = (question: string) =>
  request<{
    answer: string;
    sources: Array<{ type: string; source: string }>;
    metrics: Record<string, unknown>;
    evidence: Record<string, unknown>;
    visualization?: Record<string, unknown>;
  }>("/api/ai/query", {
    method: "POST",
    body: JSON.stringify({ question }),
  });

export async function* aiQueryStream(question: string): AsyncGenerator<StreamEvent> {
  const url = `${API_BASE}/api/ai/query/stream`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  if (!res.ok) {
    const errorBody = await res.text().catch(() => "");
    throw new Error(`API error ${res.status}: ${res.statusText}${errorBody ? ` - ${errorBody}` : ""}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const eventBlock of events) {
      let eventType = "message";
      let data = "";
      for (const line of eventBlock.split("\n")) {
        if (line.startsWith("event: ")) eventType = line.slice(7).trim();
        else if (line.startsWith("data: ")) data = line.slice(6);
      }
      if (!data) continue;
      try {
        const parsed = JSON.parse(data);
        yield { type: eventType, ...parsed } as StreamEvent;
      } catch { /* skip */ }
    }
  }
}

export const listAIAgents = () =>
  request<{ agents: Array<{ agent_id: string; name: string; description: string; domain: string; capabilities: string[]; version: string }>; count: number }>("/api/ai/agents");

export const listAISkills = () =>
  request<{ skills: Array<{ skill_id: string; name: string; description: string; required_tools: string[]; output_type: string; version: string }>; count: number }>("/api/ai/skills");

export const listAITools = () =>
  request<{ tools: Array<{ tool_id: string; name: string; description: string; category: string; version: string }>; categories: Record<string, string[]>; count: number }>("/api/ai/tools");

export const getAgentsHealth = () =>
  request<{ agents: Array<{ agent_id: string; status: string; version: string; executions: number; errors: number; avg_latency_ms: number }> }>("/api/ai/agents/health");

// Documents
export const listDocuments = () =>
  request<Array<{
    document_id: string;
    document_name: string;
    document_type: string;
    chunk_count: number;
    source_path: string;
  }>>("/documents");

export const uploadDocument = (file: File) =>
  uploadFile<{
    document_id: string;
    document_name: string;
    chunks_created: number;
    message: string;
  }>("/documents/upload", file);

export const deleteDocument = (documentId: string) =>
  request<{ document_id: string; deleted: boolean; message: string }>(
    `/documents/${documentId}`,
    { method: "DELETE" }
  );

// Dashboard
export const getDashboard = () =>
  request<{
    total_products: number;
    total_revenue: number;
    total_marketing_spend: number;
    avg_roas: number | null;
    top_category: string | null;
    total_customers: number;
    total_reviews: number;
  }>("/dashboard");

// Analytics
export const getAnalyticsOverview = () =>
  request<{
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
  }>("/api/analytics/overview");

export const getRevenueTrend = () =>
  request<Array<{
    month: string;
    revenue: number;
    units_sold: number;
    profit: number;
  }>>("/api/analytics/revenue-trend");

export const getCategoryPerformance = () =>
  request<Array<{
    category: string;
    revenue: number;
    units_sold: number;
    gross_profit: number;
    gross_margin_pct: number | null;
    avg_discount_pct: number | null;
    campaign_count: number;
    total_spend: number;
    total_roas: number | null;
  }>>("/api/analytics/category-performance");

export const getReviewsOverview = () =>
  request<{
    total_reviews: number;
    avg_rating: number | null;
    negative_count: number;
    negative_pct: number;
    by_rating: Array<{ rating: number; count: number }>;
    top_negative_themes: Array<{ theme: string; count: number }>;
  }>("/api/analytics/reviews");

export const getDiscountAnalytics = () =>
  request<{
    overall_avg_discount: number;
    discount_bands: Array<{
      discount_band: string;
      orders: number;
      total_revenue: number;
      total_units: number;
      avg_selling_price: number;
      avg_profit: number;
    }>;
    margin_by_band: Array<{ band: string; avg_margin_pct: number }>;
  }>("/api/analytics/discounts");

// Campaigns
export const listCampaigns = () =>
  request<Array<{
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
  }>>("/api/campaigns");

// Products
export const listProducts = () =>
  request<Array<{
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
  }>>("/api/products");

export const getProductDetail = (productId: string) =>
  request<{
    product: Record<string, unknown>;
    metrics: Record<string, unknown>;
    quarterly_trend: Array<Record<string, unknown>>;
    campaigns: Array<Record<string, unknown>>;
    reviews: Record<string, unknown>;
  }>(`/api/products/${productId}`);

// Customer Segments
export const getCustomerSegments = () =>
  request<Array<{
    segment: string;
    customers: number;
    revenue: number;
    avg_ltv: number;
    repeat_purchase_rate: number | null;
    avg_order_value: number | null;
  }>>("/api/customers/segments");

// Data Status
export const getDataStatus = () =>
  request<{
    structured: Record<string, number>;
    knowledge: { documents: number; chunks: number };
    has_data: boolean;
    has_knowledge: boolean;
  }>("/api/data-status");

// System Health
export const getSystemHealth = () =>
  request<Record<string, {
    status: string;
    latency_ms?: number;
    error?: string;
    message?: string;
    backend?: string;
    model?: string;
    chunks?: number;
  }>>("/api/system/health");

// Insights
export const generateInsights = () =>
  request<{
    insights: Array<{
      type: string;
      title: string;
      description: string;
      impact: string;
      confidence: string;
      evidence: string[];
    }>;
    count: number;
  }>("/api/insights", { method: "POST" });

// Executive Brief
export const generateExecutiveBrief = () =>
  request<{
    sections: Array<{ title: string; content: string }>;
    generated_at: string;
  }>("/api/executive-brief", { method: "POST" });

// Investigation
export const investigateMetric = (metric: string) =>
  request<{
    metric: string;
    breakdowns: Record<string, Array<Record<string, unknown>>>;
    trend: Array<Record<string, unknown>>;
    top_entities: Array<Record<string, unknown>>;
  }>(`/api/investigation/${metric}`);

// Data Hub
export const dataHubUpload = (file: File) =>
  uploadFile<{
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
  }>("/api/datahub/upload", file);

export const listDataHubDatasets = () =>
  request<Array<{
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
  }>>("/api/datahub/datasets");

export const getDataHubDataset = (datasetId: string) =>
  request<{
    profile: Record<string, unknown>;
    preview: Array<Record<string, unknown>>;
    semantic_mapping: Record<string, unknown>;
  }>(`/api/datahub/datasets/${datasetId}`);

export const deleteDataHubDataset = (datasetId: string) =>
  request<{ deleted: boolean }>(`/api/datahub/datasets/${datasetId}`, {
    method: "DELETE",
  });

// Semantic Layer
export const getSemanticMetrics = () =>
  request<{
    metrics: Array<{
      name: string;
      definition: string;
      formula: string;
      source: string;
      dimensions: string[];
    }>;
    count: number;
  }>("/api/semantic/metrics");

export const getSemanticDimensions = () =>
  request<{
    dimensions: Array<{
      name: string;
      columns?: string[];
      values?: string[];
      source: string;
    }>;
    count: number;
  }>("/api/semantic/dimensions");

// Data Quality
export const getDataQuality = () =>
  request<{
    tables: Record<string, {
      total_rows: number;
      checks: Array<{
        column: string;
        null_count: number;
        completeness: number;
        status: string;
      }>;
      duplicate_count: number;
    }>;
    overall_score: number;
    total_checks: number;
    passed_checks: number;
  }>("/api/data-quality");

// Data Center
export const getDataCenter = () =>
  request<{
    assets: Array<{
      id: string;
      name: string;
      type: string;
      category: string;
      source: string;
      status: string;
      row_count?: number;
      chunk_count?: number;
      metadata?: Record<string, unknown>;
    }>;
    total: number;
    structured_count: number;
    unstructured_count: number;
  }>("/api/data-center");

export const deleteDataCenterAsset = (assetId: string) =>
  request<{ deleted: boolean; type: string }>(`/api/data-center/${assetId}`,
    { method: "DELETE" }
  );

// Global Search
export const globalSearch = (q: string) =>
  request<{
    results: Array<{
      type: string;
      id: string;
      title: string;
      subtitle: string;
    }>;
    total: number;
  }>(`/api/search?q=${encodeURIComponent(q)}`);

// Conversations
export const listConversations = () =>
  request<{
    conversations: Array<{
      id: string;
      title: string;
      message_count: number;
      created_at: string;
      updated_at: string;
    }>;
  }>("/api/conversations");

export const createConversation = () =>
  request<{ id: string; message_count: number }>("/api/conversations", {
    method: "POST",
  });

export const getConversation = (conversationId: string) =>
  request<{
    id: string;
    messages: Array<{
      role: string;
      content: string;
      result?: Record<string, unknown>;
    }>;
    created_at: string;
    updated_at: string;
  }>(`/api/conversations/${conversationId}`);

export const addMessage = (
  conversationId: string,
  message: { role: string; content: string; result?: Record<string, unknown> }
) =>
  request<{
    id: string;
    messages: Array<{
      role: string;
      content: string;
      result?: Record<string, unknown>;
    }>;
  }>(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify(message),
  });

export const deleteConversation = (conversationId: string) =>
  request<{ deleted: boolean }>(`/api/conversations/${conversationId}`, {
    method: "DELETE",
  });

// Actions
export const listActions = () =>
  request<{
    actions: Array<{
      id: string;
      title: string;
      description: string;
      owner: string;
      status: string;
      source_insight: string;
      expected_outcome: string;
      actual_outcome: string | null;
      created_at: string;
      updated_at: string;
    }>;
    count: number;
  }>("/api/actions");

export const createAction = (action: {
  title: string;
  description?: string;
  owner?: string;
  source_insight?: string;
  expected_outcome?: string;
}) =>
  request<{
    id: string;
    title: string;
    description: string;
    owner: string;
    status: string;
    created_at: string;
  }>("/api/actions", {
    method: "POST",
    body: JSON.stringify(action),
  });

export const updateAction = (
  actionId: string,
  update: { status?: string; actual_outcome?: string }
) =>
  request<{
    id: string;
    title: string;
    status: string;
    actual_outcome: string | null;
    updated_at: string;
  }>(`/api/actions/${actionId}`, {
    method: "PUT",
    body: JSON.stringify(update),
  });

export const deleteAction = (actionId: string) =>
  request<{ deleted: boolean }>(`/api/actions/${actionId}`, {
    method: "DELETE",
  });
