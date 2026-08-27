"""
Skill Registry — reusable domain capabilities that compose tools + reasoning patterns.

A skill is NOT an agent. A skill is a named, structured plan template that says:
"to do X, use these tools, in this order, with these validation rules."

The orchestrator selects skills based on the user's intent + available data.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agents.skills")


@dataclass
class SkillDef:
    """Definition of a domain skill."""
    skill_id: str
    name: str
    description: str
    required_tools: List[str] = field(default_factory=list)
    optional_tools: List[str] = field(default_factory=list)
    recommended_agents: List[str] = field(default_factory=list)
    input_concepts: List[str] = field(default_factory=list)   # e.g. ["revenue", "time_dimension"]
    output_type: str = "analytical"  # "analytical" | "knowledge" | "hybrid" | "investigation"
    validation_rules: List[str] = field(default_factory=list)
    example_queries: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    status: str = "active"  # "active" | "deprecated" | "disabled"


class SkillRegistry:
    """Registry of all available skills."""

    def __init__(self):
        self._skills: Dict[str, SkillDef] = {}

    def register(self, skill: SkillDef):
        self._skills[skill.skill_id] = skill

    def get(self, skill_id: str) -> Optional[SkillDef]:
        return self._skills.get(skill_id)

    def list_skills(self) -> List[Dict[str, Any]]:
        return [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "description": s.description,
                "required_tools": s.required_tools,
                "input_concepts": s.input_concepts,
                "output_type": s.output_type,
                "version": s.version,
                "status": s.status,
            }
            for s in self._skills.values()
            if s.status == "active"
        ]

    def find_by_intent(self, intent_keywords: List[str], available_tools: List[str] = None) -> List[SkillDef]:
        """Find skills that match the given intent keywords and are supportable by available tools."""
        matches = []
        for skill in self._skills.values():
            if skill.status != "active":
                continue
            # Check if we have the required tools
            if available_tools:
                if not all(t in available_tools for t in skill.required_tools):
                    continue
            # Check concept overlap
            skill_words = set(skill.skill_id.lower().split("_") + skill.name.lower().split())
            intent_words = set(k.lower() for k in intent_keywords)
            if skill_words & intent_words:
                matches.append(skill)
        return matches


# Global singleton
_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _register_default_skills(_registry)
    return _registry


def _register_default_skills(reg: SkillRegistry):
    """Register the default set of skills."""
    skills = [
        SkillDef(
            skill_id="total_metric",
            name="Total Metric Calculation",
            description="Calculate the total/sum of a business metric",
            required_tools=["resolve_metric", "sql_generate", "sql_execute"],
            input_concepts=["metric"],
            output_type="analytical",
        ),
        SkillDef(
            skill_id="metric_by_dimension",
            name="Metric by Dimension Analysis",
            description="Break down a metric by one or more dimensions (e.g., revenue by region)",
            required_tools=["resolve_metric", "sql_generate", "sql_execute", "generate_chart_spec"],
            input_concepts=["metric", "dimension"],
            output_type="analytical",
        ),
        SkillDef(
            skill_id="trend_analysis",
            name="Time Series Trend Analysis",
            description="Analyze how a metric changes over time",
            required_tools=["resolve_metric", "compare_periods", "generate_chart_spec"],
            input_concepts=["metric", "date"],
            output_type="analytical",
        ),
        SkillDef(
            skill_id="ranking",
            name="Entity Ranking",
            description="Rank entities by a metric (top/bottom N)",
            required_tools=["resolve_metric", "sql_generate", "sql_execute", "generate_chart_spec"],
            input_concepts=["metric", "entity"],
            output_type="analytical",
        ),
        SkillDef(
            skill_id="document_qa",
            name="Document Question Answering",
            description="Answer questions from indexed documents using RAG",
            required_tools=["hybrid_search", "list_documents"],
            input_concepts=["document"],
            output_type="knowledge",
        ),
        SkillDef(
            skill_id="hybrid_analysis",
            name="Hybrid Structured + Unstructured Analysis",
            description="Combine analytical data with document evidence",
            required_tools=["resolve_metric", "sql_generate", "sql_execute", "hybrid_search"],
            input_concepts=["metric", "document"],
            output_type="hybrid",
        ),
        SkillDef(
            skill_id="workspace_overview",
            name="Workspace Overview",
            description="Provide a summary of the workspace state and data",
            required_tools=["get_workspace_summary", "list_workspace_assets"],
            input_concepts=[],
            output_type="analytical",
        ),
        SkillDef(
            skill_id="data_quality_check",
            name="Data Quality Assessment",
            description="Assess data quality of uploaded datasets",
            required_tools=["get_workspace_summary", "profile_dataset", "get_data_quality"],
            input_concepts=[],
            output_type="analytical",
        ),
        SkillDef(
            skill_id="investigation",
            name="Root Cause Investigation",
            description="Drill down into available dimensions to find root causes",
            required_tools=["resolve_metric", "sql_generate", "sql_execute", "compare_periods", "generate_chart_spec"],
            input_concepts=["metric", "decline", "change"],
            output_type="analytical",
        ),
    ]
    for s in skills:
        reg.register(s)
