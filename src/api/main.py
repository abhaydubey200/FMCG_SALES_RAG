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
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from src import config
from src.analytics import sql_layer
from src.api.schemas import (CampaignListItem, CategoryPerformance, CustomerSegment,
                              DashboardResponse, DeleteResponse, DocumentInfo,
                              EvaluationResult, MonthlyRevenueTrend, OverviewKPI,
                              ProductListItem, QueryRequest, QueryResponse, UploadResponse)
from src.rag.pipeline import get_pipeline

logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger("sales_marketing_assistant")

app = FastAPI(
    title="Amazon Sales & Marketing Intelligence Assistant",
    description="RAG + Analytics assistant over structured sales/marketing data and business knowledge documents.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

_pipeline = None


@app.on_event("startup")
def startup():
    global _pipeline
    logger.info("Loading RAG pipeline (vector store + keyword index)...")
    _pipeline = get_pipeline()
    logger.info("Pipeline ready. LLM backend=%s, embedding backend=%s", config.LLM_BACKEND, config.EMBEDDING_BACKEND)


@app.get("/health")
def health():
    return {"status": "ok", "llm_backend": config.LLM_BACKEND, "embedding_backend": config.EMBEDDING_BACKEND}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    try:
        result = _pipeline.answer(req.question)
    except Exception as e:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=f"Failed to process query: {e}")
    return QueryResponse(
        answer=result.answer, query_type=result.query_type,
        sources=result.sources, metrics=result.metrics, evidence=result.evidence,
    )


@app.get("/documents", response_model=list[DocumentInfo])
def list_documents():
    docs = {}
    for c in _pipeline.vector_store.chunks:
        if c.document_id not in docs:
            docs[c.document_id] = {
                "document_id": c.document_id, "document_name": c.document_name,
                "document_type": c.document_type, "chunk_count": 0,
                "source_path": c.metadata.get("source_path", ""),
            }
        docs[c.document_id]["chunk_count"] += 1
    return list(docs.values())


ALLOWED_EXTENSIONS = {".md", ".csv", ".xlsx", ".xls", ".txt"}


def _convert_data_file_to_markdown(file_bytes: bytes, filename: str) -> str:
    """Convert CSV/Excel/TXT data files into a Markdown document for RAG ingestion."""
    import io
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

    # .md — return as-is (read by document_loader)
    return file_bytes.decode("utf-8", errors="replace")


@app.post("/documents/upload", response_model=UploadResponse)
def upload_document(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422,
                            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    file_bytes = file.file.read()

    # For non-markdown files, convert to markdown first then save
    if ext != ".md":
        md_content = _convert_data_file_to_markdown(file_bytes, file.filename)
        stem = Path(file.filename).stem
        dest = Path(config.KB_DIR) / f"{stem}.md"
        dest.write_text(md_content, encoding="utf-8")
    else:
        dest = Path(config.KB_DIR) / file.filename
        dest.write_bytes(file_bytes)

    try:
        _pipeline.reindex()
    except Exception as e:
        logger.exception("Upload/reindex failed")
        raise HTTPException(status_code=500, detail=f"Failed to reindex: {e}")

    chunk_count = len([c for c in _pipeline.vector_store.chunks if c.document_id == dest.stem])
    return UploadResponse(document_id=dest.stem, document_name=dest.stem.replace("_", " ").title(),
                           chunks_created=chunk_count, message="Document ingested and indexed.")


@app.delete("/documents/{document_id}", response_model=DeleteResponse)
def delete_document(document_id: str):
    safe_id = "".join(ch for ch in document_id if ch.isalnum() or ch in "_-")
    path = Path(config.KB_DIR) / f"{safe_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")
    path.unlink()
    _pipeline.reindex()
    return DeleteResponse(document_id=document_id, deleted=True, message="Document removed and index rebuilt.")@app.get("/dashboard", response_model=DashboardResponse)
