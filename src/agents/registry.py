"""
Agent Registry + Base Agent + Agent Communication.

Agents are specialized reasoning components that use tools to accomplish tasks.
They are NOT chatbots — they are structured execution units with typed inputs/outputs.
"""
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agents.registry")


# ---------------------------------------------------------------------------
# Agent Communication Messages
# ---------------------------------------------------------------------------

@dataclass
class AgentMessage:
    """Typed message passed between agents."""
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:10]}")
    source_agent: str = ""
    target_agent: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    evidence_ids: List[str] = field(default_factory=list)
    status: str = "pending"  # pending | running | completed | failed | needs_replan
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    trace_id: str = ""

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "status": self.status,
            "error": self.error,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
        }


# ---------------------------------------------------------------------------
# Base Agent
# ---------------------------------------------------------------------------

class BaseAgent(ABC):
    """Abstract base for all specialist agents."""

    agent_id: str = "base"
    name: str = "Base Agent"
    description: str = ""
    domain: str = "general"
    capabilities: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    version: str = "1.0.0"

    def __init__(self):
        self._execution_count = 0
        self._total_latency_ms = 0
        self._error_count = 0

    @abstractmethod
    def execute(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        """Execute the agent's task. Must return a completed or failed message."""
        ...

    def can_handle(self, intent: Dict[str, Any]) -> float:
        """Return confidence 0.0–1.0 that this agent can handle the given intent."""
        return 0.0

    def health(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": "healthy",
            "version": self.version,
            "executions": self._execution_count,
            "errors": self._error_count,
            "avg_latency_ms": round(self._total_latency_ms / max(1, self._execution_count), 1),
        }

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            "capabilities": self.capabilities,
            "allowed_tools": self.allowed_tools,
            "version": self.version,
        }


# ---------------------------------------------------------------------------
# Agent Registry
# ---------------------------------------------------------------------------

class AgentRegistry:
    """Central registry for discovering and invoking agents."""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent):
        self._agents[agent.agent_id] = agent
        logger.info("Registered agent: %s (%s)", agent.agent_id, agent.name)

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self._agents.values()]

    def health(self) -> List[Dict[str, Any]]:
        return [a.health() for a in self._agents.values()]

    def find_best(self, intent: Dict[str, Any]) -> List[BaseAgent]:
        """Rank agents by their confidence of handling the intent."""
        scored = []
        for agent in self._agents.values():
            score = agent.can_handle(intent)
            if score > 0:
                scored.append((score, agent))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [agent for _, agent in scored]

    def invoke(self, agent_id: str, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        agent = self._agents.get(agent_id)
        if not agent:
            message.status = "failed"
            message.error = f"Agent '{agent_id}' not found"
            return message
        return agent.execute(message, context)


# Global singleton
_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
        _register_all_agents(_registry)
    return _registry


def _register_all_agents(registry: AgentRegistry):
    """Import and register every specialist agent."""
    from src.agents.specialists import (
        analytics_agent, rag_agent, data_agent, sales_agent,
        marketing_agent, investigation_agent, verification_agent, response_agent,
    )
    for agent_mod in [analytics_agent, rag_agent, data_agent, sales_agent,
                       marketing_agent, investigation_agent, verification_agent, response_agent]:
        agent = agent_mod.create_agent()
        registry.register(agent)
