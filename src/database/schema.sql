-- ═══════════════════════════════════════════════════════════════════
-- Sales & Marketing Intelligence Platform — PostgreSQL Schema
-- ═══════════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ═══════════════════════════════════════════════════════════════════════
-- CORE TABLES
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT,
    price NUMERIC(10,2),
    cost NUMERIC(10,2),
    rating NUMERIC(3,1),
    review_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sales (
    id SERIAL PRIMARY KEY,
    order_id TEXT,
    product_id TEXT REFERENCES products(product_id),
    customer_id TEXT,
    order_date DATE,
    quantity INTEGER,
    selling_price NUMERIC(10,2),
    revenue NUMERIC(12,2),
    cost NUMERIC(12,2),
    discount NUMERIC(5,2)
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    segment TEXT,
    region TEXT,
    acquisition_channel TEXT,
    first_purchase_date DATE,
    lifetime_value NUMERIC(10,2)
);

CREATE TABLE IF NOT EXISTS campaigns (
    id SERIAL PRIMARY KEY,
    campaign_id TEXT,
    campaign_name TEXT,
    product_id TEXT REFERENCES products(product_id),
    channel TEXT,
    start_date DATE,
    end_date DATE,
    impressions INTEGER,
    clicks INTEGER,
    spend NUMERIC(10,2),
    conversions INTEGER,
    attributed_revenue NUMERIC(12,2)
);

CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    review_id TEXT,
    product_id TEXT REFERENCES products(product_id),
    customer_id TEXT,
    rating INTEGER,
    review_text TEXT,
    review_date DATE
);

-- ═══════════════════════════════════════════════════════════════════════
-- DOCUMENT / RAG TABLES
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    document_name TEXT NOT NULL,
    document_type TEXT,
    file_path TEXT,
    chunk_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ready',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(document_id),
    document_name TEXT,
    document_type TEXT,
    section TEXT,
    text TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    chunk_id TEXT REFERENCES document_chunks(chunk_id),
    embedding vector(384),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════
-- DATASET TABLES
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_type TEXT,
    file_size_bytes BIGINT,
    row_count INTEGER,
    col_count INTEGER,
    quality_score NUMERIC(5,1),
    uploaded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dataset_columns (
    id SERIAL PRIMARY KEY,
    dataset_id TEXT REFERENCES datasets(dataset_id),
    column_name TEXT,
    dtype TEXT,
    null_count INTEGER,
    null_pct NUMERIC(5,2),
    unique_count INTEGER,
    semantic_type TEXT,
    sample_values JSONB DEFAULT '[]',
    min_val NUMERIC,
    max_val NUMERIC,
    mean_val NUMERIC
);

CREATE TABLE IF NOT EXISTS data_quality_results (
    id SERIAL PRIMARY KEY,
    dataset_id TEXT REFERENCES datasets(dataset_id),
    issue_type TEXT,
    severity TEXT,
    column_name TEXT,
    count INTEGER,
    message TEXT
);