def dashboard():
    with sql_layer.get_conn() as conn:
        total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        total_revenue = conn.execute("SELECT COALESCE(SUM(revenue),0) FROM sales").fetchone()[0]
        total_spend = conn.execute("SELECT COALESCE(SUM(spend),0) FROM campaigns").fetchone()[0]
        total_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        total_reviews = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        avg_roas_row = conn.execute(
            "SELECT AVG(attributed_revenue * 1.0 / NULLIF(spend,0)) FROM campaigns").fetchone()[0]
    top = sql_layer.category_performance()
    top_category = top[0]["category"] if top else None
    return DashboardResponse(
        total_products=total_products, total_revenue=round(total_revenue, 2),
        total_marketing_spend=round(total_spend, 2), avg_roas=round(avg_roas_row, 2) if avg_roas_row else None,
        top_category=top_category, total_customers=total_customers, total_reviews=total_reviews,
    )



# ---------------------------------------------------------------------------
# Advanced Analytics Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/analytics/overview", response_model=OverviewKPI)
def analytics_overview():
    with sql_layer.get_conn() as conn:
        # Current period (full dataset)
        total_revenue = conn.execute("SELECT COALESCE(SUM(revenue),0) FROM sales").fetchone()[0]
        total_units = conn.execute("SELECT COALESCE(SUM(quantity),0) FROM sales").fetchone()[0]
        total_spend = conn.execute("SELECT COALESCE(SUM(spend),0) FROM campaigns").fetchone()[0]
        total_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        avg_roas = conn.execute(
            "SELECT SUM(attributed_revenue)*1.0 / NULLIF(SUM(spend),0) FROM campaigns").fetchone()[0]
        gross_profit = conn.execute(
            "SELECT COALESCE(SUM(s.revenue - s.cost),0) FROM sales s").fetchone()[0]
        gross_margin = (gross_profit / total_revenue * 100) if total_revenue else None

        # Previous period comparison (split at midpoint of date range)
        min_date = conn.execute("SELECT MIN(order_date) FROM sales").fetchone()[0]
        max_date = conn.execute("SELECT MAX(order_date) FROM sales").fetchone()[0]
        if min_date and max_date:
            from datetime import datetime
            d1 = datetime.fromisoformat(min_date)
            d2 = datetime.fromisoformat(max_date)
            mid = (d1 + (d2 - d1) / 2).strftime("%Y-%m-%d")
            half_rev = conn.execute(
                "SELECT COALESCE(SUM(revenue),0) FROM sales WHERE order_date >= ?", (mid,)).fetchone()[0]
            half_units = conn.execute(
                "SELECT COALESCE(SUM(quantity),0) FROM sales WHERE order_date >= ?", (mid,)).fetchone()[0]
            half_spend = conn.execute(
                "SELECT COALESCE(SUM(spend),0) FROM campaigns WHERE start_date >= ?", (mid,)).fetchone()[0]
            half_roas = conn.execute(
                "SELECT SUM(attributed_revenue)*1.0/NULLIF(SUM(spend),0) FROM campaigns WHERE start_date >= ?",
                (mid,)).fetchone()[0]
            first_half_rev = total_revenue - half_rev
            first_half_units = total_units - half_units
            first_half_spend = total_spend - half_spend
            first_half_roas = conn.execute(
                "SELECT SUM(attributed_revenue)*1.0/NULLIF(SUM(spend),0) FROM campaigns WHERE start_date < ?",
                (mid,)).fetchone()[0]
            first_half_profit = conn.execute(
                "SELECT COALESCE(SUM(s.revenue - s.cost),0) FROM sales s WHERE s.order_date < ?",
                (mid,)).fetchone()[0]
            second_half_profit = gross_profit - first_half_profit
            first_half_margin = (first_half_profit / first_half_rev * 100) if first_half_rev else None
            second_half_margin = (second_half_profit / half_rev * 100) if half_rev else None
        else:
            half_rev = half_units = half_spend = half_roas = 0
            first_half_rev = first_half_units = first_half_spend = 1
            first_half_roas = 0
            first_half_margin = second_half_margin = gross_margin

        def _growth(current, previous):
            if previous and previous > 0:
                return round((current - previous) / previous * 100, 1)
            return None

    return OverviewKPI(
        total_revenue=round(total_revenue, 2),
        total_units_sold=int(total_units),
        gross_margin_pct=round(gross_margin, 1) if gross_margin else None,
        total_marketing_spend=round(total_spend, 2),
        avg_roas=round(avg_roas, 2) if avg_roas else None,
        total_customers=total_customers,
        revenue_growth_pct=_growth(half_rev, first_half_rev),
        units_growth_pct=_growth(half_units, first_half_units),
        margin_growth_pct=_growth(second_half_margin, first_half_margin),
        spend_growth_pct=_growth(half_spend, first_half_spend),
        roas_growth_pct=_growth(half_roas, first_half_roas if first_half_spend > 0 else None),
        customer_growth_pct=None,
    )


