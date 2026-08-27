"""
RAG / Knowledge Agent — handles document retrieval and question answering.
"""
import logging
from typing import Any, Dict

from src.agents.registry import BaseAgent, AgentMessage
from src.agents.tools import get_tool_registry

logger = logging.getLogger("agents.rag")


class RAGAgent(BaseAgent):
    agent_id = "rag"
    name = "RAG Knowledge Agent"
    description = "Retrieves and reasons over indexed documents using vector search, keyword search, and hybrid retrieval"
    domain = "knowledge"
    capabilities = [
        "document_retrieval", "semantic_search", "keyword_search",
        "hybrid_search", "citation", "evidence_extraction",
    ]
    allowed_tools = ["vector_search", "keyword_search", "hybrid_search", "list_documents"]

    def can_handle(self, intent: Dict[str, Any]) -> float:
        query_type = intent.get("query_type", "")
        if query_type == "knowledge":
            return 0.95
        if query_type == "hybrid":
            return 0.7  # partial — also needs analytics
        text = intent.get("text", "").lower()
        doc_signals = [
            "document", "pdf", "strategy", "policy", "report",
            "what does", "according to", "mentioned", "stated",
            "said in", "source", "citation", "reference",
        ]
        matches = sum(1 for s in doc_signals if s in text)
        if matches >= 2:
            return 0.85
        if matches >= 1:
            return 0.4
        return 0.0

    def execute(self, message: AgentMessage, context: Dict[str, Any]) -> AgentMessage:
        import time
        t0 = time.time()
        message.status = "running"
        tools = get_tool_registry()

        try:
            step = message.input_data.get("step", "search")
            query = message.input_data.get("query", "")
            top_k = message.input_data.get("top_k", 5)

            if step == "search":
                search_type = message.input_data.get("search_type", "hybrid")
                if search_type == "vector":
                    result = tools.call("vector_search", query=query, top_k=top_k)
                elif search_type == "keyword":
                    result = tools.call("keyword_search", query=query, top_k=top_k)
                else:
                    result = tools.call("hybrid_search", query=query, top_k=top_k)
            elif step == "list":
                result = tools.call("list_documents")
            else:
                result = {"error": f"Unknown step: {step}"}

            message.output_data = result
            message.status = "completed"

        except Exception as e:
            logger.error("RAG agent error: %s", e)
            message.status = "failed"
            message.error = str(e)
            self._error_count += 1

        self._execution_count += 1
        self._total_latency_ms += (time.time() - t0) * 1000
        return message


def create_agent() -> RAGAgent:
    return RAGAgent()
