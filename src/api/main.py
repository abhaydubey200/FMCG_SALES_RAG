"""
FastAPI backend (assignment Section 17).

Engineering notes (README "Backend engineering"):
- Modular: routes only orchestrate; all logic lives in src/rag, src/retrieval,
  src/analytics, src/ingestion.
- The RAG pipeline (embeddings + indexes) is built once at startup and reused
  across requests (expensive to rebuild per-request).
- Document upload/delete triggers a full knowledge-base reindex — fine at
  this corpus size; documented in README as a scalability concern for large
  corpora (incremental indexing would be needed instead).
"""
import io
import logging
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

import json

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src import config
from src.analytics import sql_layer


def _fetchall(conn, query, params=None):
    """Execute query and return list of dicts."""
    cur = conn.cursor()
    if params:
        cur.execute(query, params)
    else:
        cur.execute(query)
    rows = cur.fetchall()
    if not rows:
        return []
    try:
        return [dict(row) for row in rows]
    except Exception:
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in rows]


def _fetchone(conn, query, params=None):
    """Execute query and return single dict or None."""
    cur = conn.cursor()
    if params:
        cur.execute(query, params)
    else:
        cur.execute(query)
    row = cur.fetchone()
    if row is None:
        return None
    try:
        return dict(row)
    except Exception:
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))


def _query_error_body(e, default_code="INTERNAL_ERROR", default_retryable=False):
    """Standardized API error payload: {"error": {code, message, retryable}}."""
    msg = str(e) or e.__class__.__name__
    ml = msg.lower()
    code = default_code
    retryable = default_retryable
    if any(k in ml for k in ("timed out", "timeout", "connection aborted", "read timed out", "requests.exceptions")):
        code, retryable = "LLM_TIMEOUT", True
    elif any(k in ml for k in ("database", "postgres", "connection refused", "psycopg2", "redis")):
        code, retryable = "DATABASE_ERROR", True
    elif "no attribute" in ml or "traceback" in ml:
        code = "INTERNAL_ERROR"
    return {"error": {"code": code, "message": msg[:300], "retryable": retryable},
            "detail": msg[:300]}


def _raise_query_error(e):
    """Raise HTTPException with the standardized error contract."""
    body = _query_error_body(e)
    status = 503 if body["error"]["retryable"] else 500
    raise HTTPException(status_code=status, detail=body)


def _to_dict(row, cursor=None):
    """Convert a single row (psycopg2 or sqlite3) to a dict."""
    if row is None:
        return None
    try:
        return dict(row)
    except Exception:
        if cursor and cursor.description:
            cols = [desc[0] for desc in cursor.description]
            return dict(zip(cols, row))
        return {}

from src.api.schemas import (CampaignListItem, CategoryPerformance, CustomerSegment,
                              DashboardResponse, DeleteResponse, DocumentInfo,
                              EvaluationResult, MonthlyRevenueTrend, OverviewKPI,
                              ProductListItem, QueryRequest, QueryResponse, UploadResponse)
from src.analytics.dynamic_engine import (
    ingest_file as dynamic_ingest, list_datasets as dynamic_list_datasets,
    get_dataset as dynamic_get_dataset, delete_dataset as dynamic_delete_dataset,
    discover_available_data, get_available_kpis, generate_dynamic_overview,
    build_dynamic_semantic_context, has_workspace_data, get_workspace_tables,
    workspace_total_revenue, workspace_total_quantity, workspace_total_spend,
    workspace_revenue_by_dimension, workspace_revenue_trend, workspace_top_entities,
    workspace_row_count, workspace_column_names, _sanitize_sql_identifier as _ssi,
    _get_pg_connection,
)
from src.rag.pipeline import get_pipeline

logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger("sales_marketing_assistant")

app = FastAPI(
    title="Amazon Sales & Marketing Intelligence Assistant",
    description="RAG + Analytics assistant over structured sales/marketing data and business knowledge documents.",
    version="1.0.0",
)

# CORS: In production, restrict to specific origins via CORS_ORIGINS env var.
# For development/demo: allow all.
import os as _os
cors_origins_str = _os.getenv("CORS_ORIGINS", "*")
cors_origins = [o.strip() for o in cors_origins_str.split(",")] if cors_origins_str != "*" else ["*"]
app.add_middleware(
    CORSMiddleware, allow_origins=cors_origins, allow_credentials=(cors_origins != ["*"]),
    allow_methods=["*"], allow_headers=["*"],
)

_pipeline = None


def _auto_seed_demo():
    """Auto-seed demo datasets and knowledge docs if workspace is empty.

    Called at API startup. Idempotent: skips if workspace already has data.
    Handles both fresh Docker volumes and existing environments.
    """
    try:
        if not config.USE_POSTGRESQL:
            return

        # Check if workspace already has data
        try:
            has_data = has_workspace_data()
        except Exception:
            has_data = False

        if has_data:
            logger.info("[seed] Workspace has data — skipping auto-seed")
            return

        logger.info("[seed] Workspace empty — auto-seeding demo environment...")

        # Seed datasets
        import os as _os
        test_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "tests", "test_datasets")
        test_dir = _os.path.normpath(test_dir)

        demo_datasets = [
            ("sales_region_north.csv", "Dataset A (North)"),
            ("sales_region_south.csv", "Dataset B (South)"),
            ("sales_export_erp.csv", "Dataset C (ERP)"),
        ]

        for filename, label in demo_datasets:
            filepath = _os.path.join(test_dir, filename)
            if not _os.path.exists(filepath):
                logger.warning("[seed] %s not found — generating...", filepath)
                try:
                    import subprocess
                    gen_script = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "tests", "generate_test_datasets.py")
                    subprocess.run([sys.executable, gen_script], timeout=30, capture_output=True)
                except Exception as ge:
                    logger.warning("[seed] generate_test_datasets.py failed: %s", ge)
                if not _os.path.exists(filepath):
                    logger.error("[seed] Cannot find %s — skipping", filename)
                    continue

            try:
                with open(filepath, "rb") as f:
                    file_bytes = f.read()
                result = dynamic_ingest(file_bytes, filename, "default")
                logger.info("[seed] %s: %d rows ingested", label, result.get("total_rows", 0))
            except Exception as e:
                logger.warning("[seed] Failed to ingest %s: %s", filename, e)

        # Seed knowledge base documents
        import shutil
        kb_dir = Path(config.KB_DIR)
        kb_dir.mkdir(parents=True, exist_ok=True)
        project_root = Path(_os.path.dirname(_os.path.abspath(__file__))).parent.parent
        source_kb = project_root / "data" / "knowledge_base"

        kb_docs = [
            "trade_promotion_policy.md",
            "sustainability_and_compliance.md",
            "pricing_and_margin_policy.md",
            "quality_and_recall_policy.md",
            "category_management_strategy.md",
        ]

        docs_added = 0
        for doc_name in kb_docs:
            dest = kb_dir / doc_name
            if dest.exists():
                continue
            src_file = source_kb / doc_name
            if src_file.exists():
                shutil.copy2(str(src_file), str(dest))
                docs_added += 1

        if docs_added > 0 and _pipeline:
            logger.info("[seed] Reindexing pipeline (%d new docs)...", docs_added)
            try:
                _pipeline.reindex()
                logger.info("[seed] Pipeline reindexed")
            except Exception as e:
                logger.warning("[seed] Reindex failed: %s", e)

        # Verify
        try:
            total = workspace_total_revenue()
            logger.info("[seed] Combined revenue after seed: %.2f", total or 0)
        except Exception:
            pass

        logger.info("[seed] Auto-seed complete")

    except Exception as e:
        logger.warning("[seed] Auto-seed failed (non-fatal): %s", e)


@app.on_event("startup")
def startup():
    global _pipeline
    logger.info("Loading RAG pipeline (vector store + keyword index)...")
    _pipeline = get_pipeline()
    logger.info("Pipeline ready. LLM backend=%s, embedding backend=%s", config.LLM_BACKEND, config.EMBEDDING_BACKEND)

    # Auto-seed demo environment if workspace is empty
    _auto_seed_demo()

    # Ensure knowledge base is indexed — the pre-startup seed script may
    # have written .md files before the pipeline was loaded, so the
    # vector store could be stale. Reindex if KB docs exist but chunks
    # are zero.
    try:
        kb_dir = Path(config.KB_DIR)
        kb_files = list(kb_dir.glob("*.md")) if kb_dir.exists() else []
        if kb_files and _pipeline and len(_pipeline.vector_store.chunks) == 0:
            logger.info("[startup] KB has %d .md files but 0 chunks — reindexing...", len(kb_files))
            _pipeline.reindex()
            logger.info("[startup] Reindexed KB: %d chunks", len(_pipeline.vector_store.chunks))
    except Exception as e:
        logger.warning("[startup] KB reindex check failed: %s", e)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_backend": config.LLM_BACKEND,
        "embedding_backend": config.EMBEDDING_BACKEND,
        "groq_available": bool(config.GROQ_API_KEY),
        "query_cache_enabled": getattr(config, "ENABLE_QUERY_CACHE", True),
        "template_synthesis_enabled": getattr(config, "ENABLE_TEMPLATE_SYNTHESIS", True),
    }


