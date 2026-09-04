"""
RAG Tools — vector search, keyword search, document retrieval, citation resolution.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agents.tools.rag")


def register_tools(registry):
    from src.agents.tools import ToolDef

    def vector_search(query: str, top_k: int = 5, workspace_id: str = "default") -> Dict[str, Any]:
        """Search documents using vector similarity (workspace-scoped)."""
        try:
            # Check cache first — key includes workspace_id (isolation)
            from src.llm.query_cache import get_cached_rag, cache_rag_result
            cached = get_cached_rag(f"vector:{query}:{top_k}", workspace_id=workspace_id)
            if cached is not None:
                return cached

            from src.rag.pipeline import get_pipeline
            pipeline = get_pipeline()
            results = pipeline.vector_store.search(query, top_k=top_k, workspace_id=workspace_id)
            chunks = []
            for r in results:
                chunk = r.chunk if hasattr(r, 'chunk') else r
                chunks.append({
                    "document_id": getattr(chunk, "document_id", ""),
                    "document_name": getattr(chunk, "document_name", ""),
                    "document_type": getattr(chunk, "document_type", ""),
                    "text": getattr(chunk, "text", ""),
                    "relevance_score": getattr(r, "score", 0.0),
                    "source_path": getattr(chunk, "metadata", {}).get("source_path", "") if hasattr(chunk, "metadata") else "",
                })
            result = {"chunks": chunks, "count": len(chunks), "query": query}
            cache_rag_result(f"vector:{query}:{top_k}", result, workspace_id=workspace_id)
            return result
        except Exception as e:
            logger.error("Vector search failed: %s", e)
            return {"chunks": [], "count": 0, "error": str(e)}

    def keyword_search(query: str, top_k: int = 5, workspace_id: str = "default") -> Dict[str, Any]:
        """Search documents using keyword matching (workspace-scoped)."""
        try:
            from src.llm.query_cache import get_cached_rag, cache_rag_result
            cached = get_cached_rag(f"keyword:{query}:{top_k}", workspace_id=workspace_id)
            if cached is not None:
                return cached

            from src.rag.pipeline import get_pipeline
            pipeline = get_pipeline()
            results = pipeline.keyword_index.search(query, top_k=top_k, workspace_id=workspace_id)
            chunks = []
            for r in results:
                chunk = r.chunk if hasattr(r, 'chunk') else r
                chunks.append({
                    "document_id": getattr(chunk, "document_id", ""),
                    "document_name": getattr(chunk, "document_name", ""),
                    "text": getattr(chunk, "text", ""),
                    "relevance_score": getattr(r, "score", 0.0),
                })
            result = {"chunks": chunks, "count": len(chunks), "query": query}
            cache_rag_result(f"keyword:{query}:{top_k}", result, workspace_id=workspace_id)
            return result
        except Exception as e:
            return {"chunks": [], "count": 0, "error": str(e)}

    def hybrid_search(query: str, top_k: int = 5, workspace_id: str = "default") -> Dict[str, Any]:
        """Combined vector + keyword search with reranking (workspace-scoped)."""
        try:
            from src.llm.query_cache import get_cached_rag, cache_rag_result
            cached = get_cached_rag(f"hybrid:{query}:{top_k}", workspace_id=workspace_id)
            if cached is not None:
                return cached

            from src.rag.pipeline import get_pipeline
            pipeline = get_pipeline()
            results = pipeline.retriever.retrieve(query, top_k=top_k, workspace_id=workspace_id)
            chunks = []
            for r in results:
                chunk = r.chunk if hasattr(r, 'chunk') else r
                chunks.append({
                    "document_id": getattr(chunk, "document_id", ""),
                    "document_name": getattr(chunk, "document_name", ""),
                    "text": getattr(chunk, "text", ""),
                    "relevance_score": getattr(r, "rerank_score", getattr(r, "score", 0.0)),
                    "source_path": getattr(chunk, "metadata", {}).get("source_path", "") if hasattr(chunk, "metadata") else "",
                })
            result = {"chunks": chunks, "count": len(chunks), "query": query}
            cache_rag_result(f"hybrid:{query}:{top_k}", result, ttl=600, workspace_id=workspace_id)
            return result
        except Exception as e:
            return {"chunks": [], "count": 0, "error": str(e)}

    def list_documents(workspace_id: str = "default") -> Dict[str, Any]:
        """List indexed documents owned by the given workspace."""
        try:
            from src.rag.pipeline import get_pipeline
            from src.ingestion.document_loader import _chunk_workspace_id
            pipeline = get_pipeline()
            docs = {}
            for c in pipeline.vector_store.chunks:
                if _chunk_workspace_id(c) != workspace_id:
                    continue
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
