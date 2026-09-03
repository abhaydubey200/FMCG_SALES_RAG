"""
Analytics Agent — handles structured data analysis.

Responsibilities:
- KPI calculation
- Aggregation, ranking, comparison
- Trend analysis, time-series
- Dimensional drill-down
"""
import logging
from typing import Any, Dict, List

from src.agents.registry import BaseAgent, AgentMessage
from src.agents.tools import get_tool_registry

logger = logging.getLogger("agents.analytics")


class AnalyticsAgent(BaseAgent):
    agent_id = "analytics"
    name = "Analytics Agent"
    description = "Performs structured data analysis: aggregation, trends, rankings, comparisons"
    domain = "analytics"
    capabilities = [
        "aggregation", "trend_analysis", "comparison", "ranking",
        "segmentation", "time_series", "dimensional_drill_down",
    ]
    allowed_tools = [
        "sql_generate", "sql_validate", "sql_execute",
        "resolve_metric", "calculate_metric", "compare_periods",
        "inspect_schema", "generate_chart_spec",
    ]

    def can_handle(self, intent: Dict[str, Any]) -> float:
        query_type = intent.get("query_type", "")
        if query_type in ("analytical", "diagnostic"):
            return 0.9
        # Check for analytical keywords
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

    def execute(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Execute analytics task based on the plan step."""
        import time
        t0 = time.time()
        message.status = "running"
        tools = get_tool_registry()

        try:
            step = message.input_data.get("step", "calculate")
            result = {}

            if step == "discover":
                # Discover available data AND compute actual metric values
                result = tools.call("get_discoverable_data")
                # Also compute KPIs so the response contains real numbers
                try:
                    from src.analytics.dynamic_engine import (
                        discover_available_data, workspace_total_revenue,
                        workspace_total_quantity, workspace_total_spend,
                    )
                    data = discover_available_data()
                    kpis = []
                    total_rev = workspace_total_revenue()
                    if total_rev is not None:
                        kpis.append({"id": "total_revenue", "label": "Total Revenue", "value": round(total_rev, 2), "format": "currency"})
                    total_qty = workspace_total_quantity()
                    if total_qty is not None:
                        kpis.append({"id": "total_quantity", "label": "Total Units", "value": round(total_qty, 2), "format": "number"})
                    total_spend = workspace_total_spend()
                    if total_spend is not None:
                        kpis.append({"id": "total_spend", "label": "Total Spend", "value": round(total_spend, 2), "format": "currency"})
                    result["dynamic_kpis"] = kpis
                    # Also compute breakdowns for revenue by available dimensions
                    from src.analytics.dynamic_engine import workspace_revenue_by_dimension
                    for dim in ["region", "category", "product"]:
                        breakdown = workspace_revenue_by_dimension(dim)
                        if breakdown:
                            result.setdefault("breakdowns", {})[dim] = breakdown
                            break
                except Exception as e:
                    logger.warning("Failed to compute KPIs during discover: %s", e)
            elif step == "calculate":
                # Calculate a metric
                metric = message.input_data.get("metric", "")
                dimensions = message.input_data.get("dimensions")
                table = message.input_data.get("table", "")
                result = tools.call(
                    "calculate_metric",
                    metric=metric, table=table, dimensions=dimensions,
                )
            elif step == "trend":
                # Compare across time periods
                metric = message.input_data.get("metric", "")
                date_column = message.input_data.get("date_column", "")
                period = message.input_data.get("period", "month")
                result = tools.call(
                    "compare_periods",
                    metric=metric, date_column=date_column, period=period,
                )
            elif step == "sql":
                # Direct SQL generation + execution
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
