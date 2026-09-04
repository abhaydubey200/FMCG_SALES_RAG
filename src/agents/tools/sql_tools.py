"""
SQL Tools — deterministic SQL generation, validation, and execution.

All SQL passes through safety validation before execution.
No LLM-generated SQL is ever executed without validation.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("agents.tools.sql")

# SQL keywords that must NOT appear in analytical queries
_BLOCKED_KEYWORDS = {"DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE"}
Identifier = str  # for type hints


def _validate_identifier(name: str) -> bool:
    """Ensure identifier is safe — alphanumeric + underscores only."""
    return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name))


def _sanitize_identifier(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c == "_")
    if not safe or not safe[0].isalpha():
        safe = "col_" + safe
    return safe


def _validate_sql(sql: str) -> Tuple[bool, str]:
    """Validate SQL is safe for analytical execution."""
    upper = sql.upper()
    for kw in _BLOCKED_KEYWORDS:
        # Check for standalone keyword (not inside a string literal)
        pattern = r'\b' + kw + r'\b'
        # Simple heuristic: check if keyword appears outside quotes
        stripped = re.sub(r"'[^']*'", "", sql)  # remove single-quoted strings
        stripped = re.sub(r'"[^"]*"', "", stripped)  # remove double-quoted strings
        if re.search(pattern, stripped, re.IGNORECASE):
            return False, f"Blocked keyword: {kw}"
    if "SELECT" not in upper:
        return False, "Query must be a SELECT statement"
    return True, "OK"


def sql_generate(
    metric: str = "",
    dimensions: Optional[List[str]] = None,
    table: str = "",
    filters: Optional[Dict[str, str]] = None,
    order_by: str = "",
    limit: int = 100,
    date_column: str = "",
    date_range: Optional[Dict[str, str]] = None,
    group_by: Optional[List[str]] = None,
    aggregation: str = "SUM",
) -> Dict[str, Any]:
    """Generate a safe SQL query from semantic parameters."""
    cols = []
    if dimensions:
        cols.extend([_sanitize_identifier(d) for d in dimensions])
    metric_col = _sanitize_identifier(metric) if metric else "*"
    if aggregation and metric and metric != "*":
        # alias derives from the SANITIZED identifier — raw user text never
        # reaches SQL (prevents alias breakout like `x" ; DROP TABLE ...`)
        select_clause = f"{aggregation}(\"{metric_col}\") AS \"{metric_col}_total\""
    else:
        select_clause = f"\"{metric_col}\"" if metric else "*"
    if cols:
        select_clause = ", ".join([f'"{c}"' for c in cols]) + ", " + select_clause

    table_safe = _sanitize_identifier(table) if table else ""
    if not table_safe:
        return {"sql": "", "error": "No table specified", "valid": False}

    where_clauses = []
    if filters:
        for k, v in filters.items():
            k_safe = _sanitize_identifier(k)
            # escape single quotes so filter VALUES cannot break out of the
            # string literal (identifier-level injection is blocked above)
            v_escaped = str(v).replace("'", "''")
            where_clauses.append(f'"{k_safe}" = \'{v_escaped}\'')
    if date_range and date_column:
        dc = _sanitize_identifier(date_column)
        if "start" in date_range:
            where_clauses.append(f'"{dc}" >= \'{date_range["start"]}\'')
        if "end" in date_range:
            where_clauses.append(f'"{dc}" <= \'{date_range["end"]}\'')

    sql = f'SELECT {select_clause} FROM "{table_safe}"'
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    group_cols = group_by or cols
    if group_cols:
        sql += " GROUP BY " + ", ".join([f'"{_sanitize_identifier(g)}"' for g in group_cols])

    if order_by:
        sql += f" ORDER BY {_sanitize_identifier(order_by)} DESC"
    if limit:
        sql += f" LIMIT {min(limit, 10000)}"

    valid, msg = _validate_sql(sql)
    return {"sql": sql, "valid": valid, "validation_message": msg}


def sql_validate(sql: str) -> Dict[str, Any]:
    """Validate SQL for safety."""
    valid, msg = _validate_sql(sql)
    return {"valid": valid, "message": msg, "sql": sql}


def sql_execute(sql: str, workspace_id: str = "default") -> Dict[str, Any]:
    """Execute validated SQL and return results."""
    valid, msg = _validate_sql(sql)
    if not valid:
        return {"error": msg, "rows": [], "columns": [], "row_count": 0}

    # Check cache first
    from src.llm.query_cache import get_cached_sql, cache_sql_result
    cached = get_cached_sql(sql)
    if cached is not None:
        return cached

    try:
        from src.analytics.dynamic_engine import _get_pg_connection
        conn = _get_pg_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description] if cur.description else []
            result_rows = []
            for row in rows:
                if hasattr(row, "_asdict"):
                    result_rows.append(dict(row._asdict()))
                elif hasattr(row, "keys"):
                    result_rows.append(dict(zip(columns, row)))
                else:
                    result_rows.append(dict(zip(columns, row)))
            result = {
                "rows": result_rows,
                "columns": columns,
                "row_count": len(result_rows),
                "sql": sql,
            }
            cache_sql_result(sql, result)
            return result
        finally:
            conn.close()
    except Exception as e:
        logger.error("SQL execution failed: %s", e)
        return {"error": str(e), "rows": [], "columns": [], "row_count": 0, "sql": sql}


def register_tools(registry):
    from src.agents.tools import ToolDef

    registry.register(ToolDef(
        tool_id="sql_generate", name="SQL Generator",
        description="Generate a safe SELECT query from semantic parameters",
        category="analytics", fn=sql_generate,
        input_schema={"metric": "column to aggregate", "table": "table name", "dimensions": "group-by columns"},
        output_schema="sql, valid, validation_message",
    ))
    registry.register(ToolDef(
        tool_id="sql_validate", name="SQL Validator",
        description="Validate SQL for safety (no destructive operations)",
        category="analytics", fn=sql_validate,
        input_schema={"sql": "SQL to validate"}, output_schema="valid, message",
    ))
    registry.register(ToolDef(
        tool_id="sql_execute", name="SQL Executor",
        description="Execute validated SQL and return results",
        category="analytics", fn=sql_execute,
        input_schema={"sql": "validated SQL"}, output_schema="rows, columns, row_count",
    ))