@app.post("/api/ai/route")
def route_query(req: QueryRequest):
    """Debug endpoint — shows the deterministic routing decision for a query."""
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    try:
        from src.agents.router import get_router
        from src.agents.semantic import get_semantic_resolver
        router = get_router()
        semantic = get_semantic_resolver()

        route = router.route(req.question)
        resolved = semantic.resolve(req.question, route.route)

        return {
            "route": route.route,
            "confidence": route.confidence,
            "reasoning": route.reasoning,
            "entities": route.entities,
            "metrics": route.metrics,
            "dimensions": route.dimensions,
            "needs_llm": route.needs_llm,
            "resolved_metrics": [m.name for m in resolved.metrics],
            "resolved_dimensions": [d.name for d in resolved.dimensions],
            "grain": resolved.grain,
            "needs_rag": resolved.needs_rag,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ai/cache/stats")
def cache_stats():
    """Return cache statistics for monitoring."""
    try:
        from src.llm.query_cache import get_query_cache
        cache = get_query_cache()
        return cache.stats()
    except Exception as e:
        return {"error": str(e)}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    """Unified query endpoint — delegates to the agentic orchestrator.
    
    Previously used the legacy RAGPipeline which had incorrect multi-dataset
    aggregation. Now routes through the same orchestrator as /api/ai/query
    for a single authoritative analytics path.
    """
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    try:
        orch = _get_orchestrator()
        workspace_id = req.workspace_id or "default"
        conv_context = []
        conv_id = req.conversation_id
        if conv_id:
            try:
                with sql_layer.get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("""SELECT m.role, m.content FROM conversation_messages m
                                   JOIN conversations c ON c.id = m.conversation_id
                                   WHERE m.conversation_id = %s AND c.workspace_id = %s ORDER BY m.id""",
                                (conv_id, workspace_id))
                    conv_context = [{"role": r[0], "content": r[1]} for r in cur.fetchall()[-6:]]
            except Exception:
                pass
        result = orch.process(req.question, conversation_context=conv_context,
                              conversation_id=conv_id, workspace_id=workspace_id)
        # Adapt orchestrator response to QueryResponse format
        return QueryResponse(
            answer=result.get("answer", ""),
            query_type=result.get("query_type", "analytical"),
            sources=result.get("sources", []),
            metrics=result.get("metrics", {}),
            evidence=result.get("evidence", {}),
            visualization=result.get("visualization", {}),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Query failed")
        _raise_query_error(e)


@app.post("/query/stream")
def query_stream(req: QueryRequest):
    """SSE streaming endpoint — delegates to the agentic orchestrator.
    
    Events:
    - event: metadata  → query_type, classification, agents
    - event: agent_started → agent execution begins
    - event: token     → incremental answer text
    - event: agent_completed → agent finished
    - event: verification_completed → verification result
    - event: done      → final metrics + full answer
    - event: error     → error message
    """
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")

    def event_generator():
        full_answer = []
        try:
            # Immediate acknowledgment so frontend knows connection is alive
            yield f"event: start\ndata: {{}}\n\n"

            orch = _get_orchestrator()
            workspace_id = req.workspace_id or "default"
            conv_context = []
            conv_id = req.conversation_id
            conv_owned = False
            if conv_id:
                try:
                    with sql_layer.get_conn() as conn:
                        cur = conn.cursor()
                        # Conversation history is workspace-scoped: a conversation
                        # owned by another workspace cannot leak into this request.
                        cur.execute("SELECT 1 FROM conversations WHERE id = %s AND workspace_id = %s",
                                    (conv_id, workspace_id))
                        conv_owned = cur.fetchone() is not None
                        cur.execute("""SELECT m.role, m.content FROM conversation_messages m
                                       JOIN conversations c ON c.id = m.conversation_id
                                       WHERE m.conversation_id = %s AND c.workspace_id = %s ORDER BY m.id""",
                                    (conv_id, workspace_id))
                        conv_context = [{"role": r[0], "content": r[1]} for r in cur.fetchall()[-6:]]
                except Exception:
                    pass
            for event in orch.process_stream(req.question, conversation_context=conv_context,
                                              conversation_id=conv_id, workspace_id=workspace_id):
                event_type = event.get("type", "token")
                data = json.dumps({k: v for k, v in event.items() if k != "type"}, default=str)
                yield f"event: {event_type}\ndata: {data}\n\n"
                if event_type == "token" and "content" in event:
                    full_answer.append(event["content"])
                elif event_type == "done" and "answer" in event:
                    full_answer.clear()
                    full_answer.append(event["answer"])
            # Persist conversation messages (only when the workspace owns the conversation)
            if conv_owned and conv_id and full_answer:
                try:
                    now = datetime.now().isoformat()
                    with sql_layer.get_conn() as conn:
                        cur = conn.cursor()
                        answer_text = "".join(full_answer)
                        cur.execute("INSERT INTO conversation_messages (conversation_id, role, content) VALUES (%s, %s, %s)",
                                    (conv_id, 'assistant', answer_text))
                        cur.execute("UPDATE conversations SET updated_at = %s, title = CASE WHEN title = 'New Conversation' THEN LEFT(%s, 100) ELSE title END WHERE id = %s",
                                    (now, req.question, conv_id))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to persist streaming response: {e}")
        except Exception as e:
            logger.exception("Streaming query failed")
            body = _query_error_body(e)
            err = body["error"]
            err_payload = json.dumps({"error": "[%s] %s" % (err["code"], err["message"]),
                                      "code": err["code"], "retryable": err["retryable"]})
            yield "event: error\ndata: " + err_payload + "\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Agentic AI Architecture — Orchestrator Endpoints
# ---------------------------------------------------------------------------

_orchestrator = None


def _get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        try:
            from src.agents.orchestrator_v2 import Orchestrator
            _orchestrator = Orchestrator()
        except Exception as e:
            logger.warning("V2 orchestrator import failed (%s), using V1", e)
            from src.agents.orchestrator import Orchestrator
            _orchestrator = Orchestrator()
    return _orchestrator


@app.post("/api/ai/query")
def ai_query(req: QueryRequest):
    """Agentic query — uses the full multi-specialist orchestrator pipeline."""
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    try:
        orch = _get_orchestrator()
        workspace_id = req.workspace_id or "default"
        conv_context = []
        conv_id = req.conversation_id
        conv_owned = False
        if conv_id:
            try:
                with sql_layer.get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT 1 FROM conversations WHERE id = %s AND workspace_id = %s",
                                (conv_id, workspace_id))
                    conv_owned = cur.fetchone() is not None
                    cur.execute("""SELECT m.role, m.content FROM conversation_messages m
                                   JOIN conversations c ON c.id = m.conversation_id
                                   WHERE m.conversation_id = %s AND c.workspace_id = %s ORDER BY m.id""",
                                (conv_id, workspace_id))
                    conv_context = [{"role": r[0], "content": r[1]} for r in cur.fetchall()[-6:]]
            except Exception:
                pass
        result = orch.process(req.question, conversation_context=conv_context,
                              conversation_id=conv_id, workspace_id=workspace_id)
        # Persist user message and assistant response to conversation
        if conv_owned and conv_id:
            try:
                now = datetime.now().isoformat()
                with sql_layer.get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO conversation_messages (conversation_id, role, content) VALUES (%s, %s, %s)",
                                (conv_id, 'user', req.question))
                    result_json = json.dumps(result, default=str) if isinstance(result, dict) else str(result)
                    cur.execute("INSERT INTO conversation_messages (conversation_id, role, content, result) VALUES (%s, %s, %s, %s)",
                                (conv_id, 'assistant', result.get('answer', '') if isinstance(result, dict) else str(result), result_json))
                    cur.execute("UPDATE conversations SET updated_at = %s, title = CASE WHEN title = 'New Conversation' THEN LEFT(%s, 100) ELSE title END WHERE id = %s",
                                (now, req.question, conv_id))
                    conn.commit()
            except Exception as e:
                logger.warning(f"Failed to persist conversation messages: {e}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Agentic query failed")
        _raise_query_error(e)


