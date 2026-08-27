"""
RAG Tools — vector search, keyword search, document retrieval, citation resolution.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agents.tools.rag")


def register_tools(registry):
    from src.agents.tools import ToolDef

    def vector_search(query: str, top_k: int = 5) -> Dict[str, Any]:
        """Search documents using vector similarity."""
        try:
            from src.rag.pipeline import get_pipeline
            pipeline = get_pipeline()
            results = pipeline.vector_store.search(query, top_k=top_k)
            chunks = []
            for r in results:
                chunks.append({
                    "document_id": r.get("document_id", ""),
                    "document_name": r.get("document_name", ""),
                    "document_type": r.get("document_type", ""),
                    "text": r.get("text", ""),
                    "relevance_score": r.get("score", 0.0),
                    "source_path": r.get("metadata", {}).get("source_path", ""),
                })
            return {"chunks": chunks, "count": len(chunks), "query": query}
        except Exception as e:
            logger.error("Vector search failed: %s", e)
            return {"chunks": [], "count": 0, "error": str(e)}

    def keyword_search(query: str, top_k: int = 5) -> Dict[str, Any]:
        """Search documents using keyword matching."""
        try:
            from src.rag.pipeline import get_pipeline
            pipeline = get_pipeline()
            results = pipeline.keyword_index.search(query, top_k=top_k)
            chunks = []
            for r in results:
                chunks.append({
                    "document_id": r.get("document_id", ""),
                    "document_name": r.get("document_name", ""),
                    "text": r.get("text", ""),
                    "relevance_score": r.get("score", 0.0),
                })
            return {"chunks": chunks, "count": len(chunks), "query": query}
        except Exception as e:
            return {"chunks": [], "count": 0, "error": str(e)}

    def hybrid_search(query: str, top_k: int = 5) -> Dict[str, Any]:
        """Combined vector + keyword search with reranking."""
        try:
            from src.rag.pipeline import get_pipeline
            pipeline = get_pipeline()
            results = pipeline.retriever.retrieve(query, top_k=top_k)
            chunks = []
            for r in results:
                chunks.append({
                    "document_id": getattr(r, "document_id", ""),
                    "document_name": getattr(r, "document_name", ""),
                    "text": getattr(r, "text", ""),
                    "relevance_score": getattr(r, "score", 0.0),
                    "source_path": getattr(r, "metadata", {}).get("source_path", "") if hasattr(r, "metadata") else "",
                })
            return {"chunks": chunks, "count": len(chunks), "query": query}
        except Exception as e:
            return {"chunks": [], "count": 0, "error": str(e)}

    def list_documents() -> Dict[str, Any]:
        """List all indexed documents."""
        try:
            from src.rag.pipeline import get_pipeline
            pipeline = get_pipeline()
            docs = {}
            for c in pipeline.vector_store.chunks:
                if c.document_id not in docs:
                    docs[c.document_id] = {
                        "document_id": c.document_id,
                        "document_name": c.document_name,
                        "document_type": c.document_type,
                        "chunk_count": 0,
                    }
                docs[c.document_id]["chunk_count"] += 1
            return {"documents": list(docs.values()), "count": len(docs)}
        except Exception as e:
            return {"documents": [], "count": 0, "error": str(e)}

    registry.register(ToolDef(
        tool_id="vector_search", name="Vector Search",
        description="Semantic search through document embeddings using pgvector",
        category="rag", fn=vector_search,
        input_schema={"query": "search query", "top_k": "max results"},
        output_schema="chunks with relevance scores",
    ))
    registry.register(ToolDef(
        tool_id="keyword_search", name="Keyword Search",
        description="Keyword-based document search",
        category="rag", fn=keyword_search,
        input_schema={"query": "search query", "top_k": "max results"},
        output_schema="chunks with scores",
    ))
    registry.register(ToolDef(
        tool_id="hybrid_search", name="Hybrid Search",
        description="Combined vector + keyword search with reranking",
        category="rag", fn=hybrid_search,
        input_schema={"query": "search query", "top_k": "max results"},
        output_schema="chunks with scores",
    ))
    registry.register(ToolDef(
        tool_id="list_documents", name="Document Lister",
        description="List all indexed knowledge base documents",
        category="rag", fn=list_documents,
        input_schema={}, output_schema="documents with chunk counts",
    ))
