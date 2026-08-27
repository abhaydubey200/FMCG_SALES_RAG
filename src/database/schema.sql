-- ═══════════════════════════════════════════════════════════════════
-- QueryBridge — PostgreSQL Schema
-- Dynamic Sales & Marketing Intelligence Platform
-- ═══════════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ═══════════════════════════════════════════════════════════════════════
-- WORKSPACE
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY DEFAULT 'default',
    name TEXT NOT NULL DEFAULT 'Default Workspace',
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO workspaces (workspace_id, name) VALUES ('default', 'Default Workspace')
ON CONFLICT (workspace_id) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════
-- ASSET REGISTRY (dynamic data catalog)
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    workspace_id TEXT DEFAULT 'default',
    name TEXT NOT NULL,
    type TEXT NOT NULL,           -- 'structured' | 'unstructured'
    source_type TEXT NOT NULL,    -- 'csv' | 'xlsx' | 'pdf' | 'manual' | 'seed'
    status TEXT DEFAULT 'processing',  -- 'processing' | 'ready' | 'error' | 'deleted'
    description TEXT DEFAULT '',
    tags JSONB DEFAULT '[]',
    domain TEXT DEFAULT 'unknown',  -- 'sales' | 'marketing' | 'customer' | 'product' | 'mixed' | 'unknown'
    schema JSONB DEFAULT '{}',
    row_count INTEGER DEFAULT 0,
    column_count INTEGER DEFAULT 0,
    size_bytes BIGINT DEFAULT 0,
    table_name TEXT,              -- physical PostgreSQL table name for structured data
    semantic_status TEXT DEFAULT 'pending',  -- 'pending' | 'mapped' | 'confirmed'
    processing_status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_assets_workspace ON assets(workspace_id);
CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type);
CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);

-- ═══════════════════════════════════════════════════════════════════════
-- DATASET METADATA
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    asset_id TEXT REFERENCES assets(asset_id),
    workspace_id TEXT DEFAULT 'default',
    filename TEXT NOT NULL,
    file_type TEXT,
    file_size_bytes BIGINT,
    row_count INTEGER,
    col_count INTEGER,
    quality_score NUMERIC(5,1),
    version INTEGER DEFAULT 1,
    is_current BOOLEAN DEFAULT TRUE,
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
-- SEMANTIC MAPPING LAYER
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS semantic_mappings (
    id SERIAL PRIMARY KEY,
    workspace_id TEXT DEFAULT 'default',
    asset_id TEXT,
    table_name TEXT NOT NULL,
    source_column TEXT NOT NULL,
    canonical_concept TEXT NOT NULL,
    concept_type TEXT NOT NULL,
    confidence NUMERIC(3,2) DEFAULT 0.5,
    mapping_method TEXT DEFAULT 'auto',
    approved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(asset_id, source_column)
);

CREATE INDEX IF NOT EXISTS idx_sm_workspace ON semantic_mappings(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sm_concept ON semantic_mappings(canonical_concept);
CREATE INDEX IF NOT EXISTS idx_sm_table ON semantic_mappings(table_name);

-- ═══════════════════════════════════════════════════════════════════════
-- DOCUMENT / RAG TABLES
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    document_name TEXT NOT NULL,
    document_type TEXT,
    file_path TEXT,
    chunk_count INTEGER DEFAULT 0,
    workspace_id TEXT DEFAULT 'default',
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
-- DATASET RELATIONSHIPS
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS dataset_relationships (
    id SERIAL PRIMARY KEY,
    workspace_id TEXT DEFAULT 'default',
    source_asset_id TEXT,
    source_column TEXT,
    target_asset_id TEXT,
    target_column TEXT,
    relationship_type TEXT DEFAULT 'possible',
    confidence NUMERIC(3,2) DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════
-- CONVERSATIONS
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New Conversation',
    workspace_id TEXT DEFAULT 'default',
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

-- ═══════════════════════════════════════════════════════════════════════
-- ACTIONS
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
-- EXECUTION PERSISTENCE (agentic AI traces)
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS execution_plans (
    plan_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    workspace_id TEXT DEFAULT 'default',
    conversation_id TEXT,
    goal TEXT DEFAULT '',
    query_type TEXT DEFAULT 'analytical',
    agents_used JSONB DEFAULT '[]',
    skills_used JSONB DEFAULT '[]',
    steps JSONB DEFAULT '[]',
    status TEXT DEFAULT 'created',
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ep_trace ON execution_plans(trace_id);
CREATE INDEX IF NOT EXISTS idx_ep_workspace ON execution_plans(workspace_id);
CREATE INDEX IF NOT EXISTS idx_ep_conv ON execution_plans(conversation_id);

CREATE TABLE IF NOT EXISTS execution_steps (
    step_id TEXT PRIMARY KEY,
    plan_id TEXT REFERENCES execution_plans(plan_id),
    agent_id TEXT NOT NULL,
    tool_id TEXT,
    action TEXT DEFAULT '',
    input_data JSONB,
    output_data JSONB,
    status TEXT DEFAULT 'pending',
    duration_ms FLOAT DEFAULT 0,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_es_plan ON execution_steps(plan_id);

CREATE TABLE IF NOT EXISTS agent_executions (
    id SERIAL PRIMARY KEY,
    trace_id TEXT NOT NULL,
    plan_id TEXT,
    agent_id TEXT NOT NULL,
    status TEXT DEFAULT 'running',
    input_data JSONB,
    output_data JSONB,
    duration_ms FLOAT DEFAULT 0,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ae_trace ON agent_executions(trace_id);

CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    evidence_type TEXT DEFAULT 'unknown',
    source TEXT DEFAULT '',
    metric TEXT,
    query_text TEXT,
    result_data JSONB,
    confidence FLOAT DEFAULT 1.0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_er_trace ON evidence_records(trace_id);

CREATE TABLE IF NOT EXISTS verification_results (
    id SERIAL PRIMARY KEY,
    trace_id TEXT NOT NULL,
    plan_id TEXT,
    verdict TEXT NOT NULL,
    reason TEXT DEFAULT '',
    issues JSONB DEFAULT '[]',
    warnings JSONB DEFAULT '[]',
    evidence_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vr_trace ON verification_results(trace_id);
