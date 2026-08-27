"""
Database migration: creates schema on PostgreSQL.

NO SEED DATA. NO SYNTHETIC DATA. NO HARDCODED BUSINESS DATA.
The workspace starts completely empty. Users upload their own data.
"""
import os
import sys
from pathlib import Path

import psycopg2

# Load env
from dotenv import load_dotenv
load_dotenv()


def get_pg_conn():
    """Connect to PostgreSQL — tries DATABASE_URL first, then individual env vars."""
    database_url = os.getenv("DATABASE_URL", "")
    if database_url:
        url = database_url.replace("postgresql+asyncpg://", "postgresql://")
        return psycopg2.connect(url)
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", 5432))
    dbname = os.getenv("POSTGRES_DB", "ragsql")
    user = os.getenv("POSTGRES_USER", "ragsql")
    password = os.getenv("POSTGRES_PASSWORD", "ragsql_secret_dev")
    try:
        return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password, sslmode="require")
    except psycopg2.OperationalError:
        return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)


def create_schema(conn):
    """Create all tables and indexes from schema.sql."""
    schema_path = Path(__file__).parent / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    schema_sql = schema_path.read_text(encoding="utf-8")
    cur = conn.cursor()
    cur.execute(schema_sql)
    conn.commit()
    cur.close()
    print("Schema created successfully!")


def verify_schema(conn):
    """Verify all required tables exist."""
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]
    cur.close()

    expected = [
        "workspaces", "assets", "datasets", "dataset_columns", "data_quality_results",
        "semantic_mappings", "documents", "document_chunks", "embeddings",
        "dataset_relationships", "conversations", "conversation_messages",
        "actions", "execution_plans", "execution_steps", "agent_executions",
        "evidence_records", "verification_results",
    ]

    print("\n=== SCHEMA VERIFICATION ===")
    found = 0
    for table in expected:
        exists = table in tables
        status = "OK" if exists else "MISSING"
        if exists:
            found += 1
        print(f"  {table:35s} [{status}]")

    print(f"\n  {found}/{len(expected)} tables present")

    # Report any unexpected tables
    unexpected = [t for t in tables if t not in expected and not t.startswith("pg_")]
    if unexpected:
        print(f"\n  Additional tables: {', '.join(unexpected)}")

    return found == len(expected)


if __name__ == "__main__":
    print("Connecting to PostgreSQL...")
    conn = get_pg_conn()

    print("\nCreating schema...")
    create_schema(conn)

    print("\nVerifying schema...")
    ok = verify_schema(conn)

    conn.close()
    print(f"\nMigration {'complete' if ok else 'completed with issues'}!")