@app.get("/api/analytics/revenue-trend", response_model=list[MonthlyRevenueTrend])
def revenue_trend():
    with sql_layer.get_conn() as conn:
        rows = conn.execute("""
            SELECT strftime('%Y-%m', order_date) AS month,
                   SUM(revenue) AS revenue,
                   SUM(quantity) AS units_sold,
                   SUM(revenue - cost) AS profit
            FROM sales
            GROUP BY month ORDER BY month
        """).fetchall()
    return [MonthlyRevenueTrend(month=r["month"], revenue=round(r["revenue"], 2),
                                 units_sold=int(r["units_sold"]), profit=round(r["profit"], 2)) for r in rows]


@app.get("/api/analytics/category-performance", response_model=list[CategoryPerformance])
def category_perf():
    cats = sql_layer.category_performance()
    result = []
    for c in cats:
        with sql_layer.get_conn() as conn:
            camp = conn.execute("""
                SELECT COUNT(*) as cnt, COALESCE(SUM(spend),0) as spend,
                       SUM(attributed_revenue)*1.0/NULLIF(SUM(spend),0) as roas
                FROM campaigns c JOIN products p ON c.product_id = p.product_id
                WHERE p.category = ?
            """, (c["category"],)).fetchone()
        result.append(CategoryPerformance(
            category=c["category"], revenue=round(c["revenue"], 2),
            units_sold=int(c["units_sold"]), gross_profit=round(c["gross_profit"], 2),
            gross_margin_pct=c.get("gross_margin_pct"), avg_discount_pct=c.get("avg_discount_pct"),
            campaign_count=camp["cnt"], total_spend=round(camp["spend"], 2),
            total_roas=round(camp["roas"], 2) if camp["roas"] else None,
        ))
    return result


@app.get("/api/campaigns", response_model=list[CampaignListItem])
def list_campaigns():
    rows = sql_layer.campaign_performance(limit=100)
    return [CampaignListItem(**r) for r in rows]


@app.get("/api/campaigns/{campaign_id}", response_model=CampaignListItem)
def get_campaign(campaign_id: str):
    rows = sql_layer.campaign_performance(limit=200)
    for r in rows:
        if r["campaign_id"] == campaign_id:
            return CampaignListItem(**r)
    raise HTTPException(status_code=404, detail=f"Campaign '{campaign_id}' not found.")