@app.post("/api/ai/query/stream")
def ai_query_stream(req: QueryRequest):
    """Agentic streaming query — SSE with multi-specialist execution."""
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")

    def event_generator():
        full_answer = []
        try:
            # Immediate acknowledgment so frontend knows connection is alive
            yield f"event: start\ndata: {{}}\n\n"

            orch = _get_orchestrator()
            workspace_id = req.workspace_id or "default"
            conv_context = []
            conv_id = req.conversation_id
            conv_owned = False
            if conv_id:
                try:
                    with sql_layer.get_conn() as conn:
                        cur = conn.cursor()
                        # Conversation history is workspace-scoped: a conversation
                        # owned by another workspace cannot leak into this request.
                        cur.execute("SELECT 1 FROM conversations WHERE id = %s AND workspace_id = %s",
                                    (conv_id, workspace_id))
                        conv_owned = cur.fetchone() is not None
                        cur.execute("""SELECT m.role, m.content FROM conversation_messages m
                                       JOIN conversations c ON c.id = m.conversation_id
                                       WHERE m.conversation_id = %s AND c.workspace_id = %s ORDER BY m.id""",
                                    (conv_id, workspace_id))
                        conv_context = [{"role": r[0], "content": r[1]} for r in cur.fetchall()[-6:]]
                except Exception:
                    pass
            if conv_owned:
                # Persist user message (only when the workspace owns the conversation)
                try:
                    with sql_layer.get_conn() as conn:
                        cur = conn.cursor()
                        cur.execute("INSERT INTO conversation_messages (conversation_id, role, content) VALUES (%s, %s, %s)",
                                    (conv_id, 'user', req.question))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to persist user message: {e}")
            for event in orch.process_stream(req.question, conversation_context=conv_context,
                                              conversation_id=conv_id, workspace_id=workspace_id):
                event_type = event.get("type", "token")
                data = json.dumps({k: v for k, v in event.items() if k != "type"}, default=str)
                yield f"event: {event_type}\ndata: {data}\n\n"
                if event_type == "token" and "content" in event:
                    full_answer.append(event["content"])
                elif event_type == "done" and "answer" in event:
                    full_answer.clear()
                    full_answer.append(event["answer"])
            # Persist assistant response (only when the workspace owns the conversation)
            if conv_owned and conv_id and full_answer:
                try:
                    now = datetime.now().isoformat()
                    with sql_layer.get_conn() as conn:
                        cur = conn.cursor()
                        answer_text = "".join(full_answer)
                        cur.execute("INSERT INTO conversation_messages (conversation_id, role, content) VALUES (%s, %s, %s)",
                                    (conv_id, 'assistant', answer_text))
                        cur.execute("UPDATE conversations SET updated_at = %s, title = CASE WHEN title = 'New Conversation' THEN LEFT(%s, 100) ELSE title END WHERE id = %s",
                                    (now, req.question, conv_id))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to persist assistant response: {e}")
        except Exception as e:
            logger.exception("Agentic streaming query failed")
            body = _query_error_body(e)
            err = body["error"]
            err_payload = json.dumps({"error": "[%s] %s" % (err["code"], err["message"]),
                                      "code": err["code"], "retryable": err["retryable"]})
            yield "event: error\ndata: " + err_payload + "\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/ai/agents")
def list_agents():
    """List all registered specialist agents."""
    try:
        from src.agents.registry import get_agent_registry
        registry = get_agent_registry()
        return {"agents": registry.list_agents(), "count": len(registry.list_agents())}
    except Exception as e:
        return {"agents": [], "error": str(e)}


@app.get("/api/ai/agents/health")
def agents_health():
    """Health status of all agents."""
    try:
        from src.agents.registry import get_agent_registry
        registry = get_agent_registry()
        return {"agents": registry.health()}
    except Exception as e:
        return {"agents": [], "error": str(e)}


@app.get("/api/ai/skills")
def list_skills():
    """List all registered skills."""
    try:
        from src.agents.skills import get_skill_registry
        registry = get_skill_registry()
        return {"skills": registry.list_skills(), "count": len(registry.list_skills())}
    except Exception as e:
        return {"skills": [], "error": str(e)}


@app.get("/api/ai/tools")
def list_tools():
    """List all registered tools."""
    try:
        from src.agents.tools import get_tool_registry
        registry = get_tool_registry()
        return {"tools": registry.list_tools(), "categories": registry.categories(), "count": len(registry.list_tools())}
    except Exception as e:
        return {"tools": [], "error": str(e)}


@app.get("/documents", response_model=list[DocumentInfo])
def list_documents(workspace_id: str = "default"):
    from src.ingestion.document_loader import _chunk_workspace_id
    docs = {}
    for c in _pipeline.vector_store.chunks:
        if _chunk_workspace_id(c) != workspace_id:
            continue
        if c.document_id not in docs:
            docs[c.document_id] = {
                "document_id": c.document_id, "document_name": c.document_name,
                "document_type": c.document_type, "chunk_count": 0,
                "source_path": c.metadata.get("source_path", ""),
            }
        docs[c.document_id]["chunk_count"] += 1
    return list(docs.values())


ALLOWED_EXTENSIONS = {".md", ".csv", ".xlsx", ".xls", ".txt", ".pdf"}


def _convert_data_file_to_markdown(file_bytes: bytes, filename: str) -> str:
    """Convert CSV/Excel/TXT data files into a Markdown document for RAG ingestion."""
    ext = Path(filename).suffix.lower()

    if ext == ".csv":
        import pandas as pd
        df = pd.read_csv(io.BytesIO(file_bytes))
        lines = [f"# {Path(filename).stem.replace('_', ' ').title()}\n"]
        lines.append(f"Dataset containing {len(df)} rows and {len(df.columns)} columns.\n")
        lines.append("## Schema\n")
        for col in df.columns:
            dtype = str(df[col].dtype)
            sample = df[col].dropna().head(3).tolist()
            lines.append(f"- **{col}** ({dtype}): {sample}\n")
        lines.append("\n## Summary Statistics\n")
        lines.append(df.describe().to_markdown() + "\n")
        lines.append("\n## Full Data\n")
        for i, row in df.iterrows():
            parts = [f"{col}: {val}" for col, val in row.items() if pd.notna(val)]
            lines.append(f"- Row {i+1}: {' | '.join(parts)}\n")
        return "".join(lines)

    elif ext in (".xlsx", ".xls"):
        import pandas as pd
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        lines = [f"# {Path(filename).stem.replace('_', ' ').title()}\n"]
        lines.append(f"Excel workbook containing {len(xls.sheet_names)} sheet(s): {', '.join(xls.sheet_names)}\n")
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            lines.append(f"\n## Sheet: {sheet}\n")
            lines.append(f"{len(df)} rows, {len(df.columns)} columns.\n")
            lines.append("### Schema\n")
            for col in df.columns:
                dtype = str(df[col].dtype)
                sample = df[col].dropna().head(3).tolist()
                lines.append(f"- **{col}** ({dtype}): {sample}\n")
            lines.append("\n### Data\n")
            lines.append(df.to_markdown(index=False) + "\n")
        return "".join(lines)

    elif ext == ".txt":
        return file_bytes.decode("utf-8", errors="replace")

    return file_bytes.decode("utf-8", errors="replace")


@app.post("/documents/upload", response_model=UploadResponse)
def upload_document(file: UploadFile = File(...), workspace_id: str = Form("default")):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422,
                            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    file_bytes = file.file.read()

    if ext in (".csv", ".xlsx", ".xls") and len(file_bytes) > 512_000:
        raise HTTPException(status_code=422,
                            detail=f"Data file '{file.filename}' is too large for knowledge base ingestion ({len(file_bytes):,} bytes). "
                                   "Use the Data Hub upload instead for structured data files.")

    # Workspace-prefixed storage: two workspaces may upload the same filename
    # without colliding, and chunk metadata is tagged with the owning workspace.
    stored_name = f"{workspace_id}__{file.filename}" if workspace_id != "default" else file.filename
    if ext == ".pdf":
        dest = Path(config.KB_DIR) / stored_name
        dest.write_bytes(file_bytes)
    elif ext != ".md":
        md_content = _convert_data_file_to_markdown(file_bytes, file.filename)
        stem = Path(stored_name).stem
        dest = Path(config.KB_DIR) / f"{stem}.md"
        dest.write_text(md_content, encoding="utf-8")
    else:
        dest = Path(config.KB_DIR) / stored_name
        dest.write_bytes(file_bytes)

    doc_id = dest.stem
    try:
        with sql_layer.get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO documents (document_id, document_name, document_type, file_path, chunk_count, workspace_id, status) "
                "VALUES (%s, %s, %s, %s, 0, %s, 'ready') "
                "ON CONFLICT (document_id) DO UPDATE SET workspace_id = EXCLUDED.workspace_id, status = 'ready'",
                (doc_id, dest.stem.replace("_", " ").title(), ext.lstrip("."), str(dest), workspace_id)
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to register document in DB: {e}")

    try:
        _pipeline.reindex()
        from src.llm.query_cache import clear_all_caches
        clear_all_caches()
    except Exception as e:
        logger.exception("Upload/reindex failed")
        raise HTTPException(status_code=500, detail=f"Failed to reindex: {e}")

    chunk_count = len([c for c in _pipeline.vector_store.chunks
                       if c.document_id == doc_id and (c.metadata or {}).get("workspace_id", "default") == workspace_id])
    return UploadResponse(document_id=doc_id, document_name=doc_id.replace("_", " ").title(),
                           chunks_created=chunk_count, message="Document ingested and indexed.")


