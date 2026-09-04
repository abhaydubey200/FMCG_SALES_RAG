"""
Schema Tools — inspect workspace schema, profile datasets, detect relationships.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agents.tools.schema")


def register_tools(registry):
    from src.agents.tools import ToolDef

    def inspect_schema(table: str = "") -> Dict[str, Any]:
        """Inspect the schema of a workspace table."""
        try:
            from src.analytics.dynamic_engine import _get_pg_connection, _sanitize_sql_identifier
            if not table:
                return {"error": "No table specified", "columns": []}
            safe = _sanitize_sql_identifier(table)
            conn = _get_pg_connection()
            try:
                cur = conn.cursor()
                cur.execute(f'SELECT * FROM "{safe}" LIMIT 0')
                columns = []
                for desc in cur.description:
                    columns.append({
                        "name": desc[0],
                        "type": str(desc[1]) if desc[1] else "unknown",
                    })
                # Get row count
                cur.execute(f'SELECT COUNT(*) FROM "{safe}"')
                row_count = cur.fetchone()[0]
                return {"table": safe, "columns": columns, "row_count": row_count}
            finally:
                conn.close()
        except Exception as e:
            return {"error": str(e), "columns": []}

    def profile_dataset(table: str = "", sample_size: int = 100) -> Dict[str, Any]:
        """Profile a dataset — null rates, unique counts, min/max for numeric, samples."""
        try:
            from src.analytics.dynamic_engine import _get_pg_connection, _sanitize_sql_identifier
            if not table:
                return {"error": "No table specified"}
            safe = _sanitize_sql_identifier(table)
            conn = _get_pg_connection()
            try:
                cur = conn.cursor()
                cur.execute(f'SELECT * FROM "{safe}" LIMIT 0')
                columns = [desc[0] for desc in cur.description]
                cur.execute(f'SELECT COUNT(*) FROM "{safe}"')
                total = cur.fetchone()[0]

                profile = {"table": safe, "total_rows": total, "columns": {}}
                for col in columns:
                    col_safe = f'"{col}"'
                    try:
                        cur.execute(f'SELECT COUNT(*) FROM "{safe}" WHERE {col_safe} IS NULL')
                        nulls = cur.fetchone()[0]
                        cur.execute(f'SELECT COUNT(DISTINCT {col_safe}) FROM "{safe}"')
                        unique = cur.fetchone()[0]
                        cur.execute(f'SELECT MIN(LENGTH(CAST({col_safe} AS TEXT))) FROM "{safe}" WHERE {col_safe} IS NOT NULL')
                        min_len = cur.fetchone()[0]
                        cur.execute(f'SELECT MAX(LENGTH(CAST({col_safe} AS TEXT))) FROM "{safe}" WHERE {col_safe} IS NOT NULL')
                        max_len = cur.fetchone()[0]
                        profile["columns"][col] = {
                            "null_count": nulls,
                            "null_pct": round(100 * nulls / total, 1) if total > 0 else 0,
                            "unique_count": unique,
                            "min_length": min_len,
                            "max_length": max_len,
                        }
                    except Exception as ex:
                        profile["columns"][col] = {"error": str(ex)}
                return profile
            finally:
                conn.close()
        except Exception as e:
            return {"error": str(e)}

    def list_workspace_assets(workspace_id: str = "default") -> Dict[str, Any]:
        """List all assets in the current workspace."""
        try:
            from src.analytics.dynamic_engine import list_datasets
            from src.rag.pipeline import get_pipeline
            from src.ingestion.document_loader import _chunk_workspace_id
            assets = {"structured": [], "unstructured": []}
            # Structured
            try:
                ds_list = list_datasets(workspace_id)
                assets["structured"] = ds_list
            except Exception:
                pass
            # Unstructured — only chunks owned by this workspace
            try:
                pipeline = get_pipeline()
                docs = {}
                for c in pipeline.vector_store.chunks:
                    if _chunk_workspace_id(c) != workspace_id:
                        continue
                    if c.document_id not in docs:
                        docs[c.document_id] = {
                            "document_id": c.document_id,
                            "document_name": c.document_name,
                            "chunk_count": 0,
                        }
                    docs[c.document_id]["chunk_count"] += 1
                assets["unstructured"] = list(docs.values())
            except Exception:
                pass
            return assets
        except Exception as e:
            return {"error": str(e), "structured": [], "unstructured": []}

    def get_discoverable_data(workspace_id: str = "default") -> Dict[str, Any]:
        """Discover available measures, dimensions, and entities from workspace data."""
        try:
            from src.analytics.dynamic_engine import discover_available_data
            return discover_available_data(workspace_id)
        except Exception as e:
            return {"error": str(e), "available_measures": {}, "available_dimensions": {}}

    def dimension_values(dimension: str = "", workspace_id: str = "default") -> Dict[str, Any]:
        """List the actual distinct values for a dimension in workspace data."""
        try:
            from src.analytics.dynamic_engine import workspace_dimension_values
            if not dimension:
                return {"dimension": dimension, "values": []}
            return {"dimension": dimension, "values": workspace_dimension_values(dimension, workspace_id)}
        except Exception as e:
            return {"dimension": dimension, "values": [], "error": str(e)}

    registry.register(ToolDef(
        tool_id="dimension_values", name="Dimension Value Discovery",
        description="List actual distinct values of a dimension (e.g. real region names) from workspace data",
        category="data", fn=dimension_values,
        input_schema={"dimension": "dimension concept name"}, output_schema="values: list of distinct values",
    ))
    registry.register(ToolDef(
        tool_id="inspect_schema", name="Schema Inspector",
        description="Inspect column names and types of a workspace table",
        category="data", fn=inspect_schema,
        input_schema={"table": "table name"}, output_schema="table, columns, row_count",
    ))
    registry.register(ToolDef(
        tool_id="profile_dataset", name="Dataset Profiler",
        description="Profile a dataset: null rates, unique counts, value lengths",
        category="data", fn=profile_dataset,
        input_schema={"table": "table name"}, output_schema="total_rows, columns profile",
    ))
    registry.register(ToolDef(
        tool_id="list_workspace_assets", name="Workspace Asset Lister",
        description="List all structured and unstructured assets in the workspace",
        category="workspace", fn=list_workspace_assets,
        input_schema={}, output_schema="structured, unstructured",
    ))
    registry.register(ToolDef(
        tool_id="get_discoverable_data", name="Data Discovery",
        description="Discover available measures, dimensions, and entities from semantic layer",
        category="data", fn=get_discoverable_data,
        input_schema={}, output_schema="available_measures, available_dimensions",
    ))
