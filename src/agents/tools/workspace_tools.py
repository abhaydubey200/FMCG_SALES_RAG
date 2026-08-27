"""
Workspace Tools — manage workspace assets, inspect data, run quality checks.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agents.tools.workspace")


def register_tools(registry):
    from src.agents.tools import ToolDef

    def get_workspace_summary() -> Dict[str, Any]:
        """Get a summary of the current workspace state."""
        try:
            from src.analytics.dynamic_engine import (
                has_workspace_data, get_workspace_tables, workspace_total_revenue,
                workspace_total_quantity, workspace_total_spend, workspace_row_count,
                discover_available_data,
            )
            has_data = has_workspace_data()
            if not has_data:
                return {"has_data": False, "tables": [], "summary": "No data in workspace"}

            tables = get_workspace_tables()
            total_revenue = workspace_total_revenue() or 0
            total_units = workspace_total_quantity() or 0
            total_spend = workspace_total_spend() or 0
            total_rows = workspace_row_count()

            data_disc = discover_available_data()
            measures = list(data_disc.get("available_measures", {}).keys())
            dimensions = list(data_disc.get("available_dimensions", {}).keys())

            return {
                "has_data": True,
                "tables": tables,
                "total_rows": total_rows,
                "total_revenue": round(total_revenue, 2),
                "total_units": total_units,
                "total_spend": round(total_spend, 2),
                "available_measures": measures,
                "available_dimensions": dimensions,
            }
        except Exception as e:
            return {"has_data": False, "error": str(e)}

    def get_data_quality(table: str = "") -> Dict[str, Any]:
        """Run data quality checks on a table."""
        try:
            from src.analytics.dynamic_engine import _get_pg_connection, _sanitize_sql_identifier
            if not table:
                return {"error": "No table specified"}
            safe = _sanitize_sql_identifier(table)
            conn = _get_pg_connection()
            try:
                cur = conn.cursor()
                cur.execute(f'SELECT COUNT(*) FROM "{safe}"')
                total = cur.fetchone()[0]
                cur.execute(f'SELECT * FROM "{safe}" LIMIT 0')
                columns = [desc[0] for desc in cur.description]

                checks = []
                for col in columns:
                    cur.execute(f'SELECT COUNT(*) FROM "{safe}" WHERE "{col}" IS NULL OR "{col}" = \'\')')
                    nulls = cur.fetchone()[0]
                    pct = round(100 * (total - nulls) / total, 1) if total > 0 else 100
                    checks.append({
                        "column": col,
                        "null_count": nulls,
                        "completeness_pct": pct,
                        "status": "pass" if pct >= 90 else "warn",
                    })
                return {"table": safe, "total_rows": total, "checks": checks}
            finally:
                conn.close()
        except Exception as e:
            return {"error": str(e)}

    registry.register(ToolDef(
        tool_id="get_workspace_summary", name="Workspace Summary",
        description="Get overview of workspace: tables, row counts, available measures/dimensions",
        category="workspace", fn=get_workspace_summary,
        input_schema={}, output_schema="has_data, tables, measures, dimensions",
    ))
    registry.register(ToolDef(
        tool_id="get_data_quality", name="Data Quality Checker",
        description="Run data quality checks on a specific workspace table",
        category="workspace", fn=get_data_quality,
        input_schema={"table": "table name"}, output_schema="checks with completeness scores",
    ))