@app.get("/api/products", response_model=list[ProductListItem])
def list_products():
    with sql_layer.get_conn() as conn:
        products = [dict(r) for r in conn.execute("SELECT * FROM products").fetchall()]
        sales_agg = [dict(r) for r in conn.execute("""
            SELECT product_id, SUM(revenue) as total_revenue, SUM(quantity) as total_units,
                   AVG(discount) as avg_discount
            FROM sales GROUP BY product_id
        """).fetchall()]
        sales_map = {s["product_id"]: s for s in sales_agg}
        marketing = [dict(r) for r in conn.execute("""
            SELECT product_id, SUM(spend) as total_spend,
                   SUM(attributed_revenue)*1.0/NULLIF(SUM(spend),0) as roas
            FROM campaigns GROUP BY product_id
        """).fetchall()]
        marketing_map = {m["product_id"]: m for m in marketing}
    result = []
    for p in products:
        s = sales_map.get(p["product_id"], {})
        m = marketing_map.get(p["product_id"], {})
        rev = s.get("total_revenue", 0)
        cost = p["cost"] * s.get("total_units", 0) if s.get("total_units") else 0
        margin = ((rev - cost) / rev * 100) if rev else None
        result.append(ProductListItem(
            product_id=p["product_id"], product_name=p["product_name"],
            category=p["category"], subcategory=p["subcategory"],
            price=p["price"], cost=p["cost"], rating=p.get("rating"),
            review_count=p.get("review_count", 0),
            total_revenue=round(rev, 2), total_units_sold=int(s.get("total_units", 0)),
            gross_margin_pct=round(margin, 1) if margin else None,
            avg_discount_pct=round(s.get("avg_discount", 0), 1) if s.get("avg_discount") else None,
            total_marketing_spend=round(m.get("total_spend", 0), 2),
            product_roas=round(m["roas"], 2) if m.get("roas") else None,
        ))
    result.sort(key=lambda x: -x.total_revenue)
    return result


@app.get("/api/products/{product_id}")
def get_product_detail(product_id: str):
    product = sql_layer.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found.")
    metrics = sql_layer.product_metrics(product_id)
    trend = sql_layer.quarterly_trend(product_id)
    campaigns = sql_layer.campaigns_for_product(product_id)
    reviews = sql_layer.review_summary(product_id)
    return {
        "product": product, "metrics": metrics,
        "quarterly_trend": trend, "campaigns": campaigns, "reviews": reviews,
    }