@app.delete("/documents/{document_id}", response_model=DeleteResponse)
def delete_document(document_id: str, workspace_id: str = "default"):
    safe_id = "".join(ch for ch in document_id if ch.isalnum() or ch in "_-")
    # Only delete documents owned by the requesting workspace
    try:
        with sql_layer.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT file_path FROM documents WHERE document_id = %s AND workspace_id = %s",
                        (safe_id, workspace_id))
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")
        file_path = row[0]
    except HTTPException:
        raise
    except Exception:
        file_path = None
    path = Path(file_path) if file_path else Path(config.KB_DIR) / f"{safe_id}.md"
    if path.exists():
        path.unlink()
    try:
        with sql_layer.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT chunk_id FROM document_chunks WHERE document_id = %s", (safe_id,))
            chunk_ids = [r[0] for r in cur.fetchall()]
            if chunk_ids:
                cur.execute("DELETE FROM embeddings WHERE chunk_id = ANY(%s)", (chunk_ids,))
            cur.execute("DELETE FROM document_chunks WHERE document_id = %s", (safe_id,))
            cur.execute("DELETE FROM documents WHERE document_id = %s", (safe_id,))
            cur.execute("DELETE FROM assets WHERE asset_id = %s", (f"kb_{safe_id}",))
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to clean up DB records for document {safe_id}: {e}")
    _pipeline.reindex()
    try:
        from src.database.state_manager import get_cache_manager
        get_cache_manager().invalidate_rag()
        from src.llm.query_cache import clear_all_caches
        clear_all_caches()
    except Exception:
        pass
    return DeleteResponse(document_id=document_id, deleted=True, message="Document removed and index rebuilt.")


@app.get("/dashboard", response_model=DashboardResponse)
def dashboard(workspace_id: str = "default"):
    """Dashboard — workspace data only. No legacy fallback."""
    if has_workspace_data(workspace_id):
        total_revenue = workspace_total_revenue(workspace_id) or 0
        total_units = workspace_total_quantity(workspace_id) or 0
        total_spend = workspace_total_spend(workspace_id) or 0
        return DashboardResponse(
            total_products=int(total_units), total_revenue=round(total_revenue, 2),
            total_marketing_spend=round(total_spend, 2), avg_roas=None,
            top_category=None, total_customers=workspace_row_count(workspace_id), total_reviews=0,
        )
    return DashboardResponse(
        total_products=0, total_revenue=0, total_marketing_spend=0,
        avg_roas=None, top_category=None, total_customers=0, total_reviews=0,
    )



# ---------------------------------------------------------------------------
# Advanced Analytics Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/analytics/overview", response_model=OverviewKPI)
def analytics_overview(workspace_id: str = "default"):
    """Dynamic analytics overview — workspace data only."""
    if not has_workspace_data(workspace_id):
        return OverviewKPI(
            total_revenue=0, total_units_sold=0, gross_margin_pct=None,
            total_marketing_spend=0, avg_roas=None, total_customers=0,
            revenue_growth_pct=None, units_growth_pct=None,
            margin_growth_pct=None, spend_growth_pct=None,
            roas_growth_pct=None, customer_growth_pct=None,
        )
    try:
        total_revenue = workspace_total_revenue(workspace_id) or 0
        total_units = workspace_total_quantity(workspace_id) or 0
        total_spend = workspace_total_spend(workspace_id) or 0
        total_customers = workspace_row_count(workspace_id)
        avg_roas = (total_revenue / total_spend) if total_spend else None
        gross_margin = None
        try:
            data = discover_available_data(workspace_id)
            rev_entries = data["available_measures"].get("revenue", [])
            cost_entries = data["available_measures"].get("cost", [])
            if rev_entries and cost_entries:
                rev = rev_entries[0]
                cost = cost_entries[0]
                if rev["table"] == cost["table"]:
                    _ssi(rev["table"])
                    _ssi(rev["column"])
                    _ssi(cost["column"])
                    conn = _get_pg_connection()
                    try:
                        cur = conn.cursor()
                        cur.execute(f'SELECT SUM("{rev["column"]}" - "{cost["column"]}") FROM "{rev["table"]}"')
                        gross_profit = float(cur.fetchone()[0] or 0)
                    finally:
                        conn.close()
                    # NOTE: revenue/cost columns come from the same workspace asset
                    # table (discover_available_data is workspace-scoped).
                    if total_revenue > 0:
                        gross_margin = (gross_profit / total_revenue * 100)
        except Exception:
            pass
        return OverviewKPI(
            total_revenue=round(float(total_revenue), 2),
            total_units_sold=int(total_units),
            gross_margin_pct=round(float(gross_margin), 1) if gross_margin else None,
            total_marketing_spend=round(float(total_spend), 2),
            avg_roas=round(float(avg_roas), 2) if avg_roas else None,
            total_customers=total_customers,
            revenue_growth_pct=None, units_growth_pct=None,
            margin_growth_pct=None, spend_growth_pct=None,
            roas_growth_pct=None, customer_growth_pct=None,
        )
    except Exception as e:
        logger.warning(f"Dynamic overview failed: {e}")
        return OverviewKPI(
            total_revenue=0, total_units_sold=0, gross_margin_pct=None,
            total_marketing_spend=0, avg_roas=None, total_customers=0,
            revenue_growth_pct=None, units_growth_pct=None,
            margin_growth_pct=None, spend_growth_pct=None,
            roas_growth_pct=None, customer_growth_pct=None,
        )


@app.get("/api/analytics/revenue-trend", response_model=list[MonthlyRevenueTrend])
def revenue_trend(workspace_id: str = "default"):
    """Revenue trend — workspace data only."""
    if not has_workspace_data(workspace_id):
        return []
    try:
        trend = workspace_revenue_trend(workspace_id)
        return [MonthlyRevenueTrend(month=r["month"], revenue=round(float(r["revenue"]), 2),
                                     units_sold=0, profit=0) for r in trend]
    except Exception:
        return []


@app.get("/api/analytics/category-performance", response_model=list[CategoryPerformance])
def category_perf(workspace_id: str = "default"):
    """Category performance — workspace data only."""
    if not has_workspace_data(workspace_id):
        return []
    try:
        for dim in ["category", "product"]:
            rows = workspace_revenue_by_dimension(dim, workspace_id)
            if rows:
                return [CategoryPerformance(
                    category=str(r.get("dimension", "Unknown")),
                    revenue=round(float(r.get("revenue", 0)), 2),
                    units_sold=0, gross_profit=0,
                    gross_margin_pct=None, avg_discount_pct=None,
                    campaign_count=0, total_spend=0, total_roas=None,
                ) for r in rows]
    except Exception:
        pass
    return []


@app.get("/api/campaigns", response_model=list[CampaignListItem])
def list_campaigns(workspace_id: str = "default"):
    """Campaigns — workspace data only."""
    if not has_workspace_data(workspace_id):
        return []
    try:
        data = discover_available_data(workspace_id)
        # Find campaign-related data from semantic mappings
        conv_entries = data["available_measures"].get("conversions", [])
        spend_entries = data["available_measures"].get("spend", [])
        rev_entries = data["available_measures"].get("attribution_revenue", []) or data["available_measures"].get("revenue", [])
        # Find channel/campaign dimensions
        campaign_dims = data["available_dimensions"].get("campaign", []) or data["available_dimensions"].get("product", [])
        campaign_dims = data["available_dimensions"].get("campaign", []) or data["available_dimensions"].get("product", [])
        if conv_entries and spend_entries and campaign_dims:
            # Build campaign data from semantic mappings
            conv = conv_entries[0]
            spend = spend_entries[0]
            dim = campaign_dims[0]
            if conv["table"] == spend["table"] and dim["table"] == conv["table"]:
                _ssi(conv["table"])
                _ssi(conv["column"])
                _ssi(spend["column"])
                _ssi(dim["column"])
                rev_col = rev_entries[0]["column"] if rev_entries and rev_entries[0]["table"] == conv["table"] else None
                conn = _get_pg_connection()
                try:
                    cur = conn.cursor()
                    if rev_col:
                        _ssi(rev_col)
                        cur.execute(f"""
                            SELECT "{dim["column"]}" AS campaign_name,
                                   SUM("{spend["column"]}") AS spend,
                                   SUM("{conv["column"]}") AS conversions,
                                   SUM("{rev_col}") AS attributed_revenue
                            FROM "{conv["table"]}"
                            WHERE "{dim["column"]}" IS NOT NULL
                            GROUP BY "{dim["column"]}" ORDER BY spend DESC LIMIT 50
                        """)
                    else:
                        cur.execute(f"""
                            SELECT "{dim["column"]}" AS campaign_name,
                                   SUM("{spend["column"]}") AS spend,
                                   SUM("{conv["column"]}") AS conversions
                            FROM "{conv["table"]}"
                            WHERE "{dim["column"]}" IS NOT NULL
                            GROUP BY "{dim["column"]}" ORDER BY spend DESC LIMIT 50
                        """)
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                    result = []
                    for i, r in enumerate(rows):
                        spend_val = float(r.get("spend", 0))
                        conv_val = float(r.get("conversions", 0))
                        rev_val = float(r.get("attributed_revenue", 0)) if "attributed_revenue" in r else 0
                        result.append({
                            "campaign_id": f"ws_{i}",
                            "campaign_name": str(r.get("campaign_name", "Unknown")),
                            "product_id": "", "channel": "", "start_date": "", "end_date": "",
                            "impressions": 0, "clicks": 0, "spend": spend_val,
                            "conversions": int(conv_val), "attributed_revenue": rev_val,
                            "ctr": None, "conversion_rate": None,
                            "cpc": None, "cpa": round(spend_val / conv_val, 2) if conv_val > 0 else None,
                            "roas": round(rev_val / spend_val, 2) if spend_val > 0 else None,
                        })
                    return result
                finally:
                    conn.close()
    except Exception:
        pass
    return []


