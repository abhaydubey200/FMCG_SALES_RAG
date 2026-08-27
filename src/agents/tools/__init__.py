"""
Central Tool Registry — every deterministic operation the agents can invoke.

Tools are the building blocks: agents reason about WHAT to do,
tools do the actual work. Tools are safe, deterministic, and workspace-scoped.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("agents.tools")


@dataclass
class ToolDef:
    """Metadata + callable for a single tool."""
    tool_id: str
    name: str
    description: str
    category: str  # "data" | "analytics" | "rag" | "ai" | "visualization" | "workspace" | "conversation"
    fn: Callable[..., Any]
    input_schema: Dict[str, str] = field(default_factory=dict)   # param_name -> description
    output_schema: str = ""
    permissions: List[str] = field(default_factory=list)         # agent_ids allowed
    timeout_seconds: int = 30
    version: str = "1.0.0"


class ToolRegistry:
    """Singleton registry — all tools register here; agents reference by tool_id."""

    def __init__(self):
        self._tools: Dict[str, ToolDef] = {}

    def register(self, tool_def: ToolDef):
        self._tools[tool_def.tool_id] = tool_def
        logger.debug("Registered tool: %s", tool_def.tool_id)

    def get(self, tool_id: str) -> Optional[ToolDef]:
        return self._tools.get(tool_id)

    def call(self, tool_id: str, **kwargs) -> Any:
        tool = self._tools.get(tool_id)
        if not tool:
            raise ValueError(f"Tool '{tool_id}' not found in registry")
        logger.info("Calling tool: %s(%s)", tool_id, list(kwargs.keys()))
        return tool.fn(**kwargs)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "tool_id": t.tool_id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "input_schema": t.input_schema,
                "output_schema": t.output_schema,
                "version": t.version,
            }
            for t in self._tools.values()
        ]

    def tools_for_agent(self, agent_id: str) -> List[ToolDef]:
        """Return tools this agent is allowed to use."""
        return [
            t for t in self._tools.values()
            if not t.permissions or agent_id in t.permissions
        ]

    def categories(self) -> Dict[str, List[str]]:
        cats: Dict[str, List[str]] = {}
        for t in self._tools.values():
            cats.setdefault(t.category, []).append(t.tool_id)
        return cats


# Global singleton
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_all_tools(_registry)
    return _registry


def _register_all_tools(registry: ToolRegistry):
    """Import and register every tool module."""
    from src.agents.tools import sql_tools, schema_tools, rag_tools, metrics_tools, viz_tools, workspace_tools
    for mod in [sql_tools, schema_tools, rag_tools, metrics_tools, viz_tools, workspace_tools]:
        mod.register_tools(registry)