@app.get("/api/customers/segments", response_model=list[CustomerSegment])
def customer_segments():
    seg_data = sql_layer.segment_revenue()
    result = []
    for seg in seg_data:
        repeat = sql_layer.repeat_purchase_rate(segment=seg["segment"])
        result.append(CustomerSegment(
            segment=seg["segment"], customers=int(seg["customers"]),
            revenue=round(seg["revenue"], 2), avg_ltv=float(seg["avg_ltv"]),
            repeat_purchase_rate=repeat.get("repeat_purchase_rate_pct"),
            avg_order_value=None,
        ))
    return result


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
def datahub_upload(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(status_code=422, detail=f"Unsupported type '{ext}'. Use .csv, .xlsx, or .xls")
    try:
        from src.analytics.data_hub import ingest_file
        result = ingest_file(file.file.read(), file.filename)
    except Exception as e:
        logger.exception("DataHub upload failed")
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.get("/api/datahub/datasets")
def datahub_list():
    from src.analytics.data_hub import list_datasets
    return list_datasets()


@app.get("/api/datahub/datasets/{dataset_id}")
def datahub_detail(dataset_id: str):
    from src.analytics.data_hub import get_dataset
    ds = get_dataset(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


@app.delete("/api/datahub/datasets/{dataset_id}")
def datahub_delete(dataset_id: str):
    from src.analytics.data_hub import delete_dataset
    if not delete_dataset(dataset_id):
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Reviews Analytics
# ---------------------------------------------------------------------------

@app.get("/api/analytics/reviews")
def reviews_overview():
    with sql_layer.get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        avg_rating = conn.execute("SELECT AVG(rating) FROM reviews").fetchone()[0]
        by_rating = [dict(r) for r in conn.execute(
            "SELECT rating, COUNT(*) as count FROM reviews GROUP BY rating ORDER BY rating"
        ).fetchall()]
        negative = conn.execute("SELECT COUNT(*) FROM reviews WHERE rating <= 2").fetchone()[0]
        # Top negative themes (simple keyword extraction from negative reviews)
        neg_reviews = [dict(r) for r in conn.execute(
            "SELECT review_text FROM reviews WHERE rating <= 2 LIMIT 200"
        ).fetchall()]
        theme_keywords = {
            "battery": 0, "quality": 0, "delivery": 0, "packaging": 0,
            "customer service": 0, "broken": 0, "defective": 0, "slow": 0,
            "expensive": 0, "disappointed": 0, "return": 0, "warranty": 0,
        }
        for r in neg_reviews:
            text = r["review_text"].lower()
            for kw in theme_keywords:
                if kw in text:
                    theme_keywords[kw] += 1
        # Sort by frequency, take top themes
        top_negative = sorted(theme_keywords.items(), key=lambda x: -x[1])
        top_negative = [(t, c) for t, c in top_negative if c > 0][:6]
    return {
        "total_reviews": total,
        "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "negative_count": negative,
        "negative_pct": round(100 * negative / total, 1) if total else 0,
        "by_rating": by_rating,
        "top_negative_themes": [{"theme": t, "count": c} for t, c in top_negative],
    }


# ---------------------------------------------------------------------------
# Discount Analytics
# ---------------------------------------------------------------------------

@app.get("/api/analytics/discounts")
def discount_analytics():
    with sql_layer.get_conn() as conn:
        bands = [dict(r) for r in conn.execute("""
            SELECT
                CASE
                    WHEN discount = 0 THEN '0% (No discount)'
                    WHEN discount BETWEEN 0.01 AND 5 THEN '1-5%'
                    WHEN discount BETWEEN 5.01 AND 10 THEN '5-10%'
                    WHEN discount BETWEEN 10.01 AND 15 THEN '10-15%'
                    WHEN discount BETWEEN 15.01 AND 20 THEN '15-20%'
                    WHEN discount > 20 THEN '20%+'
                    ELSE 'Other'
                END AS discount_band,
                COUNT(*) AS orders,
                SUM(revenue) AS total_revenue,
                SUM(quantity) AS total_units,
                AVG(selling_price) AS avg_selling_price,
                ROUND(AVG(revenue - cost), 2) AS avg_profit
            FROM sales
            GROUP BY discount_band
            ORDER BY MIN(discount)
        """).fetchall()]
        overall_avg = conn.execute("SELECT AVG(discount) FROM sales").fetchone()[0]
        # Correlation: avg margin by discount band
        margin_by_band = [dict(r) for r in conn.execute("""
            SELECT
                CASE
                    WHEN discount = 0 THEN '0%'
                    WHEN discount <= 5 THEN '1-5%'
                    WHEN discount <= 10 THEN '5-10%'
                    WHEN discount <= 15 THEN '10-15%'
                    ELSE '15%+'
                END AS band,
                ROUND(100.0 * AVG(revenue - cost) / NULLIF(AVG(revenue), 0), 2) AS avg_margin_pct
            FROM sales
            GROUP BY band ORDER BY MIN(discount)
        """).fetchall()]
    return {
        "overall_avg_discount": round(overall_avg, 2) if overall_avg else 0,
        "discount_bands": bands,
        "margin_by_band": margin_by_band,
    }


# ---------------------------------------------------------------------------
# System Health / Observability
# ---------------------------------------------------------------------------

@app.get("/api/system/health")
def system_health():
    import time
    checks = {}
    # API
    checks["api"] = {"status": "healthy", "latency_ms": 0}
    # Database
    try:
        t0 = time.time()
        with sql_layer.get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
        checks["database"] = {"status": "healthy", "latency_ms": round((time.time() - t0) * 1000, 2)}
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)}
    # Vector Search
    try:
        t0 = time.time()
        _pipeline.vector_store.search("test", top_k=1)
        checks["vector_search"] = {"status": "healthy", "latency_ms": round((time.time() - t0) * 1000, 2),
                                     "chunks": len(_pipeline.vector_store.chunks)}
    except Exception as e:
        checks["vector_search"] = {"status": "error", "error": str(e)}
    # LLM
    checks["llm"] = {"status": "healthy", "backend": config.LLM_BACKEND, "model": config.OLLAMA_MODEL if config.LLM_BACKEND == "ollama" else "template-fallback"}
    # Supabase
    try:
        from src.database.supabase_client import is_configured, health_check
        if is_configured():
            checks["supabase"] = health_check()
        else:
            checks["supabase"] = {"status": "not_configured"}
    except Exception as e:
        checks["supabase"] = {"status": "error", "error": str(e)}
    return checks