-- ═══════════════════════════════════════════════════════════════════════
-- SEMANTIC LAYER
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS semantic_metrics (
    id SERIAL PRIMARY KEY,
    metric_name TEXT NOT NULL UNIQUE,
    definition TEXT,
    formula TEXT,
    data_source TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS semantic_dimensions (
    id SERIAL PRIMARY KEY,
    dimension_name TEXT NOT NULL UNIQUE,
    definition TEXT,
    source_columns TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════
-- AI / QUERY TABLES
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS queries (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    query_type TEXT,
    classification_reason TEXT,
    answer TEXT,
    sources JSONB DEFAULT '[]',
    evidence JSONB DEFAULT '{}',
    metrics JSONB DEFAULT '{}',
    latency_ms NUMERIC(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS insights (
    id SERIAL PRIMARY KEY,
    insight_type TEXT,
    title TEXT,
    description TEXT,
    impact TEXT,
    confidence TEXT,
    evidence JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════
-- CONVERSATIONS (persistent — replaces in-memory store)
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT DEFAULT 'New Conversation',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    result JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_messages_conv_id ON conversation_messages(conversation_id);

-- ═══════════════════════════════════════════════════════════════════════
-- ACTIONS (persistent — replaces in-memory store)
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    owner TEXT DEFAULT 'Unassigned',
    status TEXT DEFAULT 'open',
    source_insight TEXT DEFAULT '',
    expected_outcome TEXT DEFAULT '',
    actual_outcome TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════
-- EVALUATION
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS evaluation_cases (
    id SERIAL PRIMARY KEY,
    case_id TEXT NOT NULL,
    bucket TEXT,
    question TEXT,
    expected_query_type TEXT,
    expected_source TEXT,
    expected_characteristics TEXT
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id SERIAL PRIMARY KEY,
    total_cases INTEGER,
    type_accuracy NUMERIC(5,4),
    retrieval_recall NUMERIC(5,4),
    avg_latency_ms NUMERIC(10,2),
    by_bucket JSONB DEFAULT '{}',
    results JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════
-- OBSERVABILITY
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS system_events (
    id SERIAL PRIMARY KEY,
    event_type TEXT,
    component TEXT,
    message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════
-- INDEXES
-- ═══════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_sales_product_id ON sales(product_id);
CREATE INDEX IF NOT EXISTS idx_sales_order_date ON sales(order_date);
CREATE INDEX IF NOT EXISTS idx_sales_customer_id ON sales(customer_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_product_id ON campaigns(product_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_channel ON campaigns(channel);
CREATE INDEX IF NOT EXISTS idx_reviews_product_id ON reviews(product_id);
CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_chunk_id ON embeddings(chunk_id);

-- Vector similarity index (IVFFlat for pgvector)
DO $$ BEGIN
    CREATE INDEX idx_embeddings_vector ON embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
EXCEPTION WHEN others THEN NULL;
END $$;

-- ═══════════════════════════════════════════════════════════════════════
-- INITIAL DATA: Semantic Layer
-- ═══════════════════════════════════════════════════════════════════════

INSERT INTO semantic_metrics (metric_name, definition, formula, data_source) VALUES
('Revenue', 'Total sales revenue', 'SUM(revenue)', 'sales'),
('Units Sold', 'Total units sold', 'SUM(quantity)', 'sales'),
('Gross Profit', 'Revenue minus cost of goods', 'SUM(revenue - cost)', 'sales'),
('Gross Margin', 'Profit margin percentage', '100 * SUM(revenue - cost) / SUM(revenue)', 'sales'),
('Average Order Value', 'Revenue per order', 'SUM(revenue) / COUNT(DISTINCT order_id)', 'sales'),
('Discount %', 'Mean discount applied', 'AVG(discount)', 'sales'),
('ROAS', 'Return on ad spend', 'SUM(attributed_revenue) / SUM(spend)', 'campaigns'),
('CTR', 'Click-through rate', 'SUM(clicks) / SUM(impressions)', 'campaigns'),
('Conversion Rate', 'Conversion rate', 'SUM(conversions) / SUM(clicks)', 'campaigns'),
('CAC', 'Customer acquisition cost', 'SUM(spend) / COUNT(DISTINCT customer_id)', 'campaigns'),
('LTV', 'Customer lifetime value', 'AVG(lifetime_value)', 'customers'),
('Repeat Purchase Rate', 'Repeat purchase rate', 'customers with >1 order / total', 'sales')
ON CONFLICT (metric_name) DO NOTHING;

INSERT INTO semantic_dimensions (dimension_name, definition, source_columns) VALUES
('Product', 'product_id, product_name, category, subcategory', 'products'),
('Category', 'product category grouping', 'products'),
('Subcategory', 'subcategory within a category', 'products'),
('Customer', 'customer_id, segment, region', 'customers'),
('Customer Segment', 'Premium, Regular, Budget, New Customer', 'customers'),
('Region', 'geographic region', 'customers'),
('Campaign', 'campaign_id, campaign_name, channel', 'campaigns'),
('Channel', 'marketing channel', 'campaigns'),
('Date', 'order_date, start_date, end_date', 'sales')
ON CONFLICT (dimension_name) DO NOTHING;
