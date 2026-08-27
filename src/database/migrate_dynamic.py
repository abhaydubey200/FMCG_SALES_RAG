"""
Database migration script — applies new schema additions to existing databases.

Run this after updating schema.sql to add the dynamic data tables.
Safe to run multiple times (uses IF NOT EXISTS and ON CONFLICT).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src import config


def migrate():
    """Apply schema migration."""
    if not config.USE_POSTGRESQL:
        print("PostgreSQL not configured. Migration only applies to PostgreSQL databases.")
        return

    import psycopg2
    conn = psycopg2.connect(config.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    migrations = [
        # 1. Workspaces table
        """
        CREATE TABLE IF NOT EXISTS workspaces (
            workspace_id TEXT PRIMARY KEY DEFAULT 'default',
            name TEXT NOT NULL DEFAULT 'Default Workspace',
            created_at TIMESTAMP DEFAULT NOW()
        );
        """,
        "INSERT INTO workspaces (workspace_id, name) VALUES ('default', 'Default Workspace') ON CONFLICT (workspace_id) DO NOTHING;",

        # 2. Assets table (dynamic data catalog)
        """
        CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            workspace_id TEXT DEFAULT 'default',
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            source_type TEXT NOT NULL,
            status TEXT DEFAULT 'processing',
            description TEXT DEFAULT '',
            tags JSONB DEFAULT '[]',
            domain TEXT DEFAULT 'unknown',
            schema JSONB DEFAULT '{}',
            row_count INTEGER DEFAULT 0,
            column_count INTEGER DEFAULT 0,
            size_bytes BIGINT DEFAULT 0,
            table_name TEXT,
            semantic_status TEXT DEFAULT 'pending',
            processing_status TEXT DEFAULT 'pending',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_assets_workspace ON assets(workspace_id);",
        "CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type);",
        "CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);",

        # 3. Update datasets table to add asset_id, workspace_id, version, is_current
        """
        ALTER TABLE datasets ADD COLUMN IF NOT EXISTS asset_id TEXT;
        ALTER TABLE datasets ADD COLUMN IF NOT EXISTS workspace_id TEXT DEFAULT 'default';
        ALTER TABLE datasets ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;
        ALTER TABLE datasets ADD COLUMN IF NOT EXISTS is_current BOOLEAN DEFAULT TRUE;
        """,

        # 4. Update documents table to add workspace_id
        """
        ALTER TABLE documents ADD COLUMN IF NOT EXISTS workspace_id TEXT DEFAULT 'default';
        """,

        # 5. Semantic mappings table
        """
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
        """,
        "CREATE INDEX IF NOT EXISTS idx_sm_workspace ON semantic_mappings(workspace_id);",
        "CREATE INDEX IF NOT EXISTS idx_sm_concept ON semantic_mappings(canonical_concept);",
        "CREATE INDEX IF NOT EXISTS idx_sm_table ON semantic_mappings(table_name);",

        # 6. Dataset relationships table
        """
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
        """,
    ]

    print("Applying migrations...")
    for i, sql in enumerate(migrations):
        try:
            cur.execute(sql)
            print(f"  Migration {i+1}/{len(migrations)}: OK")
        except Exception as e:
            # Some migrations may fail if column already exists — that's fine
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"  Migration {i+1}/{len(migrations)}: Skipped (already applied)")
            else:
                print(f"  Migration {i+1}/{len(migrations)}: Warning - {e}")

    # Verify
    print("\n=== VERIFICATION ===")
    for table in ["workspaces", "assets", "semantic_mappings", "dataset_relationships"]:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table}: {count} rows")
        except Exception as e:
            print(f"  {table}: NOT FOUND ({e})")

    # Check for uploaded data tables
    cur.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name LIKE 'data_%' OR table_name LIKE 'uploaded_%'
    """)
    dynamic_tables = cur.fetchall()
    if dynamic_tables:
        print(f"\n  Dynamic tables found: {', '.join(t[0] for t in dynamic_tables)}")

    conn.close()
    print("\nMigration complete!")


if __name__ == "__main__":
    migrate()
