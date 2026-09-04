"""
Metrics Tools — resolve business concepts to physical columns, compute metrics.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agents.tools.metrics")


def register_tools(registry):
    from src.agents.tools import ToolDef

    def resolve_metric(concept: str = "", table: str = "") -> Dict[str, Any]:
        """Resolve a business concept (e.g., 'revenue') to physical column + table."""
        try:
            from src.analytics.dynamic_engine import discover_available_data
            data = discover_available_data()
            concept_lower = concept.lower().replace(" ", "_").replace("-", "_")

            # Try to find the concept in measures
            for measure_name, entries in data.get("available_measures", {}).items():
                if concept_lower in measure_name.lower() or measure_name.lower() in concept_lower:
                    if entries:
                        return {
                            "resolved": True,
                            "business_concept": measure_name,
                            "physical_column": entries[0]["column"],
                            "table": entries[0]["table"],
                            "all_matches": entries,
                        }

            # Try dimensions
            for dim_name, entries in data.get("available_dimensions", {}).items():
                if concept_lower in dim_name.lower() or dim_name.lower() in concept_lower:
                    if entries:
                        return {
                            "resolved": True,
                            "business_concept": dim_name,
                            "physical_column": entries[0]["column"],
                            "table": entries[0]["table"],
                            "type": "dimension",
                            "all_matches": entries,
                        }

            return {
                "resolved": False,
                "concept": concept,
                "error": f"Could not resolve '{concept}' to a physical column",
                "available_measures": list(data.get("available_measures", {}).keys()),
                "available_dimensions": list(data.get("available_dimensions", {}).keys()),
            }
        except Exception as e:
            return {"resolved": False, "error": str(e)}

    def calculate_metric(
        metric: str = "",
        table: str = "",
        dimensions: Optional[List[str]] = None,
        filters: Optional[Dict[str, str]] = None,
        order_by: str = "",
        limit: int = 100,
        date_column: str = "",
        date_range: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Calculate a metric by resolving it and executing SQL."""
        # Resolve
        resolution = resolve_metric(concept=metric, table=table)
        if not resolution.get("resolved"):
            return {"error": resolution.get("error", "Could not resolve metric"), "data": []}

        physical_col = resolution["physical_column"]
        resolved_table = table or resolution.get("table", "")

        # Generate SQL
        gen_result = registry.call(
            "sql_generate",
            metric=physical_col,
            table=resolved_table,
            dimensions=dimensions,
            filters=filters,
            order_by=order_by,
            limit=limit,
            date_column=date_column,
            date_range=date_range,
            aggregation="SUM" if not dimensions else "SUM",
        )

        if not gen_result.get("valid"):
            return {"error": gen_result.get("validation_message", "Invalid SQL"), "data": []}

        # Execute
        exec_result = registry.call("sql_execute", sql=gen_result["sql"])

        return {
            "metric": metric,
            "resolved_to": physical_col,
            "table": resolved_table,
            "sql": gen_result["sql"],
            "data": exec_result.get("rows", []),
            "columns": exec_result.get("columns", []),
            "row_count": exec_result.get("row_count", 0),
            "error": exec_result.get("error"),
        }

    def workspace_metric(
        metric: str = "revenue",
        dimension: str = "",
        op: str = "auto",
        limit: int = 50,
        workspace_id: str = "default",
        exclude_value: str = "",
        include_value: str = "",
    ) -> Dict[str, Any]:
        """Aggregate a canonical measure across ALL workspace tables (deterministic).

        op: "total" (single aggregate) | "by_dimension" | "trend" | "excluding" | "only" | "auto"
        "excluding" aggregates the rows that are NOT `exclude_value` within
        `dimension` (e.g. revenue excluding North → South + West); "only"
        aggregates the rows that ARE `include_value` (e.g. North + West). Both
        return a single labeled total and never compute from subtraction labels.
        "auto" chooses: by_dimension when a dimension is given, trend when the
        dimension is a time grain (month/quarter/year/date), otherwise total.
        Uses the dynamic engine's workspace-wide aggregation so multi-dataset
        workspaces are summed/weighted correctly (never a single table).
        """
        try:
            from src.analytics.dynamic_engine import (
                workspace_metric_total, workspace_metric_by_dimension, workspace_metric_trend,
            )
            time_grain = dimension in ("month", "quarter", "year", "date")
            if op == "auto":
                if dimension and time_grain:
                    op = "trend"
                elif dimension:
                    op = "by_dimension"
                else:
                    op = "total"

            if op in ("excluding", "only"):
                raw_value = exclude_value if op == "excluding" else include_value
                if not dimension or not raw_value:
                    return {"metric": metric, "op": op,
                            "error": (f"{op} requires a dimension and a "
                                      f"{'value to exclude' if op == 'excluding' else 'value to keep'}"),
                            "data": [], "available": False}
                rows = workspace_metric_by_dimension(metric, dimension, workspace_id)
                if not rows:
                    return {"metric": metric, "dimension": dimension, "op": op,
                            "error": f"No data to compute '{metric} {op} {raw_value}' from",
                            "data": [], "available": False}
                sel = {v.strip().lower() for v in raw_value.lower().split(" and ")}
                is_rate = (metric in ("discount", "margin", "price", "rating", "roas",
                                      "discount_pct", "margin_pct", "discount_rate", "avg_rating")
                           or any(k in metric for k in ("discount", "margin", "rating", "roas", "price")))
                if is_rate:
                    return {"metric": metric, "dimension": dimension, "op": op,
                            "error": (f"'{metric}' is a rate/percentage measure — {op} is only "
                                      "supported for additive measures (summed across rows)."),
                            "data": [], "available": False}
                if op == "excluding":
                    selected = [r for r in rows
                                if str(r.get("dimension", "")).lower() not in sel]
                    join_word = "excluding"
                else:
                    selected = [r for r in rows
                                if str(r.get("dimension", "")).lower() in sel]
                    join_word = "in"
                value = round(sum(float(r.get(metric, 0) or 0) for r in selected), 2)
                names = [str(r.get("dimension")) for r in selected]
                suffix = f" ({' + '.join(names)})" if names else ""
                label = f"{metric.capitalize()} {join_word} {raw_value}{suffix}"
                return {"metric": metric, "dimension": dimension, "op": "total",
                        "value": value, "available": True,
                        "exclude_value": exclude_value, "include_value": include_value,
                        "included": names, "label": label,
                        "data": selected, "row_count": 1, "format": "currency" if metric in ("revenue", "spend", "profit", "cost") else "number",
                        "sql": f"workspace aggregate {metric} GROUP BY {dimension} {join_word} {raw_value}"}

            if op == "total":
                value = workspace_metric_total(metric, workspace_id)
                if value is None:
                    return {"metric": metric, "error": f"Metric '{metric}' not found in workspace data", "available": False, "data": []}
                return {"metric": metric, "op": "total", "value": value, "available": True,
                        "data": [{metric: value}], "format": "currency" if metric in ("revenue", "spend", "profit", "cost") else "number",
                        "row_count": 1, "sql": f"workspace aggregate SUM/AVG({metric})"}
            if op == "by_dimension":
                rows = workspace_metric_by_dimension(metric, dimension, workspace_id, limit=limit)
                if not rows:
                    return {"metric": metric, "dimension": dimension, "error": "No matching data", "data": [], "available": False}
                return {"metric": metric, "dimension": dimension, "op": "by_dimension",
                        "data": rows, "row_count": len(rows), "available": True,
                        "sql": f"workspace aggregate {metric} GROUP BY {dimension}"}
            if op == "trend":
                rows = workspace_metric_trend(metric, workspace_id)
                if not rows:
                    return {"metric": metric, "op": "trend", "error": "No time-series data", "data": [], "available": False}
                return {"metric": metric, "op": "trend", "data": rows, "row_count": len(rows),
                        "available": True, "sql": f"workspace aggregate {metric} by month"}
            return {"metric": metric, "error": f"Unknown op {op}", "data": []}
        except Exception as e:
            logger.error("workspace_metric failed: %s", e)
            return {"metric": metric, "error": str(e), "data": [], "available": False}

    def get_available_kpis() -> Dict[str, Any]:
        """Get KPIs that can be calculated from current workspace data."""
        try:
            from src.analytics.dynamic_engine import get_available_kpis
            return get_available_kpis()
        except Exception as e:
            return {"kpis": [], "error": str(e)}

    def compare_periods(
        metric: str = "",
        table: str = "",
        date_column: str = "",
        period: str = "month",
    ) -> Dict[str, Any]:
        """Compare metric across time periods."""
        resolution = resolve_metric(concept=metric, table=table)
        if not resolution.get("resolved"):
            return {"error": resolution.get("error"), "comparisons": []}

        physical_col = resolution["physical_column"]
        resolved_table = table or resolution.get("table", "")
        dc = date_column or ""
        if not dc:
            # Try to find a date column
            for dim_name, entries in resolution.get("all_matches", []):
                pass
            data_disc = resolve_metric(concept="date", table=resolved_table)
            if data_disc.get("resolved"):
                dc = data_disc["physical_column"]

        if not dc:
            return {"error": "No date column found for period comparison", "comparisons": []}

        try:
            from src.analytics.dynamic_engine import _get_pg_connection, _sanitize_sql_identifier
            safe_table = _sanitize_sql_identifier(resolved_table)
            safe_col = _sanitize_sql_identifier(physical_col)
            safe_dc = _sanitize_sql_identifier(dc)

            conn = _get_pg_connection()
            try:
                cur = conn.cursor()
                # Monthly aggregation
                if period == "month":
                    sql = f"""SELECT DATE_TRUNC('month', "{safe_dc}") AS period,
                                     SUM("{safe_col}") AS value
                              FROM "{safe_table}"
                              GROUP BY period ORDER BY period"""
                elif period == "quarter":
                    sql = f"""SELECT DATE_TRUNC('quarter', "{safe_dc}") AS period,
                                     SUM("{safe_col}") AS value
                              FROM "{safe_table}"
                              GROUP BY period ORDER BY period"""
                else:
                    sql = f"""SELECT DATE_TRUNC('year', "{safe_dc}") AS period,
                                     SUM("{safe_col}") AS value
                              FROM "{safe_table}"
                              GROUP BY period ORDER BY period"""

                cur.execute(sql)
                rows = cur.fetchall()
                comparisons = []
                prev_value = None
                for row in rows:
                    period_val = str(row[0]) if row[0] else ""
                    value = float(row[1]) if row[1] else 0
                    growth_pct = None
                    if prev_value and prev_value > 0:
                        growth_pct = round((value - prev_value) / prev_value * 100, 1)
                    comparisons.append({
                        "period": period_val,
                        "value": value,
                        "growth_pct": growth_pct,
                    })
                    prev_value = value
                return {"comparisons": comparisons, "metric": metric, "period": period}
            finally:
                conn.close()
        except Exception as e:
            return {"error": str(e), "comparisons": []}

    registry.register(ToolDef(
        tool_id="resolve_metric", name="Metric Resolver",
        description="Resolve a business concept to its physical column and table",
        category="analytics", fn=resolve_metric,
        input_schema={"concept": "business concept name", "table": "optional table hint"},
        output_schema="resolved, physical_column, table",
    ))
    registry.register(ToolDef(
        tool_id="workspace_metric", name="Workspace Metric Aggregator",
        description="Aggregate a canonical measure across ALL workspace tables (totals, by-dimension, trend)",
        category="analytics", fn=workspace_metric,
        input_schema={"metric": "canonical concept", "dimension": "dimension concept", "op": "total/by_dimension/trend/auto"},
        output_schema="value or data rows with metric values",
    ))
    registry.register(ToolDef(
        tool_id="calculate_metric", name="Metric Calculator",
        description="Calculate a business metric from workspace data",
        category="analytics", fn=calculate_metric,
        input_schema={"metric": "concept", "table": "table", "dimensions": "group-by"},
        output_schema="data rows with metric values",
    ))
    registry.register(ToolDef(
        tool_id="get_available_kpis", name="KPI Discovery",
        description="Discover which KPIs can be calculated from current data",
        category="analytics", fn=get_available_kpis,
        input_schema={}, output_schema="list of available KPIs",
    ))
    registry.register(ToolDef(
        tool_id="compare_periods", name="Period Comparison",
        description="Compare a metric across time periods (growth/decline)",
        category="analytics", fn=compare_periods,
        input_schema={"metric": "concept", "date_column": "date field", "period": "month/quarter/year"},
        output_schema="period, value, growth_pct",
    ))
