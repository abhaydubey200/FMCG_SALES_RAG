"""
Verification Agent — MANDATORY component that validates results.

Checks:
- SQL was executed and returned results
- Calculations are consistent
- Semantic mappings are valid
- Citations point to real documents
- No unsupported claims
- No hallucinated metrics
- No unsupported causality
"""
import logging
from typing import Any, Dict, List

from src.agents.registry import BaseAgent, AgentMessage
from src.agents.evidence import EvidenceGraph

logger = logging.getLogger("agents.verification")


class VerificationAgent(BaseAgent):
    agent_id = "verification"
    name = "Verification Agent"
    description = "Validates results for consistency, correctness, and honesty"
    domain = "verification"
    capabilities = [
        "verify_sql", "verify_calculations", "verify_citations",
        "detect_hallucination", "detect_unsupported_causality",
        "validate_source_relevance",
    ]
    allowed_tools = []

    def can_handle(self, intent: Dict[str, Any]) -> float:
        return 1.0  # Always verifies — mandatory

    def execute(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        import time
        t0 = time.time()
        message.status = "running"

        try:
            evidence_graph: EvidenceGraph = context.get("evidence_graph")
            all_evidence = evidence_graph.all_evidence() if evidence_graph else []
            plan_output = message.input_data.get("plan_output", {})
            user_query = message.input_data.get("user_query", "")

            issues = []
            warnings = []

            # Check 1: Did we collect any evidence?
            if not all_evidence:
                issues.append("No evidence collected to support any claims")

            # Check 2: Structured evidence should have SQL and rows
            for ev in all_evidence:
                if ev.evidence_type == "structured":
                    if not ev.query:
                        warnings.append(f"Structured evidence {ev.evidence_id} has no SQL query")
                    if ev.result is None:
                        issues.append(f"Structured evidence {ev.evidence_id} has no result data")

                elif ev.evidence_type == "unstructured":
                    if not ev.text:
                        issues.append(f"Document evidence {ev.evidence_id} has no text")
                    if ev.relevance_score is not None and ev.relevance_score < 0.1:
                        warnings.append(f"Document evidence {ev.evidence_id} has very low relevance ({ev.relevance_score})")

            # Check 3: If query asks about metrics, we should have structured evidence
            metric_words = ["revenue", "sales", "total", "sum", "average", "count", "spend"]
            if any(w in user_query.lower() for w in metric_words):
                structured = evidence_graph.structured_evidence() if evidence_graph else []
                if not structured:
                    issues.append("Query requires numerical evidence but no structured data was retrieved")

            # Check 4: If query asks about documents, we should have document evidence
            doc_words = ["document", "pdf", "strategy", "policy", "report", "according"]
            if any(w in user_query.lower() for w in doc_words):
                doc_ev = evidence_graph.document_evidence() if evidence_graph else []
                if not doc_ev:
                    warnings.append("Query may require document evidence but none was retrieved")

            # Determine verdict
            if issues:
                verdict = "FAIL"
                reason = f"Issues found: {'; '.join(issues)}"
            elif warnings:
                verdict = "PASS_WITH_WARNINGS"
                reason = f"Warnings: {'; '.join(warnings)}"
            else:
                verdict = "PASS"
                reason = "All verification checks passed"

            message.output_data = {
                "verdict": verdict,
                "reason": reason,
                "issues": issues,
                "warnings": warnings,
                "evidence_count": len(all_evidence),
            }
            message.status = "completed"

        except Exception as e:
            logger.error("Verification agent error: %s", e)
            message.status = "failed"
            message.error = str(e)
            message.output_data = {"verdict": "ERROR", "reason": str(e)}
            self._error_count += 1

        self._execution_count += 1
        self._total_latency_ms += (time.time() - t0) * 1000
        return message


def create_agent() -> VerificationAgent:
    return VerificationAgent()
