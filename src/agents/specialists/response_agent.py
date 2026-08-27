"""
Response Agent — synthesizes verified evidence into a final user response.

Responsibilities:
- Combine evidence from multiple agents
- Generate natural language answer
- Include visualization specs
- Include citations
- Explain limitations
- Generate follow-up suggestions
"""
import logging
from typing import Any, Dict, List

from src.agents.registry import BaseAgent, AgentMessage
from src.agents.evidence import EvidenceGraph

logger = logging.getLogger("agents.response")


class ResponseAgent(BaseAgent):
    agent_id = "response"
    name = "Response Agent"
    description = "Synthesizes verified evidence into the final user-facing response"
    domain = "response"
    capabilities = [
        "synthesize_evidence", "generate_answer", "generate_visualization",
        "include_citations", "explain_limitations", "generate_follow_ups",
    ]
    allowed_tools = ["generate_chart_spec"]

    def can_handle(self, intent: Dict[str, Any]) -> float:
        return 1.0  # Always the final step

    def execute(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        import time
        t0 = time.time()
        message.status = "running"

        try:
            evidence_graph: EvidenceGraph = context.get("evidence_graph")
            plan_output: Dict[str, Any] = message.input_data.get("plan_output", {})
            verification: Dict[str, Any] = message.input_data.get("verification", {})
            user_query: str = message.input_data.get("user_query", "")
            llm_answer: str = message.input_data.get("llm_answer", "")

            # Collect all evidence
            all_evidence = evidence_graph.all_evidence() if evidence_graph else []
            structured = evidence_graph.structured_evidence() if evidence_graph else []
            doc_evidence = evidence_graph.document_evidence() if evidence_graph else []

            # Build sources list
            sources = []
            seen = set()
            for ev in all_evidence:
                src_key = f"{ev.evidence_type}:{ev.source}"
                if src_key not in seen:
                    sources.append({"type": ev.evidence_type, "source": ev.source})
                    seen.add(src_key)

            # Build visualization from any chart specs in evidence
            visualization = plan_output.get("visualization", {})

            # Build metrics from evidence
            metrics = {
                "query_type": plan_output.get("query_type", "analytical"),
                "agents_used": plan_output.get("agents_used", []),
                "skills_used": plan_output.get("skills_used", []),
                "tools_used": plan_output.get("tools_used", []),
                "evidence_count": len(all_evidence),
                "verification": verification.get("verdict", "NOT_VERIFIED"),
                "verification_reason": verification.get("reason", ""),
                "end_to_end_latency_ms": plan_output.get("total_latency_ms", 0),
            }

            # Determine the answer text
            answer = llm_answer
            if not answer and structured:
                # Build a data-based answer
                for ev in structured:
                    if ev.result and isinstance(ev.result, list) and ev.result:
                        answer = f"Based on the data: {ev.query or 'analytical query'} returned {len(ev.result)} results."
                        break
            if not answer and doc_evidence:
                texts = [e.text for e in doc_evidence if e.text][:3]
                answer = "From the documents: " + " ".join(texts[:200] + "..." if len(texts) > 200 else texts)
            if not answer:
                answer = "I was unable to find sufficient evidence to answer this question."

            # Evidence dict for the AnalystResponse component
            evidence_dict = {}
            kb_chunks = []
            for ev in doc_evidence:
                kb_chunks.append({
                    "source": ev.source,
                    "text": ev.text or "",
                    "relevance_score": ev.relevance_score or 0.0,
                })
            if kb_chunks:
                evidence_dict["knowledge_base_chunks"] = kb_chunks

            message.output_data = {
                "answer": answer,
                "sources": sources,
                "metrics": metrics,
                "evidence": evidence_dict,
                "visualization": visualization,
            }
            message.status = "completed"

        except Exception as e:
            logger.error("Response agent error: %s", e)
            message.status = "failed"
            message.error = str(e)
            self._error_count += 1

        self._execution_count += 1
        self._total_latency_ms += (time.time() - t0) * 1000
        return message


def create_agent() -> ResponseAgent:
    return ResponseAgent()
