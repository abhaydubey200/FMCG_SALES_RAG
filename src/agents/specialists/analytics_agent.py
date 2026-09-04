"""
Analytics Agent — handles structured data analysis.

Responsibilities:
- Workspace-wide metric aggregation (totals, by-dimension, trends)
- Ranking / top-N
- Dimensional drill-down

Correctness note: in a multi-dataset workspace the agent aggregates ACROSS
all tables that map to the requested measure/dimension (e.g. revenue exists
in Dataset A + B + C). It never answers from a single arbitrary table.
"""
import logging
import time
from typing import Any, Dict, List

from src.agents.registry import BaseAgent, AgentMessage
from src.agents.tools import get_tool_registry

logger = logging.getLogger("agents.analytics")


class AnalyticsAgent(BaseAgent):
    agent_id = "analytics"
    name = "Analytics Agent"
    description = "Performs workspace-wide structured data analysis: aggregation, trends, rankings, comparisons"
    domain = "analytics"
    capabilities = [
        "aggregation", "trend_analysis", "comparison", "ranking",
        "segmentation", "time_series", "dimensional_drill_down",
    ]
    allowed_tools = [
        "sql_generate", "sql_validate", "sql_execute", "workspace_metric",
        "resolve_metric", "calculate_metric", "compare_periods",
        "inspect_schema", "generate_chart_spec",
    ]

    def can_handle(self, intent: Dict[str, Any]) -> float:
        query_type = intent.get("query_type", "")
        if query_type in ("analytical", "diagnostic"):
            return 0.9
        text = intent.get("text", "").lower()
        analytical_signals = [
            "total", "sum", "average", "max", "min", "count",
            "revenue", "sales", "trend", "compare", "rank", "top",
            "bottom", "growth", "decline", "by region", "by product",
            "monthly", "quarterly", "yearly", "how much", "how many",
        ]
        matches = sum(1 for s in analytical_signals if s in text)
        if matches >= 2:
            return 0.7
        if matches >= 1:
            return 0.4
        return 0.0

    def _compact_discover(self, workspace_id: str = "default") -> Dict[str, Any]:
        """Discover availability WITHOUT dumping internal table metadata into the answer.

        Returns: has_data, available_measures, available_dimensions, dynamic_kpis,
        and at most one dimensional breakdown (used to keep evidence small).
        """
        from src.agents.tools import get_tool_registry
        tools = get_tool_registry()
        result: Dict[str, Any] = {"has_data": False, "dynamic_kpis": [], "breakdowns": {}}
        try:
            data = tools.call("get_discoverable_data")
            result["has_data"] = bool(data.get("assets"))
            result["available_measures"] = list(data.get("available_measures", {}).keys())
            result["available_dimensions"] = list(data.get("available_dimensions", {}).keys())

            from src.analytics.dynamic_engine import (
                discover_available_data, workspace_total_revenue,
                workspace_total_quantity, workspace_total_spend,
            )
            kpis = []
            total_rev = workspace_total_revenue(workspace_id)
            if total_rev is not None:
                kpis.append({"id": "total_revenue", "label": "Total Revenue", "value": round(total_rev, 2), "format": "currency"})
            total_qty = workspace_total_quantity(workspace_id)
            if total_qty is not None:
                kpis.append({"id": "total_quantity", "label": "Total Units", "value": round(total_qty, 2), "format": "number"})
            total_spend = workspace_total_spend(workspace_id)
            if total_spend is not None:
                kpis.append({"id": "total_spend", "label": "Total Spend", "value": round(total_spend, 2), "format": "currency"})
            if kpis:
                result["dynamic_kpis"] = kpis

            # At most one breakdown, preferring the first available dimension
            available_dims = result["available_dimensions"]
            for dim in ("region", "category", "product"):
                if dim in available_dims:
                    rows = tools.call("workspace_metric", metric="revenue", dimension=dim, op="by_dimension", workspace_id=workspace_id)
                    if rows.get("data"):
                        result["breakdowns"][dim] = rows["data"]
                    break
        except Exception as e:
            logger.warning("Compact discover failed: %s", e)
            result["error"] = str(e)
        return result

    def execute(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        t0 = time.time()
        message.status = "running"
        tools = get_tool_registry()

        try:
            step = message.input_data.get("step", "metric")
            workspace_id = message.input_data.get("workspace_id", "default")
            result: Dict[str, Any] = {}

            if step == "discover":
                result = self._compact_discover(workspace_id)

            elif step == "metric":
                metric = message.input_data.get("metric", "")
                dimension = message.input_data.get("dimension", "") or ""
                op = message.input_data.get("op", "auto")
                limit = int(message.input_data.get("limit", 50) or 50)
                filter_value = (message.input_data.get("filter_value") or "").strip()
                exclude_value = (message.input_data.get("exclude_value") or "").strip()
                include_value = (message.input_data.get("include_value") or "").strip()
                result = tools.call(
                    "workspace_metric", metric=metric, dimension=dimension,
                    op=op, limit=limit, workspace_id=workspace_id,
                    exclude_value=exclude_value, include_value=include_value,
                )
                result["metric"] = metric
                if dimension:
                    result["dimension"] = dimension
                # Region/dimension value filter (e.g. "in the North region")
                if filter_value and op == "by_dimension" and result.get("data"):
                    fv = filter_value.lower()
                    filtered = [r for r in result["data"]
                                if str(r.get("dimension", "")).lower() == fv]
                    result["data"] = filtered
                    result["row_count"] = len(filtered)
                    result["filter_value"] = filter_value
                    if not filtered:
                        result["error"] = f"No data for {dimension} = {filter_value}"
                        result["available"] = False
                # Comparison display subset (e.g. "North vs South revenue")
                if include_value and op == "by_dimension" and result.get("data"):
                    keep = {v.strip().lower() for v in include_value.split(" and ")}
                    filtered = [r for r in result["data"]
                                if str(r.get("dimension", "")).lower() in keep]
                    result["data"] = filtered
                    result["row_count"] = len(filtered)
                    result["include_value"] = include_value
                    if not filtered:
                        result["error"] = f"No data for {dimension} in {include_value}"
                        result["available"] = False

            elif step == "trend":
                metric = message.input_data.get("metric", "revenue")
                result = tools.call("workspace_metric", metric=metric, dimension="month", op="trend", workspace_id=workspace_id)
                result["metric"] = metric

            elif step == "top":
                metric = message.input_data.get("metric", "revenue")
                dimension = message.input_data.get("dimension", "product")
                limit = int(message.input_data.get("limit", 10) or 10)
                result = tools.call("workspace_metric", metric=metric, dimension=dimension, op="by_dimension", limit=limit, workspace_id=workspace_id)
                result["metric"] = metric
                result["dimension"] = dimension
                result["is_top"] = True

            elif step == "sql":
                # Direct SQL generation + execution against a specific table (advanced/explicit use)
                gen = tools.call(
                    "sql_generate",
                    metric=message.input_data.get("metric", ""),
                    table=message.input_data.get("table", ""),
                    dimensions=message.input_data.get("dimensions"),
                    order_by=message.input_data.get("order_by", ""),
                    limit=message.input_data.get("limit", 100),
                )
                if gen.get("valid"):
                    exec_result = tools.call("sql_execute", sql=gen["sql"])
                    result = {**gen, **exec_result}
                else:
                    result = gen

            elif step == "schema":
                table = message.input_data.get("table", "")
                result = tools.call("inspect_schema", table=table)
            else:
                result = {"error": f"Unknown step: {step}"}

            message.output_data = result
            message.status = "completed"

        except Exception as e:
            logger.error("Analytics agent error: %s", e)
            message.status = "failed"
            message.error = str(e)
            self._error_count += 1

        self._execution_count += 1
        self._total_latency_ms += (time.time() - t0) * 1000
        return message


def create_agent() -> AnalyticsAgent:
    return AnalyticsAgent()
