"""
Marketing Intelligence Agent — campaign analysis, spend, conversions, ROAS.

Only calculates metrics supported by available data.
"""
import logging
from typing import Any, Dict

from src.agents.registry import BaseAgent, AgentMessage
from src.agents.tools import get_tool_registry

logger = logging.getLogger("agents.marketing")


class MarketingAgent(BaseAgent):
    agent_id = "marketing_intelligence"
    name = "Marketing Intelligence Agent"
    description = "Campaign analysis, marketing spend, conversions, CTR, CPC, CPA, ROAS"
    domain = "marketing"
    capabilities = [
        "campaign_analysis", "marketing_spend", "channel_analysis",
        "conversion_analysis", "ctr_analysis", "roas_analysis",
    ]
    allowed_tools = [
        "resolve_metric", "calculate_metric", "sql_generate", "sql_execute",
        "compare_periods", "inspect_schema", "get_discoverable_data",
        "generate_chart_spec",
    ]

    def can_handle(self, intent: Dict[str, Any]) -> float:
        text = intent.get("text", "").lower()
        mktg_signals = [
            "campaign", "marketing", "spend", "impressions", "clicks",
            "conversions", "ctr", "cpc", "cpa", "roas",
            "channel", "audience", "reach", "advertising",
        ]
        matches = sum(1 for s in mktg_signals if s in text)
        if matches >= 3:
            return 0.85
        if matches >= 2:
            return 0.6
        return 0.0

    def execute(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        import time
        t0 = time.time()
        message.status = "running"
        tools = get_tool_registry()

        try:
            step = message.input_data.get("step", "analyze")
            if step == "analyze":
                metric = message.input_data.get("metric", "")
                dimensions = message.input_data.get("dimensions")
                result = tools.call("calculate_metric", metric=metric, dimensions=dimensions)
            elif step == "discover":
                result = tools.call("get_discoverable_data")
            elif step == "sql":
                gen = tools.call(
                    "sql_generate",
                    metric=message.input_data.get("metric", ""),
                    table=message.input_data.get("table", ""),
                    dimensions=message.input_data.get("dimensions"),
                    order_by=message.input_data.get("order_by", ""),
                    limit=message.input_data.get("limit", 20),
                )
                if gen.get("valid"):
                    exec_result = tools.call("sql_execute", sql=gen["sql"])
                    result = {**gen, **exec_result}
                else:
                    result = gen
            else:
                result = {"error": f"Unknown step: {step}"}

            message.output_data = result
            message.status = "completed"
        except Exception as e:
            logger.error("Marketing agent error: %s", e)
            message.status = "failed"
            message.error = str(e)
            self._error_count += 1

        self._execution_count += 1
        self._total_latency_ms += (time.time() - t0) * 1000
        return message


def create_agent() -> MarketingAgent:
    return MarketingAgent()