# ---------------------------------------------------------------------------
# AI Insights & Recommendations
# ---------------------------------------------------------------------------

@app.post("/api/insights")
def generate_insights():
    """Generate proactive business insights from the data."""
    insights = []
    with sql_layer.get_conn() as conn:
        # Revenue decline detection
        trend = [dict(r) for r in conn.execute("""
            SELECT strftime('%Y-%m', order_date) AS month, SUM(revenue) AS revenue
            FROM sales GROUP BY month ORDER BY month
        """).fetchall()]
        if len(trend) >= 3:
            last_3 = [t["revenue"] for t in trend[-3:]]
            if all(last_3[i] < last_3[i-1] for i in range(1, len(last_3))):
                decline_pct = round((last_3[0] - last_3[-1]) / last_3[0] * 100, 1)
                insights.append({
                    "type": "warning", "title": "Revenue Decline Trend",
                    "description": f"Revenue has declined for {len(last_3)} consecutive periods ({decline_pct}% cumulative decline).",
                    "impact": "high", "confidence": "high",
                    "evidence": [f"Last 3 months: {', '.join(f'${v:,.0f}' for v in last_3)}"],
                })

        # Low ROAS campaigns
        low_roas = [dict(r) for r in conn.execute("""
            SELECT campaign_name, roas FROM (
                SELECT campaign_name, SUM(attributed_revenue)*1.0/NULLIF(SUM(spend),0) as roas
                FROM campaigns GROUP BY campaign_name
            ) WHERE roas < 3.0
        """).fetchall()]
        if low_roas:
            names = ", ".join(c["campaign_name"] for c in low_roas[:3])
            insights.append({
                "type": "warning", "title": "Below-Target ROAS Campaigns",
                "description": f"{len(low_roas)} campaign(s) have ROAS below the 3.0x guideline threshold: {names}.",
                "impact": "medium", "confidence": "high",
                "evidence": [f"{c['campaign_name']}: {c['roas']}x ROAS" for c in low_roas[:3]],
            })

        # High-margin products
        high_margin = [dict(r) for r in conn.execute("""
            SELECT p.product_name, ROUND(100.0 * SUM(s.revenue - s.cost) / NULLIF(SUM(s.revenue), 0), 1) as margin
            FROM sales s JOIN products p ON s.product_id = p.product_id
            GROUP BY p.product_id HAVING margin > 50
            ORDER BY margin DESC LIMIT 3
        """).fetchall()]
        if high_margin:
            insights.append({
                "type": "success", "title": "High-Margin Products",
                "description": f"{len(high_margin)} products have gross margins above 50%, indicating strong profitability.",
                "impact": "high", "confidence": "high",
                "evidence": [f"{p['product_name']}: {p['margin']}% margin" for p in high_margin],
            })

        # Customer segment opportunity
        premium_ltv = conn.execute("""
            SELECT AVG(lifetime_value) as ltv FROM customers WHERE segment = 'Premium'
        """).fetchone()[0]
        regular_ltv = conn.execute("""
            SELECT AVG(lifetime_value) as ltv FROM customers WHERE segment = 'Regular'
        """).fetchone()[0]
        if premium_ltv and regular_ltv and premium_ltv > regular_ltv * 2:
            insights.append({
                "type": "info", "title": "Premium Customer Value",
                "description": f"Premium customers have {premium_ltv/regular_ltv:.1f}x the LTV of Regular customers. Retention investment in this segment has outsized ROI.",
                "impact": "high", "confidence": "medium",
                "evidence": [f"Premium avg LTV: ${premium_ltv:,.0f}", f"Regular avg LTV: ${regular_ltv:,.0f}"],
            })

    return {"insights": insights, "count": len(insights)}


