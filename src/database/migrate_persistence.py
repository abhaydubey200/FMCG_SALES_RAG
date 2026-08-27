"""
Database migration — adds execution persistence tables.
Safe to run multiple times.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src import config


def migrate():
    if not config.USE_POSTGRESQL:
        print("PostgreSQL not configured. Skipping persistence migration.")
        return

    import psycopg2
    conn = psycopg2.connect(config.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    migrations = [
        # Execution Plans
        """
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
        """,
        "CREATE INDEX IF NOT EXISTS idx_ep_trace ON execution_plans(trace_id);",
        "CREATE INDEX IF NOT EXISTS idx_ep_workspace ON execution_plans(workspace_id);",
        "CREATE INDEX IF NOT EXISTS idx_ep_conv ON execution_plans(conversation_id);",

        # Execution Steps
        """
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
        """,
        "CREATE INDEX IF NOT EXISTS idx_es_plan ON execution_steps(plan_id);",

        # Agent Executions
        """
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
        """,
        "CREATE INDEX IF NOT EXISTS idx_ae_trace ON agent_executions(trace_id);",

        # Evidence Records
        """
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
        """,
        "CREATE INDEX IF NOT EXISTS idx_er_trace ON evidence_records(trace_id);",

        # Verification Results
        """
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
        """,
        "CREATE INDEX IF NOT EXISTS idx_vr_trace ON verification_results(trace_id);",
    ]

    print("Applying persistence migrations...")
    for i, sql in enumerate(migrations):
        try:
            cur.execute(sql)
            print(f"  Migration {i+1}/{len(migrations)}: OK")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"  Migration {i+1}/{len(migrations)}: Skipped")
            else:
                print(f"  Migration {i+1}/{len(migrations)}: Warning - {e}")

    print("\nPersistence migration complete!")


if __name__ == "__main__":
    migrate()