@app.get("/api/campaigns/{campaign_id}", response_model=CampaignListItem)
def get_campaign(campaign_id: str):
    raise HTTPException(status_code=404, detail="Campaign not found. Campaigns are dynamically generated from uploaded data.")


@app.get("/api/products", response_model=list[ProductListItem])
def list_products(workspace_id: str = "default"):
    """Products — workspace data only."""
    if not has_workspace_data(workspace_id):
        return []
    try:
        top = workspace_top_entities(limit=50, workspace_id=workspace_id)
        return [ProductListItem(
            product_id=f"ws_{i}", product_name=str(r.get("name", "Unknown")),
            category="", subcategory="", price=0, cost=0, rating=None,
            review_count=0,
            total_revenue=round(float(r.get("revenue", 0)), 2),
            total_units_sold=0, gross_margin_pct=None, avg_discount_pct=None,
            total_marketing_spend=0, product_roas=None,
        ) for i, r in enumerate(top)]
    except Exception:
        return []


@app.get("/api/products/{product_id}")
def get_product_detail(product_id: str):
    raise HTTPException(status_code=404, detail="Product not found. Products are dynamically generated from uploaded data.")


@app.get("/api/customers/segments", response_model=list[CustomerSegment])
def customer_segments(workspace_id: str = "default"):
    """Customer segments — workspace data only."""
    if not has_workspace_data(workspace_id):
        return []
    try:
        data = discover_available_data(workspace_id)
        cust_dim = data["available_dimensions"].get("customer", []) or data["available_dimensions"].get("customer_name", [])
        if cust_dim:
            return []  # Dynamic customer segments from uploaded data
    except Exception:
        pass
    return []


@app.get("/api/evaluation/run", response_model=EvaluationResult)
def run_evaluation_endpoint():
    from src.evaluation.eval_runner import run_evaluation
    out = run_evaluation(verbose=False)
    s = out["summary"]
    return EvaluationResult(
        total_cases=s["total_cases"],
        query_type_accuracy=s["query_type_accuracy"],
        retrieval_recall_at_k=s["retrieval_recall_at_k"],
        avg_end_to_end_latency_ms=s["avg_end_to_end_latency_ms"],
        p95_end_to_end_latency_ms=s["p95_end_to_end_latency_ms"],
        by_bucket=s["by_bucket"],
        test_cases=out["results"],
    )


# ---------------------------------------------------------------------------
# Data Hub Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/datahub/upload")
def datahub_upload(file: UploadFile = File(...), workspace_id: str = Form("default")):
    ext = Path(file.filename).suffix.lower()
    STRUCTURED_EXTS = {".csv", ".xlsx", ".xls"}
    UNSTRUCTURED_EXTS = {".pdf", ".docx", ".doc", ".txt"}

    if ext in STRUCTURED_EXTS:
        try:
            result = dynamic_ingest(file.file.read(), file.filename, workspace_id)
            if _pipeline:
                _pipeline._cache.clear()
            try:
                from src.database.state_manager import get_cache_manager
                get_cache_manager().invalidate_workspace()
                from src.llm.query_cache import clear_all_caches
                clear_all_caches()
            except Exception:
                pass
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            logger.exception("DataHub upload failed")
            raise HTTPException(status_code=500, detail=str(e))
        return result

    if ext in UNSTRUCTURED_EXTS:
        file_bytes = file.file.read()
        # Workspace-prefixed storage so the same filename can exist in two
        # workspaces without colliding; chunk metadata is tagged with the owner.
        stored_name = f"{workspace_id}__{file.filename}" if workspace_id != "default" else file.filename
        stem = Path(stored_name).stem
        if ext == ".pdf":
            dest = Path(config.KB_DIR) / stored_name
        elif ext != ".md":
            try:
                if ext == ".txt":
                    md_content = file_bytes.decode("utf-8", errors="replace")
                elif ext in (".docx", ".doc"):
                    try:
                        import docx
                        doc = docx.Document(io.BytesIO(file_bytes))
                        md_content = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                    except ImportError:
                        md_content = file_bytes.decode("utf-8", errors="replace")
                else:
                    md_content = file_bytes.decode("utf-8", errors="replace")
                dest = Path(config.KB_DIR) / f"{stem}.md"
                dest.write_text(md_content, encoding="utf-8")
            except Exception:
                dest = Path(config.KB_DIR) / stored_name
                dest.write_bytes(file_bytes)
        else:
            dest = Path(config.KB_DIR) / stored_name
            dest.write_bytes(file_bytes)

        doc_id = stem
        try:
            with sql_layer.get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO documents (document_id, document_name, document_type, file_path, chunk_count, workspace_id, status) "
                    "VALUES (%s, %s, %s, %s, 0, %s, 'processing') "
                    "ON CONFLICT (document_id) DO UPDATE SET status = 'processing'",
                    (doc_id, stem.replace("_", " ").title(), ext.lstrip("."), str(dest), workspace_id)
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to register document in DB: {e}")

        asset_id = f"kb_{doc_id}"
        try:
            with sql_layer.get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO assets (asset_id, workspace_id, name, type, source_type, status, row_count, size_bytes, table_name) "
                    "VALUES (%s, %s, %s, 'unstructured', %s, 'ready', 0, %s, NULL) "
                    "ON CONFLICT (asset_id) DO UPDATE SET status = 'ready', size_bytes = EXCLUDED.size_bytes, updated_at = NOW()",
                    (asset_id, workspace_id, file.filename, ext.lstrip("."), len(file_bytes))
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to register asset: {e}")

        try:
            _pipeline.reindex()
        except Exception as e:
            logger.warning(f"Reindex after unstructured upload failed: {e}")

        return {
            "dataset_ids": [asset_id],
            "profiles": [{
                "dataset_id": asset_id,
                "filename": file.filename,
                "file_type": ext.lstrip("."),
                "file_size_bytes": len(file_bytes),
                "row_count": 0,
                "col_count": 0,
                "duplicate_rows": 0,
                "quality_score": 100,
                "uploaded_at": datetime.now().isoformat(),
                "sheet_name": None,
                "columns": [],
                "issues": [],
            }],
            "total_rows": 0,
            "total_columns": 0,
        }

    raise HTTPException(status_code=422, detail=f"Unsupported type '{ext}'. Use .csv, .xlsx, .xls, .pdf, .docx, .doc, or .txt")


@app.get("/api/datahub/datasets")
def datahub_list(workspace_id: str = "default"):
    return dynamic_list_datasets(workspace_id)


