"""
Database migration: creates schema on PostgreSQL and migrates data from SQLite.
"""
import os
import sqlite3
import sys
import json
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

# Load env
from dotenv import load_dotenv
load_dotenv()

# ═══════════════════════════════════════════════════════════════════════════
# postgreSQL connection
# ═══════════════════════════════════════════════════════════════════════════

def get_pg_conn():
    host = os.getenv("POSTGRES_HOST")
    port = int(os.getenv("POSTGRES_PORT", 5432))
    dbname = os.getenv("POSTGRES_DB", "postgres")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD")
    if not host or not password:
        raise EnvironmentError("POSTGRES_HOST and POSTGRES_PASSWORD must be set in .env")
    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password, sslmode="require")


# ═══════════════════════════════════════════════════════════════════════════
# SCHEMA
# ═══════════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """
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

CREATE TABLE IF NOT EXISTS evaluation_cases (
    id SERIAL PRIMARY KEY,
    case_id TEXT NOT NULL,
    bucket TEXT,
    question TEXT,
    expected_query_type TEXT,
    expected_source TEXT,
    expected_characteristics TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id SERIAL PRIMARY KEY,
    total_cases INTEGER,
    type_accuracy NUMERIC(5,4),
    retrieval_recall NUMERIC(5,4),
    avg_latency_ms NUMERIC(10,2),
    p95_latency_ms NUMERIC(10,2),
    by_bucket JSONB DEFAULT '{}',
    results JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW()
);

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
-- NOTE: This requires data to exist first; run after data migration
-- CREATE INDEX IF NOT EXISTS idx_embeddings_vector ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
"""


def create_schema(conn):
    """Create all tables and indexes on postgreSQL."""
    cur = conn.cursor()
    cur.execute(SCHEMA_SQL)
    conn.commit()
    cur.close()
    print("Schema created successfully!")
    
    # Create vector index separately (needs data first)
    try:
        cur = conn.cursor()
        cur.execute("""
            DO $$ BEGIN
                CREATE INDEX idx_embeddings_vector ON embeddings 
                USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
            EXCEPTION WHEN others THEN NULL;
            END $$;
        """)
        conn.commit()
        cur.close()
        print("Vector index created!")
    except Exception as e:
        print(f"Vector index deferred (will create after data): {e}")


def migrate_data(conn):
    """Migrate data from SQLite to PostgreSQL."""
    db_path = os.getenv("DB_PATH", "data/warehouse.db")
    if not Path(db_path).exists():
        print(f"SQLite not found at {db_path} — generating synthetic data first...")
        from src.ingestion.data_generator import generate_all
        generate_all()
    
    sqlite_conn = sqlite3.connect(db_path)
    sqlite_conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Products
    rows = [dict(r) for r in sqlite_conn.execute("SELECT * FROM products").fetchall()]
    if rows:
        execute_values(cur, "INSERT INTO products (product_id, product_name, category, subcategory, price, cost, rating, review_count) VALUES %s",
                       [(r["product_id"], r["product_name"], r["category"], r["subcategory"],
                         r["price"], r["cost"], r.get("rating"), r.get("review_count", 0)) for r in rows],
                       page_size=500)
        print(f"  Products: {len(rows)} rows")
    
    # Sales
    rows = [dict(r) for r in sqlite_conn.execute("SELECT * FROM sales").fetchall()]
    if rows:
        execute_values(cur, """INSERT INTO sales (order_id, product_id, customer_id, order_date, quantity,
                          selling_price, revenue, cost, discount) VALUES %s""",
                       [(r.get("order_id", ""), r["product_id"], r.get("customer_id", ""),
                         r["order_date"], r["quantity"], r["selling_price"],
                         r["revenue"], r["cost"], r["discount"]) for r in rows],
                       page_size=1000)
        print(f"  Sales: {len(rows)} rows")
    
    # Customers
    rows = [dict(r) for r in sqlite_conn.execute("SELECT * FROM customers").fetchall()]
    if rows:
        execute_values(cur, """INSERT INTO customers (customer_id, segment, region, acquisition_channel,
                          first_purchase_date, lifetime_value) VALUES %s""",
                       [(r["customer_id"], r["segment"], r["region"], r["acquisition_channel"],
                         r["first_purchase_date"], r["lifetime_value"]) for r in rows],
                       page_size=500)
        print(f"  Customers: {len(rows)} rows")
    
    # Campaigns
    rows = [dict(r) for r in sqlite_conn.execute("SELECT * FROM campaigns").fetchall()]
    if rows:
        execute_values(cur, """INSERT INTO campaigns (campaign_id, campaign_name, product_id, channel,
                          start_date, end_date, impressions, clicks, spend, conversions, attributed_revenue) VALUES %s""",
                       [(r["campaign_id"], r["campaign_name"], r["product_id"], r["channel"],
                         r["start_date"], r["end_date"], r["impressions"], r["clicks"],
                         r["spend"], r["conversions"], r["attributed_revenue"]) for r in rows],
                       page_size=500)
        print(f"  Campaigns: {len(rows)} rows")
    
    # Reviews
    rows = [dict(r) for r in sqlite_conn.execute("SELECT * FROM reviews").fetchall()]
    if rows:
        execute_values(cur, """INSERT INTO reviews (review_id, product_id, customer_id, rating,
                          review_text, review_date) VALUES %s""",
                       [(r.get("review_id", ""), r["product_id"], r.get("customer_id", ""),
                         r["rating"], r.get("review_text", ""), r["review_date"]) for r in rows],
                       page_size=1000)
        print(f"  Reviews: {len(rows)} rows")
    
    conn.commit()
    cur.close()
    sqlite_conn.close()
    print("Data migration complete!")


def migrate_knowledge_base(conn):
    """Migrate knowledge base documents and chunks into postgreSQL."""
    from src.ingestion.document_loader import load_knowledge_base
    chunks = load_knowledge_base()
    if not chunks:
        print("No knowledge base chunks to migrate.")
        return
    
    cur = conn.cursor()
    
    # Collect unique documents
    docs = {}
    for c in chunks:
        if c.document_id not in docs:
            docs[c.document_id] = {
                "document_id": c.document_id,
                "document_name": c.document_name,
                "document_type": c.document_type,
                "file_path": c.metadata.get("source_path", ""),
                "chunk_count": 0,
            }
        docs[c.document_id]["chunk_count"] += 1
    
    # Insert documents
    for doc in docs.values():
        cur.execute("""INSERT INTO documents (document_id, document_name, document_type, file_path, chunk_count)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (document_id) DO UPDATE SET chunk_count = EXCLUDED.chunk_count""",
                    (doc["document_id"], doc["document_name"], doc["document_type"],
                     doc["file_path"], doc["chunk_count"]))
    
    # Insert chunks
    for c in chunks:
        cur.execute("""INSERT INTO document_chunks (chunk_id, document_id, document_name, document_type, section, text, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (chunk_id) DO NOTHING""",
                    (c.chunk_id, c.document_id, c.document_name, c.document_type,
                     c.section, c.text, json.dumps(c.metadata)))
    
    conn.commit()
    cur.close()
    print(f"Knowledge base migrated: {len(docs)} documents, {len(chunks)} chunks")


def migrate_embeddings(conn):
    """Generate embeddings and store in pgvector."""
    from src.retrieval.embeddings import get_embedder
    import numpy as np
    
    cur = conn.cursor()
    cur.execute("SELECT chunk_id, text FROM document_chunks")
    rows = cur.fetchall()
    if not rows:
        print("No chunks to embed.")
        return
    
    chunk_ids = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    
    embedder = get_embedder()
    embedder.fit(texts)
    vectors = embedder.embed(texts)
    
    # Insert embeddings
    for cid, vec in zip(chunk_ids, vectors):
        vec_str = "[" + ",".join(str(float(v)) for v in vec) + "]"
        cur.execute("INSERT INTO embeddings (chunk_id, embedding) VALUES (%s, %s::vector)",
                    (cid, vec_str))
    
    conn.commit()
    cur.close()
    print(f"Embeddings migrated: {len(chunk_ids)} vectors, dim={vectors.shape[1]}")


def add_semantic_layer(conn):
    """Add semantic metric and dimension definitions."""
    metrics = [
        ("Revenue", "Total sales revenue", "SUM(revenue)", "sales"),
        ("Units Sold", "Total units sold", "SUM(quantity)", "sales"),
        ("Gross Profit", "Revenue minus cost", "SUM(revenue - cost)", "sales"),
        ("Gross Margin", "Profit margin percentage", "100 * SUM(revenue - cost) / SUM(revenue)", "sales"),
        ("Average Order Value", "Revenue per order", "SUM(revenue) / COUNT(DISTINCT order_id)", "sales"),
        ("Discount %", "Mean discount applied", "AVG(discount)", "sales"),
        ("ROAS", "Return on ad spend", "SUM(attributed_revenue) / SUM(spend)", "campaigns"),
        ("CTR", "Click-through rate", "SUM(clicks) / SUM(impressions)", "campaigns"),
        ("Conversion Rate", "Conversion rate", "SUM(conversions) / SUM(clicks)", "campaigns"),
        ("CAC", "Customer acquisition cost", "SUM(spend) / COUNT(DISTINCT customer_id)", "campaigns"),
        ("LTV", "Customer lifetime value", "AVG(lifetime_value)", "customers"),
        ("Repeat Purchase Rate", "Repeat purchase rate", "COUNT(DISTINCT customer_id with orders > 1) / COUNT(DISTINCT customer_id)", "sales"),
    ]
    dims = [
        ("Product", "product_id, product_name, category, subcategory", "products"),
        ("Category", "product category grouping", "products"),
        ("Customer", "customer_id, segment, region", "customers"),
        ("Customer Segment", "Premium, Regular, Budget, New Customer", "customers"),
        ("Region", "geographic region", "customers"),
        ("Campaign", "campaign_id, campaign_name, channel", "campaigns"),
        ("Channel", "marketing channel", "campaigns"),
        ("Date", "order_date, start_date, end_date", "sales"),
    ]
    cur = conn.cursor()
    for name, defn, formula, source in metrics:
        cur.execute("""INSERT INTO semantic_metrics (metric_name, definition, formula, data_source)
                       VALUES (%s, %s, %s, %s) ON CONFLICT (metric_name) DO NOTHING""",
                    (name, defn, formula, source))
    for name, defn, source in dims:
        cur.execute("""INSERT INTO semantic_dimensions (dimension_name, definition, source_columns)
                       VALUES (%s, %s, %s) ON CONFLICT (dimension_name) DO NOTHING""",
                    (name, defn, source))
    conn.commit()
    cur.close()
    print(f"Semantic layer: {len(metrics)} metrics, {len(dims)} dimensions")


def verify_migration(conn):
    """Verify all tables have data."""
    cur = conn.cursor()
    tables = ["products", "sales", "customers", "campaigns", "reviews",
              "documents", "document_chunks", "embeddings", "semantic_metrics", "semantic_dimensions"]
    print("\n=== VERIFICATION ===")
    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        status = "OK" if count > 0 else "EMPTY"
        print(f"  {table:25s}: {count:>6} rows [{status}]")
    cur.close()


if __name__ == "__main__":
    print("Connecting to PostgreSQL...")
    conn = get_pg_conn()
    
    print("\n1. Creating schema...")
    create_schema(conn)
    
    print("\n2. Migrating structured data...")
    migrate_data(conn)
    
    print("\n3. Migrating knowledge base...")
    migrate_knowledge_base(conn)
    
    print("\n4. Migrating embeddings to pgvector...")
    migrate_embeddings(conn)
    
    print("\n5. Adding semantic layer...")
    add_semantic_layer(conn)
    
    print("\n6. Verifying...")
    verify_migration(conn)
    
    conn.close()
    print("\nMigration complete!")
