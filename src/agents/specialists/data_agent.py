"""
Data Intelligence Agent — schema understanding, profiling, data quality.
"""
import logging
from typing import Any, Dict

from src.agents.registry import BaseAgent, AgentMessage
from src.agents.tools import get_tool_registry

logger = logging.getLogger("agents.data")


class DataAgent(BaseAgent):
    agent_id = "data_intelligence"
    name = "Data Intelligence Agent"
    description = "Schema understanding, profiling, data type interpretation, quality analysis"
    domain = "data"
    capabilities = [
        "schema_understanding", "profiling", "data_type_interpretation",
        "dimensional_analysis", "metric_discovery", "data_quality",
    ]
    allowed_tools = [
        "inspect_schema", "profile_dataset", "get_discoverable_data",
        "list_workspace_assets", "get_data_quality", "get_workspace_summary",
    ]

    def can_handle(self, intent: Dict[str, Any]) -> float:
        text = intent.get("text", "").lower()
        signals = [
            "schema", "profile", "quality", "null", "duplicate",
            "column", "structure", "what data", "what tables",
            "data sources", "asset", "dataset",
        ]
        matches = sum(1 for s in signals if s in text)
        if matches >= 2:
            return 0.8
        if matches >= 1:
            return 0.4
        return 0.1  # always useful as a fallback for data inspection

    def execute(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        import time
        t0 = time.time()
        message.status = "running"
        tools = get_tool_registry()

        try:
            step = message.input_data.get("step", "summary")
            if step == "summary":
                result = tools.call("get_workspace_summary")
            elif step == "schema":
                result = tools.call("inspect_schema", table=message.input_data.get("table", ""))
            elif step == "profile":
                result = tools.call("profile_dataset", table=message.input_data.get("table", ""))
            elif step == "quality":
                result = tools.call("get_data_quality", table=message.input_data.get("table", ""))
            elif step == "discover":
                result = tools.call("get_discoverable_data")
            elif step == "assets":
                result = tools.call("list_workspace_assets")
            else:
                result = {"error": f"Unknown step: {step}"}

            message.output_data = result
            message.status = "completed"
        except Exception as e:
            logger.error("Data agent error: %s", e)
            message.status = "failed"
            message.error = str(e)
            self._error_count += 1

        self._execution_count += 1
        self._total_latency_ms += (time.time() - t0) * 1000
        return message


def create_agent() -> DataAgent:
    return DataAgent()