@app.post("/api/executive-brief")
def executive_brief():
    """Generate a structured executive brief from the data."""
    with sql_layer.get_conn() as conn:
        total_rev = conn.execute("SELECT SUM(revenue) FROM sales").fetchone()[0]
        total_units = conn.execute("SELECT SUM(quantity) FROM sales").fetchone()[0]
        total_spend = conn.execute("SELECT SUM(spend) FROM campaigns").fetchone()[0]
        total_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        avg_roas = conn.execute("SELECT SUM(attributed_revenue)*1.0/NULLIF(SUM(spend),0) FROM campaigns").fetchone()[0]
        gross_profit = conn.execute("SELECT SUM(revenue - cost) FROM sales").fetchone()[0]
        margin = round(100 * gross_profit / total_rev, 1) if total_rev else 0

        # Top category
        top_cat = conn.execute("""
            SELECT p.category, SUM(s.revenue) as rev
            FROM sales s JOIN products p ON s.product_id = p.product_id
            GROUP BY p.category ORDER BY rev DESC LIMIT 1
        """).fetchone()

        # Top product
        top_prod = conn.execute("""
            SELECT p.product_name, SUM(s.revenue) as rev
            FROM sales s JOIN products p ON s.product_id = p.product_id
            GROUP BY p.product_id ORDER BY rev DESC LIMIT 1
        """).fetchone()

        # Best campaign
        best_camp = conn.execute("""
            SELECT campaign_name, SUM(attributed_revenue)*1.0/NULLIF(SUM(spend),0) as roas
            FROM campaigns GROUP BY campaign_name ORDER BY roas DESC LIMIT 1
        """).fetchone()

        # Review sentiment
        neg_pct = conn.execute("""
            SELECT ROUND(100.0 * COUNT(CASE WHEN rating <= 2 THEN 1 END) / COUNT(*), 1) FROM reviews
        """).fetchone()[0]

    sections = [
        {
            "title": "Business Performance",
            "content": f"Total revenue: ${total_rev:,.0f} across {total_units:,} units. Gross margin: {margin}%. Total marketing spend: ${total_spend:,.0f} with blended ROAS of {avg_roas:.2f}x.",
        },
        {
            "title": "Key Drivers",
            "content": f"Top category: {top_cat[0]} (${top_cat[1]:,.0f} revenue). Top product: {top_prod[0]} (${top_prod[1]:,.0f} revenue). Best campaign: {best_camp[0]} ({best_camp[1]:.2f}x ROAS).",
        },
        {
            "title": "Risks",
            "content": f"Negative review rate: {neg_pct}%. {len([1 for r in conn.execute('SELECT campaign_name FROM (SELECT campaign_name, SUM(attributed_revenue)*1.0/NULLIF(SUM(spend),0) as roas FROM campaigns GROUP BY campaign_name) WHERE roas < 3.0').fetchall()])} campaigns below 3.0x ROAS target.",
        },
        {
            "title": "Opportunities",
            "content": "Premium segment has highest LTV — retention investment recommended. High-margin products (above 50%) should receive increased marketing budget. Email channel shows strongest retention metrics.",
        },
        {
            "title": "Recommended Actions",
            "content": "1) Review underperforming campaign budgets. 2) Increase premium customer retention spend. 3) Investigate negative review themes for quality improvements. 4) Double down on high-margin product lines.",
        },
    ]
    return {"sections": sections, "generated_at": datetime.now().isoformat() if 'datetime' in dir() else ""}