@app.get("/api/datahub/datasets/{dataset_id}")
def datahub_detail(dataset_id: str, workspace_id: str = "default"):
    ds = dynamic_get_dataset(dataset_id, workspace_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


@app.delete("/api/datahub/datasets/{dataset_id}")
def datahub_delete(dataset_id: str, workspace_id: str = "default"):
    if not dynamic_delete_dataset(dataset_id, workspace_id):
        raise HTTPException(status_code=404, detail="Dataset not found")
    if _pipeline:
        _pipeline._cache.clear()
    try:
        from src.database.state_manager import get_cache_manager
        get_cache_manager().invalidate_workspace()
        from src.llm.query_cache import clear_all_caches
        clear_all_caches()
    except Exception:
        pass
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Reviews Analytics
# ---------------------------------------------------------------------------

@app.get("/api/analytics/reviews")
def reviews_overview(workspace_id: str = "default"):
    """Reviews — workspace data only. Computes from actual data if rating column exists."""
    if not has_workspace_data(workspace_id):
        return {"total_reviews": 0, "avg_rating": None, "negative_count": 0,
                "negative_pct": 0, "by_rating": [], "top_negative_themes": []}
    try:
        data = discover_available_data(workspace_id)
        rating_entries = data["available_measures"].get("rating", [])
        if not rating_entries:
            return {"total_reviews": 0, "avg_rating": None, "negative_count": 0,
                    "negative_pct": 0, "by_rating": [], "top_negative_themes": []}
        entry = rating_entries[0]
        _ssi(entry["table"])
        _ssi(entry["column"])
        conn = _get_pg_connection()
        try:
            cur = conn.cursor()
            cur.execute(f'SELECT COUNT(*), AVG("{entry["column"]}") FROM "{entry["table"]}" WHERE "{entry["column"]}" IS NOT NULL')
            row = cur.fetchone()
            total = int(row[0] or 0)
            avg_rating = float(row[1]) if row[1] else None
            negative = 0
            if avg_rating is not None:
                cur.execute(f'SELECT COUNT(*) FROM "{entry["table"]}" WHERE "{entry["column"]}" < 3')
                negative = int(cur.fetchone()[0] or 0)
            negative_pct = round(100 * negative / total, 1) if total > 0 else 0
            return {"total_reviews": total, "avg_rating": round(avg_rating, 2) if avg_rating else None,
                    "negative_count": negative, "negative_pct": negative_pct,
                    "by_rating": [], "top_negative_themes": []}
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Reviews overview failed: {e}")
        return {"total_reviews": 0, "avg_rating": None, "negative_count": 0,
                "negative_pct": 0, "by_rating": [], "top_negative_themes": []}


# ---------------------------------------------------------------------------
# Discount Analytics
# ---------------------------------------------------------------------------

@app.get("/api/analytics/discounts")
def discount_analytics(workspace_id: str = "default"):
    """Discount analytics — workspace data only. Computes from actual data if discount column exists."""
    if not has_workspace_data(workspace_id):
        return {"overall_avg_discount": 0, "discount_bands": [], "margin_by_band": []}
    try:
        data = discover_available_data(workspace_id)
        discount_entries = data["available_measures"].get("discount", [])
        if not discount_entries:
            return {"overall_avg_discount": 0, "discount_bands": [], "margin_by_band": []}
        entry = discount_entries[0]
        _ssi(entry["table"])
        _ssi(entry["column"])
        conn = _get_pg_connection()
        try:
            cur = conn.cursor()
            cur.execute(f'SELECT AVG("{entry["column"]}") FROM "{entry["table"]}" WHERE "{entry["column"]}" IS NOT NULL')
            avg_discount = float(cur.fetchone()[0] or 0)
            return {"overall_avg_discount": round(avg_discount, 2), "discount_bands": [], "margin_by_band": []}
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Discount analytics failed: {e}")
        return {"overall_avg_discount": 0, "discount_bands": [], "margin_by_band": []}


# ---------------------------------------------------------------------------
# Data Status
# ---------------------------------------------------------------------------

@app.get("/api/data-status")
def data_status(workspace_id: str = "default"):
    """Return whether structured data and knowledge base exist.
    CRITICAL: Only report workspace-uploaded data.
    """
    from src.ingestion.document_loader import _chunk_workspace_id
    status = {"structured": {}, "knowledge": {}, "has_data": False, "has_workspace_data": False}
    try:
        workspace_has = has_workspace_data(workspace_id)
        status["has_workspace_data"] = workspace_has

        tables = {}
        if workspace_has:
            try:
                assets = get_workspace_tables(workspace_id)
                for a in assets:
                    tables[a["table_name"]] = a.get("row_count", 0)
            except Exception:
                pass
            status["has_data"] = len(tables) > 0 and any(v > 0 for v in tables.values())
        else:
            status["has_data"] = False

        status["structured"] = tables
    except Exception:
        status["structured"] = {"error": "database unavailable"}

    try:
        docs = set()
        chunks = 0
        if _pipeline and _pipeline.vector_store:
            for c in _pipeline.vector_store.chunks:
                if _chunk_workspace_id(c) != workspace_id:
                    continue
                docs.add(c.document_id)
                chunks += 1
        status["knowledge"] = {"documents": len(docs), "chunks": chunks}
        status["has_knowledge"] = len(docs) > 0
    except Exception:
        status["knowledge"] = {"error": "vector store unavailable"}
        status["has_knowledge"] = False
    return status


# ---------------------------------------------------------------------------
# System Health / Observability
# ---------------------------------------------------------------------------

@app.get("/api/system/health")
def system_health():
    import time
    checks = {}
    checks["api"] = {"status": "healthy", "latency_ms": 0}
    try:
        t0 = time.time()
        with sql_layer.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        checks["database"] = {"status": "healthy", "latency_ms": round((time.time() - t0) * 1000, 2)}
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)[:200]}
    try:
        t0 = time.time()
        _pipeline.vector_store.search("test", top_k=1)
        checks["vector_search"] = {"status": "healthy", "latency_ms": round((time.time() - t0) * 1000, 2),
                                     "chunks": len(_pipeline.vector_store.chunks)}
    except Exception as e:
        checks["vector_search"] = {"status": "error", "error": str(e)}
    checks["llm"] = {"status": "healthy", "backend": config.LLM_BACKEND, "model": config.OLLAMA_MODEL if config.LLM_BACKEND == "ollama" else "template-fallback"}
    try:
        import redis as _redis
        import os as _os
        t0 = time.time()
        r = _redis.from_url(_os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
        r.ping()
        checks["redis"] = {"status": "healthy", "latency_ms": round((time.time() - t0) * 1000, 2)}
    except Exception as e:
        checks["redis"] = {"status": "not_configured", "message": str(e)[:100]}
    from src import config as _cfg
    if _cfg.USE_POSTGRESQL:
        try:
            import psycopg2
            t0 = time.time()
            pg_conn = psycopg2.connect(_cfg.DATABASE_URL)
            pg_conn.cursor().execute("SELECT 1")
            pg_conn.close()
            checks["postgresql"] = {"status": "healthy", "latency_ms": round((time.time() - t0) * 1000, 2), "url": _cfg.DATABASE_URL.split("@")[-1] if "@" in _cfg.DATABASE_URL else "configured"}
        except Exception as e:
            checks["postgresql"] = {"status": "error", "error": str(e)[:200]}
    else:
        checks["postgresql"] = {"status": "not_configured", "message": "Using SQLite fallback"}
    return checks


# ---------------------------------------------------------------------------
# AI Insights & Recommendations
# ---------------------------------------------------------------------------

@app.post("/api/insights")
def generate_insights(workspace_id: str = "default"):
    """Generate proactive business insights from workspace data."""
    if not has_workspace_data(workspace_id):
        return {
            "insights": [{
                "type": "info", "title": "No Data Available",
                "description": "Upload sales or marketing data to generate insights.",
                "impact": "low", "confidence": "high",
                "evidence": ["No uploaded data in workspace"],
            }],
            "count": 1,
        }

    try:
        overview = generate_dynamic_overview(workspace_id)
        trend = overview.get("trend", [])
        breakdowns = overview.get("breakdowns", {})
        insights = []

        if len(trend) >= 3:
            last_3 = [t.get("revenue", 0) for t in trend[-3:]]
            if all(isinstance(v, (int, float)) for v in last_3):
                if all(last_3[i] < last_3[i-1] for i in range(1, len(last_3))):
                    decline_pct = round((last_3[0] - last_3[-1]) / last_3[0] * 100, 1) if last_3[0] else 0
                    insights.append({
                        "type": "warning", "title": "Declining Trend Detected",
                        "description": f"Revenue has declined for {len(last_3)} consecutive periods ({decline_pct}% cumulative decline).",
                        "impact": "high", "confidence": "high",
                        "evidence": [f"Last 3 periods: {', '.join(f'${v:,.0f}' for v in last_3)}"],
                    })

        for dim_name, dim_data in breakdowns.items():
            if dim_data and len(dim_data) >= 2:
                top = dim_data[0]
                bottom = dim_data[-1]
                top_val = top.get("revenue", 0)
                bottom_val = bottom.get("revenue", 0)
                if top_val and bottom_val and bottom_val > 0 and top_val > bottom_val * 3:
                    insights.append({
                        "type": "info",
                        "title": f"{dim_name.title()} Imbalance Detected",
                        "description": f"'{top.get('dimension', 'N/A')}' has {top_val/bottom_val:.1f}x more revenue than '{bottom.get('dimension', 'N/A')}'.",
                        "impact": "medium", "confidence": "high",
                        "evidence": [f"Top: {top.get('dimension')}: ${top_val:,.0f}", f"Bottom: {bottom.get('dimension')}: ${bottom_val:,.0f}"],
                    })

    except Exception as e:
        logger.warning(f"Insight generation error: {e}")
        insights = []

    if not insights:
        insights.append({
            "type": "info", "title": "Data Analyzed",
            "description": "Your workspace data was analyzed but no significant patterns were detected.",
            "impact": "low", "confidence": "high",
            "evidence": ["Workspace data analyzed"],
        })

    return {"insights": insights, "count": len(insights)}


@app.post("/api/executive-brief")
def executive_brief(workspace_id: str = "default"):
    """Generate a structured executive brief from workspace data."""
    if not has_workspace_data(workspace_id):
        return {
            "sections": [{
                "title": "No Data Available",
                "content": "Upload sales or marketing data to generate an executive brief.",
            }],
            "generated_at": datetime.now().isoformat(),
        }

    total_revenue = workspace_total_revenue(workspace_id) or 0
    total_units = workspace_total_quantity(workspace_id) or 0
    total_spend = workspace_total_spend(workspace_id) or 0

    sections = [
        {
            "title": "Business Performance",
            "content": f"Total revenue: ${total_revenue:,.0f} across {int(total_units):,} units. Total marketing spend: ${total_spend:,.0f}.",
        },
        {
            "title": "Data Sources",
            "content": f"Analysis based on {workspace_row_count(workspace_id)} records from uploaded workspace data.",
        },
    ]
    return {"sections": sections, "generated_at": datetime.now().isoformat()}


# ---------------------------------------------------------------------------
# Investigation Workspace
# ---------------------------------------------------------------------------

@app.get("/api/investigation/{metric}")
def investigate_metric(metric: str, workspace_id: str = "default"):
    """Drill-down investigation for a specific metric — workspace data only."""
    result = {"metric": metric, "breakdowns": {}, "trend": [], "top_entities": []}
    try:
        dynamic = generate_dynamic_overview(workspace_id)
        if dynamic.get("breakdowns"):
            for dim_name, dim_data in dynamic["breakdowns"].items():
                result["breakdowns"][f"by_{dim_name}"] = dim_data
        if dynamic.get("trend"):
            result["trend"] = dynamic["trend"]
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Action & Outcome Tracking (PostgreSQL)
# ---------------------------------------------------------------------------

@app.get("/api/actions")
def list_actions():
    with sql_layer.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, title, description, owner, status, source_insight, expected_outcome, actual_outcome, created_at, updated_at FROM actions ORDER BY created_at DESC")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            for k in ("created_at", "updated_at"):
                if r.get(k):
                    r[k] = str(r[k])
    return {"actions": rows, "count": len(rows)}

@app.post("/api/actions")
def create_action(action: dict):
    action_id = f"act_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    with sql_layer.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO actions (id, title, description, owner, status, source_insight, expected_outcome, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, 'open', %s, %s, %s, %s)""",
                    (action_id, action.get("title", "Untitled Action"), action.get("description", ""),
                     action.get("owner", "Unassigned"), action.get("source_insight", ""),
                     action.get("expected_outcome", ""), now, now))
        conn.commit()
    return {"id": action_id, "title": action.get("title", "Untitled Action"),
            "description": action.get("description", ""), "owner": action.get("owner", "Unassigned"),
            "status": "open", "created_at": now}

