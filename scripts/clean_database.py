"""
Complete database + file cleanup script.

Removes ALL seeded/demo/synthetic data from:
- PostgreSQL (legacy tables + dynamic tables)
- Local files (knowledge_base, vector_store, SQLite)

After running this, the workspace is completely empty and ready for
a user to upload their own data.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

import psycopg2


def get_pg_conn():
    """Connect to PostgreSQL — tries DATABASE_URL, then env vars, then Docker defaults."""
    # 1. Try DATABASE_URL
    database_url = os.getenv("DATABASE_URL", "")
    if database_url:
        url = database_url.replace("postgresql+asyncpg://", "postgresql://")
        return psycopg2.connect(url)

    # 2. Try individual env vars
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", 5432))
    dbname = os.getenv("POSTGRES_DB", "ragsql")
    user = os.getenv("POSTGRES_USER", "ragsql")
    password = os.getenv("POSTGRES_PASSWORD", "")

    # 3. Try Docker default credentials if not set
    if not password:
        password = "ragsql_secret_dev"
        host = "localhost"
        print("  Using Docker default credentials (localhost:5432)")

    try:
        return psycopg2.connect(
            host=host, port=port, dbname=dbname,
            user=user, password=password, sslmode="require"
        )
    except psycopg2.OperationalError:
        # Try without sslmode=require (local Docker)
        return psycopg2.connect(
            host=host, port=port, dbname=dbname,
            user=user, password=password
        )


def clean_postgresql(conn):
    """Remove all seed data from PostgreSQL. Uses autocommit so each
    statement is independent — one failure won't abort the rest."""
    conn.autocommit = True
    cur = conn.cursor()

    # 1. Drop ALL dynamic data tables (uploaded_data_*, data_*)
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        AND (table_name LIKE 'uploaded_data%%' OR table_name LIKE 'data_%%')
    """)
    dynamic_tables = [r[0] for r in cur.fetchall()]
    for table in dynamic_tables:
        try:
            cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
            print(f"  Dropped dynamic table: {table}")
        except Exception as e:
            print(f"  Skip drop {table}: {e}")

    # 2. Truncate legacy tables (keep structure, remove data)
    legacy_tables = [
        "verification_results", "evidence_records", "agent_executions",
        "execution_steps", "execution_plans",
        "conversation_messages", "conversations",
        "actions",
        "semantic_mappings", "dataset_relationships",
        "dataset_columns", "data_quality_results", "datasets",
        "embeddings", "document_chunks", "documents",
        "assets",
    ]
    for table in legacy_tables:
        try:
            cur.execute(f'TRUNCATE TABLE "{table}" CASCADE')
            print(f"  Truncated: {table}")
        except Exception as e:
            err = str(e).split('\n')[0]
            print(f"  Skip {table}: {err}")

    # 3. Clean workspace — keep default workspace only
    try:
        cur.execute("DELETE FROM workspaces WHERE workspace_id != 'default'")
        print("  Cleaned extra workspaces")
    except Exception as e:
        print(f"  Skip workspace cleanup: {e}")

    cur.close()


def clean_local_files():
    """Remove all seed/demo/local files."""
    base = Path(__file__).resolve().parent.parent

    # Knowledge base documents
    kb_dir = base / "data" / "knowledge_base"
    if kb_dir.exists():
        for f in kb_dir.glob("*"):
            if f.is_file():
                f.unlink()
                print(f"  Removed: {f.name}")

    # Vector store pickle
    for p in [base / "data" / "vector_store.pkl", base / "vector_store.pkl"]:
        if p.exists():
            p.unlink()
            print(f"  Removed: {p.name}")

    # SQLite database
    for p in [base / "data" / "warehouse.db", base / "warehouse.db"]:
        if p.exists():
            p.unlink()
            print(f"  Removed: {p.name}")


def verify_clean(conn):
    """Verify everything is clean. Uses autocommit for safe individual queries."""
    conn.autocommit = True
    cur = conn.cursor()

    print("\n=== VERIFICATION ===")

    # Check dynamic tables
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        AND (table_name LIKE 'uploaded_data%%' OR table_name LIKE 'data_%%')
    """)
    dynamic = [r[0] for r in cur.fetchall()]
    print(f"  Dynamic tables: {len(dynamic)} (should be 0)")

    def safe_count(table):
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            return cur.fetchone()[0]
        except Exception:
            return None

    assets = safe_count("assets")
    print(f"  Assets: {assets} (should be 0)")

    docs = safe_count("documents")
    print(f"  Documents: {docs} (should be 0)")

    convs = safe_count("conversations")
    print(f"  Conversations: {convs} (should be 0)")

    mappings = safe_count("semantic_mappings")
    print(f"  Semantic mappings: {mappings} (should be 0)")

    datasets = safe_count("datasets")
    print(f"  Datasets: {datasets} (should be 0)")

    ws = safe_count("workspaces")
    print(f"  Workspaces: {ws} (should be 1 — default)")

    # Local files
    base = Path(__file__).resolve().parent.parent
    kb_files = list((base / "data" / "knowledge_base").glob("*")) if (base / "data" / "knowledge_base").exists() else []
    print(f"  Knowledge base files: {len(kb_files)} (should be 0)")

    has_sqlite = (base / "data" / "warehouse.db").exists()
    print(f"  SQLite database: {'EXISTS' if has_sqlite else 'absent'} (should be absent)")

    cur.close()

    clean = (
        len(dynamic) == 0
        and (assets is None or assets == 0)
        and (docs is None or docs == 0)
        and (convs is None or convs == 0)
        and (mappings is None or mappings == 0)
        and (datasets is None or datasets == 0)
        and len(kb_files) == 0
        and not has_sqlite
        and (ws is None or ws <= 1)
    )
    print(f"\n  {'CLEAN' if clean else 'NEEDS ATTENTION'}")
    return clean


if __name__ == "__main__":
    print("QueryBridge — Complete Cleanup")
    print("=" * 50)

    print("\n1. Cleaning PostgreSQL...")
    conn = get_pg_conn()
    clean_postgresql(conn)

    print("\n2. Cleaning local files...")
    clean_local_files()

    print("\n3. Verifying...")
    clean = verify_clean(conn)

    conn.close()
    print(f"\nCleanup {'complete' if clean else 'completed with issues'}!")
