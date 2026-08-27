"""
Visualization Tools — generate chart specs from query results.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agents.tools.viz")


def register_tools(registry):
    from src.agents.tools import ToolDef

    def generate_chart_spec(
        data: List[Dict] = None,
        chart_type: str = "auto",
        x_key: str = "",
        y_keys: Optional[List[str]] = None,
        title: str = "",
    ) -> Dict[str, Any]:
        """Generate a visualization spec from data rows."""
        if not data:
            return {"charts": [], "kpis": [], "tables": []}

        charts = []
        kpis = []
        tables = []
        y_keys = y_keys or []

        # Auto-detect chart type
        if chart_type == "auto":
            if len(data) == 1:
                chart_type = "kpi"
            elif x_key and len(data) <= 20:
                chart_type = "bar"
            elif x_key and any(
                any(month in str(row.get(x_key, "")).lower()
                    for month in ["2024", "2025", "2026", "jan", "feb", "mar", "apr", "may", "jun",
                                  "jul", "aug", "sep", "oct", "nov", "dec"])
                for row in data
            ):
                chart_type = "line"
            else:
                chart_type = "bar"

        if chart_type == "kpi":
            for row in data[:4]:
                for k, v in row.items():
                    if isinstance(v, (int, float)):
                        formatted = f"${v:,.0f}" if v > 1000 else str(v)
                        kpis.append({"label": k.replace("_", " ").title(), "value": formatted})
        elif chart_type in ("bar", "line"):
            if not y_keys:
                y_keys = [k for k in data[0].keys() if k != x_key and isinstance(data[0].get(k), (int, float))][:3]
            if not x_key and data:
                x_key = [k for k in data[0].keys() if not isinstance(data[0].get(k), (int, float))][0] if data[0] else ""
            charts.append({
                "type": chart_type,
                "title": title or f"Data Visualization",
                "data": data,
                "x_key": x_key,
                "y_keys": y_keys,
                "y_labels": [k.replace("_", " ").title() for k in y_keys],
                "colors": ["#4F46E5", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6"],
            })
        else:
            # Default: table
            if data:
                columns = [{"key": k, "header": k.replace("_", " ").title()} for k in data[0].keys()]
                tables.append({"title": title or "Results", "columns": columns, "rows": data})

        return {"charts": charts, "kpis": kpis, "tables": tables}

    registry.register(ToolDef(
        tool_id="generate_chart_spec", name="Chart Spec Generator",
        description="Generate visualization specs (KPI, bar, line, table) from data",
        category="visualization", fn=generate_chart_spec,
        input_schema={"data": "result rows", "chart_type": "auto|kpi|bar|line", "x_key": "x axis column"},
        output_schema="charts, kpis, tables",
    ))