@app.put("/api/actions/{action_id}")
def update_action(action_id: str, update: dict):
    with sql_layer.get_conn() as conn:
        cur = conn.cursor()
        if "status" in update:
            cur.execute("UPDATE actions SET status = %s, updated_at = NOW() WHERE id = %s", (update["status"], action_id))
        if "actual_outcome" in update:
            cur.execute("UPDATE actions SET actual_outcome = %s, updated_at = NOW() WHERE id = %s", (update["actual_outcome"], action_id))
        conn.commit()
        cur.execute("SELECT id, title, status, actual_outcome, updated_at FROM actions WHERE id = %s", (action_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Action not found")
        cols = [d[0] for d in cur.description]
        result = dict(zip(cols, row))
        result["updated_at"] = str(result["updated_at"]) if result.get("updated_at") else None
    return result

@app.delete("/api/actions/{action_id}")
def delete_action(action_id: str):
    with sql_layer.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM actions WHERE id = %s", (action_id,))
        conn.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Data Center — Unified Data Asset Registry
# ---------------------------------------------------------------------------

@app.get("/api/data-center")
def data_center(workspace_id: str = "default"):
    """Unified registry of structured + unstructured data assets — workspace data only."""
    from src.ingestion.document_loader import _chunk_workspace_id
    assets = []
    try:
        dynamic_ds = dynamic_list_datasets(workspace_id)
        for ds in dynamic_ds:
            assets.append({
                "id": f"datahub_{ds.get('dataset_id', ds.get('filename', 'unknown'))}",
                "name": ds.get('filename', 'Unknown'),
                "type": "structured",
                "category": ds.get('domain', 'uploaded_dataset'),
                "source": "DataHub",
                "status": ds.get('status', 'ready'),
                "row_count": ds.get('total_rows', 0),
                "metadata": ds,
            })
    except Exception:
        pass

    try:
        docs = {}
        for c in (_pipeline.vector_store.chunks if _pipeline else []):
            if _chunk_workspace_id(c) != workspace_id:
                continue
            if c.document_id not in docs:
                docs[c.document_id] = {
                    "id": f"kb_{c.document_id}",
                    "name": c.document_name,
                    "type": "unstructured",
                    "category": "knowledge_base",
                    "source": c.document_type,
                    "status": "indexed",
                    "chunk_count": 0,
                    "metadata": {"document_id": c.document_id,
                                  "document_type": c.document_type,
                                  "source_path": c.metadata.get("source_path", "")},
                }
            docs[c.document_id]["chunk_count"] += 1
        assets.extend(docs.values())
    except Exception as e:
        assets.append({"id": "kb_error", "name": "Knowledge Base", "type": "unstructured",
                       "status": "error", "metadata": {"error": str(e)}})

    return {
        "assets": assets,
        "total": len(assets),
        "structured_count": len([a for a in assets if a.get("type") == "structured"]),
        "unstructured_count": len([a for a in assets if a.get("type") == "unstructured"]),
    }


@app.get("/api/data-center/{asset_id}")
def get_data_center_asset(asset_id: str, workspace_id: str = "default"):
    """Get a single data center asset by ID."""
    from src.ingestion.document_loader import _chunk_workspace_id
    if asset_id.startswith("datahub_"):
        dataset_id = asset_id.replace("datahub_", "", 1)
        try:
            ds_list = dynamic_list_datasets(workspace_id)
            for ds in ds_list:
                if ds.get('dataset_id') == dataset_id or ds.get('filename') == dataset_id:
                    return {
                        "id": f"datahub_{ds.get('dataset_id', dataset_id)}",
                        "name": ds.get('filename', 'Unknown'),
                        "type": "structured",
                        "category": ds.get('domain', 'uploaded_dataset'),
                        "source": "DataHub",
                        "status": ds.get('status', 'ready'),
                        "row_count": ds.get('total_rows', 0),
                        "metadata": ds,
                    }
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="Dataset not found")

    if asset_id.startswith("kb_"):
        document_id = asset_id.replace("kb_", "", 1)
        if _pipeline:
            for c in _pipeline.vector_store.chunks:
                if c.document_id == document_id and _chunk_workspace_id(c) == workspace_id:
                    return {
                        "id": f"kb_{c.document_id}",
                        "name": c.document_name,
                        "type": "unstructured",
                        "category": "knowledge_base",
                        "source": c.document_type,
                        "status": "indexed",
                        "metadata": {"document_id": c.document_id, "document_type": c.document_type},
                    }
        raise HTTPException(status_code=404, detail="Document not found")

    raise HTTPException(status_code=404, detail="Asset not found")


@app.delete("/api/data-center/{asset_id}")
def delete_data_center_asset(asset_id: str, workspace_id: str = "default"):
    """Delete a data center asset."""
    if asset_id.startswith("datahub_"):
        dataset_id = asset_id.replace("datahub_", "", 1)
        if dynamic_delete_dataset(dataset_id, workspace_id):
            if _pipeline:
                _pipeline._cache.clear()
            return {"deleted": True, "type": "structured"}
        raise HTTPException(status_code=404, detail="Dataset not found")

    if asset_id.startswith("kb_"):
        document_id = asset_id.replace("kb_", "", 1)
        # Ownership check: only the owning workspace may delete a document
        try:
            with sql_layer.get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM documents WHERE document_id = %s AND workspace_id = %s",
                            (document_id, workspace_id))
                owned = cur.fetchone() is not None
        except Exception:
            owned = False
        if not owned:
            raise HTTPException(status_code=404, detail="Document not found")
        for ext in [".md", ".pdf", ".txt", ".docx", ".doc"]:
            p = Path(config.KB_DIR) / f"{document_id}{ext}"
            if p.exists():
                p.unlink()
        try:
            with sql_layer.get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT chunk_id FROM document_chunks WHERE document_id = %s", (document_id,))
                chunk_ids = [r[0] for r in cur.fetchall()]
                if chunk_ids:
                    cur.execute("DELETE FROM embeddings WHERE chunk_id = ANY(%s)", (chunk_ids,))
                cur.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))
                cur.execute("DELETE FROM documents WHERE document_id = %s", (document_id,))
                cur.execute("DELETE FROM assets WHERE asset_id = %s", (f"kb_{document_id}",))
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to clean up DB records for document {document_id}: {e}")
        if _pipeline:
            _pipeline.reindex()
        return {"deleted": True, "type": "unstructured"}

    raise HTTPException(status_code=404, detail="Asset not found")


