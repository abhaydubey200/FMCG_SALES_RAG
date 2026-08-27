"""
Investigation Agent — dynamic root-cause investigation.

Inspects available dimensions dynamically, does NOT use a hardcoded tree.
"""
import logging
from typing import Any, Dict, List

from src.agents.registry import BaseAgent, AgentMessage
from src.agents.tools import get_tool_registry

logger = logging.getLogger("agents.investigation")


class InvestigationAgent(BaseAgent):
    agent_id = "investigation"
    name = "Investigation Agent"
    description = "Dynamic root-cause analysis and dimensional drill-down"
    domain = "investigation"
    capabilities = [
        "root_cause_analysis", "dimensional_drill_down", "anomaly_detection",
        "trend_investigation", "segmentation_analysis",
    ]
    allowed_tools = [
        "resolve_metric", "calculate_metric", "sql_generate", "sql_execute",
        "compare_periods", "get_discoverable_data", "generate_chart_spec",
        "inspect_schema",
    ]

    def can_handle(self, intent: Dict[str, Any]) -> float:
        text = intent.get("text", "").lower()
        signals = [
            "why", "cause", "reason", "investigate", "drill",
            "decline", "drop", "increase", "change", "variance",
            "anomaly", "unusual", "unexpected",
        ]
        matches = sum(1 for s in signals if s in text)
        if matches >= 2:
            return 0.8
        if matches >= 1:
            return 0.5
        return 0.0

    def execute(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        import time
        t0 = time.time()
        message.status = "running"
        tools = get_tool_registry()

        try:
            step = message.input_data.get("step", "drill_down")

            if step == "discover_dimensions":
                # Find available dimensions for drill-down
                data = tools.call("get_discoverable_data")
                dims = {}
                for concept, entries in data.get("available_dimensions", {}).items():
                    dims[concept] = entries
                message.output_data = {"available_dimensions": dims}
                message.status = "completed"

            elif step == "drill_down":
                # Drill into a specific dimension
                metric = message.input_data.get("metric", "")
                dimension = message.input_data.get("dimension", "")
                result = tools.call(
                    "calculate_metric",
                    metric=metric,
                    dimensions=[dimension] if dimension else None,
                    limit=message.input_data.get("limit", 20),
                )
                message.output_data = result
                message.status = "completed"

            elif step == "compare":
                # Compare metric across dimensions
                metric = message.input_data.get("metric", "")
                date_column = message.input_data.get("date_column", "")
                period = message.input_data.get("period", "month")
                result = tools.call(
                    "compare_periods",
                    metric=metric, date_column=date_column, period=period,
                )
                message.output_data = result
                message.status = "completed"

            else:
                message.output_data = {"error": f"Unknown step: {step}"}
                message.status = "failed"

        except Exception as e:
            logger.error("Investigation agent error: %s", e)
            message.status = "failed"
            message.error = str(e)
            self._error_count += 1

        self._execution_count += 1
        self._total_latency_ms += (time.time() - t0) * 1000
        return message


def create_agent() -> InvestigationAgent:
    return InvestigationAgent()