# ---------------------------------------------------------------------------
# Semantic Layer
# ---------------------------------------------------------------------------

@app.get("/api/semantic/metrics")
def semantic_metrics(workspace_id: str = "default"):
    """Dynamic semantic metrics from uploaded data only."""
    metrics = []
    try:
        data = discover_available_data(workspace_id)
        for concept, entries in data.get("available_measures", {}).items():
            for e in entries:
                metrics.append({
                    "name": concept.replace("_", " ").title(),
                    "definition": f"Dynamic metric from {e['table']}.{e['column']}",
                    "formula": f"SUM({e['column']})",
                    "source": e["table"],
                    "dimensions": [],
                })
    except Exception:
        pass
    return {"metrics": metrics, "count": len(metrics)}

@app.get("/api/semantic/dimensions")
def semantic_dimensions(workspace_id: str = "default"):
    """Dynamic semantic dimensions from uploaded data only."""
    dimensions = []
    try:
        data = discover_available_data(workspace_id)
        for concept, entries in data.get("available_dimensions", {}).items():
            for e in entries:
                dimensions.append({
                    "name": concept.replace("_", " ").title(),
                    "columns": [e["column"]],
                    "source": e["table"],
                })
    except Exception:
        pass
    return {"dimensions": dimensions, "count": len(dimensions)}


# ---------------------------------------------------------------------------
# Data Quality — Dynamic
# ---------------------------------------------------------------------------

@app.get("/api/data-quality")
def data_quality(workspace_id: str = "default"):
    """Dynamic data quality — inspects uploaded workspace tables only."""
    report = {"tables": {}, "overall_score": 0, "total_checks": 0, "passed_checks": 0}

    if not has_workspace_data(workspace_id):
        return report

    try:
        tables_data = get_workspace_tables(workspace_id)
        if not tables_data:
            return report

        total_checks = 0
        passed_checks = 0

        conn = _get_pg_connection()
        try:
            cur = conn.cursor()
            for t in tables_data:
                table_name = t.get("table_name")
                if not table_name:
                    continue
                _ssi(table_name)
                try:
                    cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                    total = cur.fetchone()[0]
                except Exception:
                    continue

                # Get column names dynamically
                cur.execute(f'SELECT * FROM "{table_name}" LIMIT 0')
                columns = [desc[0] for desc in cur.description]

                table_report = {"total_rows": total, "checks": [], "duplicate_count": 0}
                for col in columns:
                    try:
                        cur.execute(f'SELECT COUNT(*) FROM "{table_name}" WHERE "{col}" IS NULL OR "{col}" = \'\'' )
                        nulls = cur.fetchone()[0]
                        total_checks += 1
                        pct = round(100 * (total - nulls) / total, 1) if total > 0 else 100
                        passed = pct >= 90
                        if passed:
                            passed_checks += 1
                        table_report["checks"].append({
                            "column": col, "null_count": nulls, "completeness": pct,
                            "status": "pass" if passed else "warn",
                        })
                    except Exception:
                        pass

                # Duplicate check using first column as heuristic
                if columns:
                    try:
                        cur.execute(f'SELECT COUNT(*) - COUNT(DISTINCT "{columns[0]}") FROM "{table_name}"')
                        dups = cur.fetchone()[0]
                        table_report["duplicate_count"] = dups
                    except Exception:
                        pass

                report["tables"][table_name] = table_report
        finally:
            conn.close()

        report["overall_score"] = round(100 * passed_checks / total_checks, 1) if total_checks > 0 else 100
        report["total_checks"] = total_checks
        report["passed_checks"] = passed_checks
    except Exception as e:
        logger.warning(f"Data quality check failed: {e}")

    return report


# ---------------------------------------------------------------------------
# Global Search
# ---------------------------------------------------------------------------

@app.get("/api/search")
def global_search(q: str = "", workspace_id: str = "default"):
    from src.ingestion.document_loader import _chunk_workspace_id
    if not q.strip():
        return {"results": [], "total": 0}
    results = []
    ql = q.lower()

    # Search workspace assets
    try:
        ds_list = dynamic_list_datasets(workspace_id)
        for ds in ds_list:
            fn = (ds.get("filename") or "").lower()
            if ql in fn:
                results.append({"type": "dataset", "id": ds.get("dataset_id", ""), "title": ds.get("filename", ""), "subtitle": f"{ds.get('total_rows', 0)} rows"})
    except Exception:
        pass

    # Search documents (own workspace only)
    for doc in (_pipeline.vector_store.chunks if _pipeline else []):
        if _chunk_workspace_id(doc) != workspace_id:
            continue
        if ql in doc.document_name.lower() or ql in doc.text[:200].lower():
            results.append({"type": "document", "id": doc.document_id, "title": doc.document_name, "subtitle": doc.document_type})
            break

    return {"results": results[:20], "total": len(results)}


# ---------------------------------------------------------------------------
# Conversation Persistence (PostgreSQL)
# ---------------------------------------------------------------------------


@app.get("/api/conversations")
def list_conversations(workspace_id: str = "default"):
    with sql_layer.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE workspace_id = %s ORDER BY updated_at DESC",
                    (workspace_id,))
        rows = cur.fetchall()
        convos = []
        for r in rows:
            r = _to_dict(r, cur)
            cur2 = conn.cursor()
            cur2.execute("SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = %s", (r["id"],))
            msg_count = cur2.fetchone()[0]
            convos.append({
                "id": r["id"], "title": r["title"], "message_count": msg_count,
                "created_at": str(r["created_at"]), "updated_at": str(r["updated_at"]),
            })
    return {"conversations": convos}


@app.post("/api/conversations")
def create_conversation(workspace_id: str = "default"):
    cid = f"conv_{uuid.uuid4().hex[:12]}"
    now = datetime.now().isoformat()
    with sql_layer.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO conversations (id, title, workspace_id, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)",
                    (cid, "New Conversation", workspace_id, now, now))
        conn.commit()
    return {"id": cid, "workspace_id": workspace_id, "message_count": 0}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str, workspace_id: str = "default"):
    with sql_layer.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, title, workspace_id, created_at, updated_at FROM conversations WHERE id = %s AND workspace_id = %s",
                    (conversation_id, workspace_id))
        conv = cur.fetchone()
        if not conv:
            # Cross-workspace access must look like "not found" — never leak existence.
            raise HTTPException(status_code=404, detail="Conversation not found")
        conv = _to_dict(conv, cur)
        cur.execute("SELECT role, content, result FROM conversation_messages WHERE conversation_id = %s ORDER BY id", (conversation_id,))
        messages = []
        for m in cur.fetchall():
            m = _to_dict(m, cur)
            result = None
            if m.get("result"):
                result = json.loads(m["result"]) if isinstance(m["result"], str) else m["result"]
            messages.append({"role": m["role"], "content": m["content"], "result": result})
        conv["messages"] = messages
        return conv


@app.post("/api/conversations/{conversation_id}/messages")
def add_message(conversation_id: str, message: dict, workspace_id: str = "default"):
    role = message.get("role", "user")
    content = message.get("content", "")
    now = datetime.now().isoformat()

    with sql_layer.get_conn() as conn:
        cur = conn.cursor()
        # Ownership check before writing — no writing into another workspace's thread
        cur.execute("SELECT 1 FROM conversations WHERE id = %s AND workspace_id = %s",
                    (conversation_id, workspace_id))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        result_json = None
        if message.get("result"):
            result_json = json.dumps(message["result"])
        cur.execute("INSERT INTO conversation_messages (conversation_id, role, content, result) VALUES (%s, %s, %s, %s)",
                    (conversation_id, role, content, result_json))
        cur.execute("UPDATE conversations SET updated_at = %s, title = CASE WHEN title = 'New Conversation' AND %s = 'user' THEN LEFT(%s, 100) ELSE title END WHERE id = %s",
                    (now, role, content, conversation_id))
        conn.commit()

        cur.execute("SELECT role, content, result FROM conversation_messages WHERE conversation_id = %s ORDER BY id", (conversation_id,))
        messages = []
        for m in cur.fetchall():
            m = _to_dict(m, cur)
            result = None
            if m.get("result"):
                result = json.loads(m["result"]) if isinstance(m["result"], str) else m["result"]
            messages.append({"role": m["role"], "content": m["content"], "result": result})
    return {"id": conversation_id, "messages": messages}


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, workspace_id: str = "default"):
    with sql_layer.get_conn() as conn:
        cur = conn.cursor()
        # Only the owning workspace can delete its own conversation
        cur.execute("SELECT 1 FROM conversations WHERE id = %s AND workspace_id = %s",
                    (conversation_id, workspace_id))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        cur.execute("DELETE FROM conversation_messages WHERE conversation_id = %s", (conversation_id,))
        cur.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
        conn.commit()
    return {"deleted": True}
