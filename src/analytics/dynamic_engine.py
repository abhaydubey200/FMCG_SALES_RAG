"""
Dynamic Data Engine — the core module for self-service analytics.

Handles:
  1. File validation & upload to PostgreSQL
  2. Schema inference & profiling
  3. Semantic mapping (auto-detect column → business concept)
  4. Dynamic SQL generation from semantic mappings
  5. Asset lifecycle (create, read, update, delete, reprocess)
  6. Workspace isolation
"""
import io
import re
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src import config

logger = logging.getLogger("dynamic_data_engine")

# ═══════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_WORKSPACE = "default"

# Canonical concepts for semantic mapping
CANONICAL_MEASURES = {
    "revenue": {"aliases": ["revenue", "sales", "amount", "income", "net_sales", "sales_amount",
                             "net_revenue", "total_sales", "gross_sales", "net_amount", "total_revenue",
                             "sales_revenue", "gross_revenue", "turnover", "total_amount"],
                "agg": "SUM", "type": "measure"},
    "quantity": {"aliases": ["quantity", "qty", "units", "units_sold", "volume", "count",
                              "num_units", "number_of_units", "items_sold", "quantity_sold"],
                 "agg": "SUM", "type": "measure"},
    "cost": {"aliases": ["cost", "total_cost", "cogs", "cost_of_goods", "unit_cost",
                          "purchase_cost", "production_cost"],
             "agg": "SUM", "type": "measure"},
    "profit": {"aliases": ["profit", "gross_profit", "net_profit", "margin", "earnings",
                            "operating_profit", "net_income"],
               "agg": "SUM", "type": "measure"},
    "spend": {"aliases": ["spend", "ad_spend", "advertising_spend", "marketing_spend",
                           "total_spend", "budget", "cost_per", "advertising_cost"],
              "agg": "SUM", "type": "measure"},
    "price": {"aliases": ["price", "unit_price", "selling_price", "avg_price", "mean_price",
                           "average_price", "retail_price", "list_price"],
              "agg": "AVG", "type": "measure"},
    "discount": {"aliases": ["discount", "discount_pct", "discount_percent", "discount_rate",
                              "reduction", "markdown", "promo_pct", "promo_percent",
                              "promotion_pct", "promotion_percent", "promo_discount",
                              "promotional_discount", "promo_rate"],
                 "agg": "AVG", "type": "measure"},
    "impressions": {"aliases": ["impressions", "views", "reach", "ad_views", "impressions_count"],
                    "agg": "SUM", "type": "measure"},
    "clicks": {"aliases": ["clicks", "click_count", "ad_clicks", "click_through"],
               "agg": "SUM", "type": "measure"},
    "conversions": {"aliases": ["conversions", "conversion_count", "purchases", "orders",
                                 "transactions", "total_orders", "num_orders"],
                    "agg": "SUM", "type": "measure"},
    "rating": {"aliases": ["rating", "score", "stars", "review_rating", "avg_rating"],
               "agg": "AVG", "type": "measure"},
    "ltv": {"aliases": ["ltv", "lifetime_value", "customer_lifetime_value", "clv",
                         "lifetime_revenue"],
            "agg": "AVG", "type": "measure"},
    "attribution_revenue": {"aliases": ["attributed_revenue", "conversion_revenue",
                                         "revenue_attributed"],
                            "agg": "SUM", "type": "measure"},
}

CANONICAL_DIMENSIONS = {
    "date": {"aliases": ["date", "order_date", "transaction_date", "sale_date", "purchase_date",
                          "start_date", "end_date", "campaign_date", "order_day", "sale_day",
                          "transaction_day", "report_date", "period_date", "ship_date",
                          "created_date", "invoice_date"],
             "type": "date"},
    "product": {"aliases": ["product", "product_name", "product_id", "item", "item_name",
                             "sku", "sku_name", "product_description", "item_description",
                             "product_label", "item_label", "product_title"],
                "type": "dimension"},
    "category": {"aliases": ["category", "product_category", "cat", "product_cat",
                              "department", "product_group", "product_type"],
                 "type": "dimension"},
    "subcategory": {"aliases": ["subcategory", "sub_category", "sub_category_name",
                                 "product_subcategory"],
                    "type": "dimension"},
    "region": {"aliases": ["region", "territory", "sales_region", "territory_name",
                            "geography", "market", "area", "district", "country",
                            "state", "province", "city", "location"],
               "type": "dimension"},
    "customer": {"aliases": ["customer", "customer_id", "cust_id", "client_id",
                              "buyer_id", "account_id"],
                 "type": "dimension"},
    "customer_name": {"aliases": ["customer_name", "cust_name", "client_name",
                                   "buyer_name", "account_name"],
                      "type": "dimension"},
    "segment": {"aliases": ["segment", "customer_segment", "market_segment",
                             "customer_type", "client_type", "tier"],
                "type": "dimension"},
    "channel": {"aliases": ["channel", "sales_channel", "marketing_channel",
                             "distribution_channel", "medium", "source_channel"],
                "type": "dimension"},
    "campaign": {"aliases": ["campaign", "campaign_name", "campaign_id", "promo",
                              "promotion", "promotion_name", "ad_campaign"],
                 "type": "dimension"},
    "order_id": {"aliases": ["order_id", "transaction_id", "sale_id", "invoice_id",
                               "order_number", "transaction_number"],
                 "type": "identifier"},
    "rep": {"aliases": ["rep", "sales_rep", "representative", "salesperson", "agent"],
            "type": "dimension"},
}

# Domain detection keywords
DOMAIN_KEYWORDS = {
    "sales": ["revenue", "sales", "order", "quantity", "price", "cost", "profit",
              "discount", "product", "customer", "transaction"],
    "marketing": ["campaign", "spend", "impressions", "clicks", "conversions",
                  "ctr", "roas", "channel", "ad", "marketing", "lead"],
    "customer": ["customer", "segment", "ltv", "lifetime", "acquisition",
                 "churn", "retention", "repeat"],
    "product": ["product", "sku", "category", "inventory", "stock"],
}


# ═══════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ColumnProfile:
    name: str
    dtype: str
    null_count: int
    null_pct: float
    unique_count: int
    sample_values: list
    min_val: Any = None
    max_val: Any = None
    mean_val: Any = None
    median_val: Any = None
    semantic_type: str = "unknown"


@dataclass
class DatasetProfile:
    dataset_id: str
    filename: str
    file_type: str
    file_size_bytes: int
    row_count: int
    col_count: int
    columns: List[ColumnProfile]
    duplicate_rows: int
    quality_score: float
    uploaded_at: str
    sheet_name: Optional[str] = None
    issues: List[dict] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# DATABASE HELPERS
# ═══════════════════════════════════════════════════════════════════════

def _get_pg_connection(retries: int = 2, delay: float = 0.25):
    """Get a fresh PostgreSQL connection with bounded retry.

    A single connect() can transiently fail right after container recreate
    (pool/DNS/accept warm-up). Retrying a couple of times with a short delay
    rides out the blip instead of misreporting an empty workspace. This is a
    connection-level retry only — never a query retry.
    """
    import time as _time
    import psycopg2
    if not config.USE_POSTGRESQL or not config.DATABASE_URL:
        raise RuntimeError("PostgreSQL required for dynamic data engine")
    last_exc = None
    for attempt in range(max(1, retries + 1)):
        try:
            return psycopg2.connect(config.DATABASE_URL, connect_timeout=10)
        except Exception as e:  # psycopg2.OperationalError et al.
            last_exc = e
            if attempt < retries:
                _time.sleep(delay * (attempt + 1))
    raise RuntimeError(f"Database unavailable: {last_exc}") from last_exc


def _safe_table_name(name: str) -> str:
    """Convert a name to a safe PostgreSQL table name."""
    # Only allow alphanumeric and underscores
    safe = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower().strip())
    # Must start with a letter or underscore
    if safe and safe[0].isdigit():
        safe = 't_' + safe
    # Truncate to 63 chars (PostgreSQL limit)
    safe = safe[:63]
    # Remove trailing underscores
    safe = safe.rstrip('_')
    return safe or 'unnamed_table'


def _safe_column_name(name: str) -> str:
    """Convert a name to a safe PostgreSQL column name."""
    safe = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower().strip())
    if safe and safe[0].isdigit():
        safe = 'c_' + safe
    safe = safe[:63].rstrip('_')
    return safe or 'unnamed_col'


def _sanitize_sql_identifier(identifier: str) -> str:
    """Validate that a string is a safe SQL identifier (no injection possible)."""
    if not identifier:
        raise ValueError("Empty identifier")
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
        raise ValueError(f"Unsafe identifier: {identifier}")
    if len(identifier) > 63:
        raise ValueError(f"Identifier too long: {identifier}")
    return identifier


# ═══════════════════════════════════════════════════════════════════════
# FILE VALIDATION
# ═══════════════════════════════════════════════════════════════════════

def validate_file(file_bytes: bytes, filename: str) -> Tuple[bool, str]:
    """Validate uploaded file. Returns (is_valid, error_message)."""
    ext = Path(filename).suffix.lower()
    if ext not in {".csv", ".xlsx", ".xls"}:
        return False, f"Unsupported file type '{ext}'. Accepted: .csv, .xlsx, .xls"

    max_size = config.MAX_UPLOAD_SIZE_BYTES
    if len(file_bytes) > max_size:
        return False, f"File too large ({len(file_bytes):,} bytes). Maximum: {max_size:,} bytes"

    if len(file_bytes) == 0:
        return False, "File is empty"

    # Try to parse to catch malformed files early
    try:
        if ext == ".csv":
            pd.read_csv(io.BytesIO(file_bytes), nrows=5)
        elif ext in (".xlsx", ".xls"):
            pd.read_excel(io.BytesIO(file_bytes), nrows=5)
    except Exception as e:
        return False, f"Cannot parse file: {str(e)[:200]}"

    return True, ""


# ═══════════════════════════════════════════════════════════════════════
# SCHEMA INFERENCE & PROFILING
# ═══════════════════════════════════════════════════════════════════════

SEMANTIC_PATTERNS = {
    # Date must be checked FIRST — "sales_date" contains "sales" but is a date
    "date": ["date", "time", "created", "updated", "period", "month", "quarter", "year"],
    "id": ["id", "key", "code"],
    "category": ["category", "segment", "channel", "region", "type", "status", "class"],
    "text": ["name", "description", "title", "text", "review", "comment", "note"],
    "rating": ["rating", "score", "stars"],
    "percentage": ["rate", "ratio", "percent", "pct", "margin", "discount", "ctr", "roas", "growth"],
    "count": ["count", "units", "quantity", "orders", "customers", "impressions", "clicks", "conversions", "reviews"],
    # Revenue patterns come LAST — avoid matching "sales_date" as revenue
    "revenue": ["revenue", "amount", "income", "profit", "spend", "cost", "price", "ltv", "cac", "aov"],
}


def detect_semantic_type(col_name: str, dtype: str, sample_values: list) -> str:
    """Detect the semantic type of a column based on name patterns and data."""
    name_lower = col_name.lower().replace(" ", "_").replace("-", "_")

    for stype, patterns in SEMANTIC_PATTERNS.items():
        for pattern in patterns:
            if pattern in name_lower:
                return stype

    if dtype == "object" and sample_values:
        try:
            pd.to_datetime(sample_values[:5], format="mixed")
            return "date"
        except (ValueError, TypeError):
            pass

    if dtype in ("int64", "float64") and sample_values:
        try:
            vals = [float(v) for v in sample_values if v is not None]
            if vals and 0 < max(vals) <= 5 and len(set(vals)) <= 10:
                return "rating"
        except (ValueError, TypeError):
            pass

    return "unknown"


def auto_map_columns(columns: List[ColumnProfile]) -> List[dict]:
    """Auto-detect semantic mappings for columns.
    
    Priority order:
    1. Exact matches (highest confidence)
    2. Dimensions before measures (dimensions are more specific)
    3. Avoid mapping date-containing columns to revenue
    """
    mappings = []
    used_concepts = set()

    for col in columns:
        name_lower = col.name.lower().replace(" ", "_").replace("-", "_")
        best_concept = None
        best_confidence = 0.0
        best_type = "unknown"

        # Check against canonical dimensions FIRST (more specific)
        for concept, info in CANONICAL_DIMENSIONS.items():
            for alias in info["aliases"]:
                if alias == name_lower:
                    conf = 0.95  # Exact match — highest priority
                    if conf > best_confidence and concept not in used_concepts:
                        best_concept = concept
                        best_confidence = conf
                        best_type = info["type"]
                        break
                elif alias in name_lower:
                    conf = 0.7
                    if conf > best_confidence and concept not in used_concepts:
                        best_concept = concept
                        best_confidence = conf
                        best_type = info["type"]

        # Then check against canonical measures
        for concept, info in CANONICAL_MEASURES.items():
            if concept in used_concepts:
                continue
            for alias in info["aliases"]:
                if alias == name_lower:
                    conf = 0.95  # Exact match
                    if conf > best_confidence:
                        best_concept = concept
                        best_confidence = conf
                        best_type = "measure"
                        break
                elif alias in name_lower:
                    conf = 0.7
                    # Penalize if column name contains a dimension-like suffix
                    if any(suffix in name_lower for suffix in ["_date", "_time", "_day", "_id"]):
                        conf = 0.4  # Lower confidence for compound names
                    if conf > best_confidence:
                        best_concept = concept
                        best_confidence = conf
                        best_type = "measure"

        if best_concept:
            used_concepts.add(best_concept)
            mappings.append({
                "source_column": col.name,
                "canonical_concept": best_concept,
                "concept_type": best_type,
                "confidence": best_confidence,
                "mapping_method": "auto",
                "approved": best_confidence >= 0.7,
            })

    return mappings


def profile_dataset(df: pd.DataFrame, filename: str, ext: str,
                    file_size: int, dataset_id: str,
                    sheet_name: str = None) -> DatasetProfile:
    """Profile a single DataFrame."""
    columns = []
    for col in df.columns:
        series = df[col]
        sample = series.dropna().head(5).tolist()
        cp = ColumnProfile(
            name=str(col),
            dtype=str(series.dtype),
            null_count=int(series.isna().sum()),
            null_pct=round(100 * series.isna().sum() / len(series), 2) if len(series) > 0 else 0,
            unique_count=int(series.nunique()),
            sample_values=[str(v) for v in sample[:5]],
        )
        if series.dtype in ("int64", "float64"):
            cp.min_val = float(series.min()) if not series.isna().all() else None
            cp.max_val = float(series.max()) if not series.isna().all() else None
            cp.mean_val = round(float(series.mean()), 4) if not series.isna().all() else None
            cp.median_val = float(series.median()) if not series.isna().all() else None
        cp.semantic_type = detect_semantic_type(str(col), str(series.dtype), sample)
        columns.append(cp)

    dup_rows = int(df.duplicated().sum())
    issues = _validate_data(df, filename)

    profile = DatasetProfile(
        dataset_id=dataset_id,
        filename=filename,
        file_type=ext.lstrip("."),
        file_size_bytes=file_size,
        row_count=len(df),
        col_count=len(df.columns),
        columns=columns,
        duplicate_rows=dup_rows,
        quality_score=0,
        uploaded_at=datetime.now().isoformat(),
        sheet_name=sheet_name,
        issues=issues,
    )
    profile.quality_score = _calculate_quality_score(profile)
    return profile


def _validate_data(df: pd.DataFrame, filename: str) -> List[dict]:
    """Detect data quality issues."""
    issues = []
    for col in df.columns:
        null_count = int(df[col].isna().sum())
        if null_count > 0:
            issues.append({
                "type": "missing_values",
                "severity": "warning" if null_count / len(df) < 0.1 else "error",
                "column": col,
                "count": null_count,
                "message": f"{null_count} missing values in column '{col}' ({null_count/len(df)*100:.1f}%)",
            })

    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        issues.append({
            "type": "duplicate_rows",
            "severity": "warning",
            "count": dup_count,
            "message": f"{dup_count} duplicate rows detected",
        })
    return issues


def _calculate_quality_score(profile: DatasetProfile) -> float:
    """Calculate a data quality score (0-100)."""
    score = 100.0
    total_cells = profile.row_count * profile.col_count
    if total_cells > 0:
        total_nulls = sum(c.null_count for c in profile.columns)
        score -= (total_nulls / total_cells) * 40
    if profile.row_count > 0:
        score -= (profile.duplicate_rows / profile.row_count) * 20
    low_unique_cols = sum(1 for c in profile.columns if c.unique_count <= 1 and profile.row_count > 1)
    if profile.col_count > 0:
        score -= (low_unique_cols / profile.col_count) * 10
    unknown_cols = sum(1 for c in profile.columns if c.semantic_type == "unknown")
    if profile.col_count > 0:
        score -= (unknown_cols / profile.col_count) * 10
    return max(0, min(100, round(score, 1)))


def detect_domain(columns: List[ColumnProfile]) -> str:
    """Detect whether a dataset is sales, marketing, customer, product, or mixed."""
    scores = {domain: 0 for domain in DOMAIN_KEYWORDS}
    for col in columns:
        name_lower = col.name.lower()
        for domain, keywords in DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw in name_lower:
                    scores[domain] += 1

    max_score = max(scores.values()) if scores else 0
    if max_score == 0:
        return "unknown"

    top_domains = [d for d, s in scores.items() if s == max_score]
    if len(top_domains) > 1:
        return "mixed"
    return top_domains[0]


# ═══════════════════════════════════════════════════════════════════════
# CORE: UPLOAD & PERSIST TO POSTGRESQL
# ═══════════════════════════════════════════════════════════════════════

def ingest_file(file_bytes: bytes, filename: str,
                workspace_id: str = DEFAULT_WORKSPACE) -> dict:
    """
    Full ingestion pipeline: Validate → Parse → Profile → Map → Store in PostgreSQL.
    Returns the full profile, dataset_id, and asset_id.
    """
    # Validate
    is_valid, error_msg = validate_file(file_bytes, filename)
    if not is_valid:
        raise ValueError(error_msg)

    ext = Path(filename).suffix.lower()
    file_hash = hashlib.md5(file_bytes).hexdigest()[:12]
    # Workspace-namespaced id: two workspaces may upload the SAME bytes/filename
    # without colliding on dataset_id (which is also the physical table name).
    ws_tag = _safe_table_name(workspace_id)
    dataset_id = f"{ws_tag}__{Path(filename).stem}_{file_hash}"

    conn = _get_pg_connection()
    try:
        conn.autocommit = False
        cur = conn.cursor()

        # Ensure workspace exists
        cur.execute(
            "INSERT INTO workspaces (workspace_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (workspace_id, f"Workspace {workspace_id}")
        )

        all_profiles = []

        if ext == ".csv":
            df = pd.read_csv(io.BytesIO(file_bytes))
            asset_id, profile = _ingest_dataframe(
                conn, cur, df, filename, ext, len(file_bytes), dataset_id,
                workspace_id, sheet_name=None
            )
            all_profiles.append(profile)

        elif ext in (".xlsx", ".xls"):
            xls = pd.ExcelFile(io.BytesIO(file_bytes))
            for sheet_name in xls.sheet_names:
                try:
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    if df.empty:
                        continue
                    sheet_id = f"{dataset_id}__{_safe_table_name(sheet_name)}"
                    asset_id, profile = _ingest_dataframe(
                        conn, cur, df, filename, ext, len(file_bytes),
                        sheet_id, workspace_id, sheet_name=sheet_name
                    )
                    all_profiles.append(profile)
                except Exception as e:
                    logger.warning(f"Failed to process sheet '{sheet_name}': {e}")

        conn.commit()

        return {
            "dataset_ids": [p.dataset_id for p in all_profiles],
            "asset_ids": [p.dataset_id for p in all_profiles],  # asset_id == dataset_id
            "profiles": [_profile_to_dict(p) for p in all_profiles],
            "total_rows": sum(p.row_count for p in all_profiles),
            "total_columns": sum(p.col_count for p in all_profiles),
        }

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ingest_dataframe(conn, cur, df: pd.DataFrame, filename: str, ext: str,
                       file_size: int, dataset_id: str, workspace_id: str,
                       sheet_name: str = None) -> Tuple[str, DatasetProfile]:
    """Ingest a single DataFrame into PostgreSQL."""
    # Profile the data
    profile = profile_dataset(df, filename, ext, file_size, dataset_id, sheet_name)

    # Create asset record
    asset_id = dataset_id
    table_name = _safe_table_name(dataset_id)
    domain = detect_domain(profile.columns)
    display_name = Path(filename).stem.replace("_", " ").title()
    if sheet_name:
        display_name += f" — {sheet_name}"

    cur.execute("""
        INSERT INTO assets (asset_id, workspace_id, name, type, source_type, status,
                           domain, row_count, column_count, size_bytes, table_name,
                           schema, semantic_status, processing_status)
        VALUES (%s, %s, %s, 'structured', %s, 'ready', %s, %s, %s, %s, %s, %s, 'pending', 'ready')
        ON CONFLICT (asset_id) DO UPDATE SET
            name = EXCLUDED.name, status = 'ready', row_count = EXCLUDED.row_count,
            column_count = EXCLUDED.column_count, domain = EXCLUDED.domain,
            updated_at = NOW()
    """, (asset_id, workspace_id, display_name, ext.lstrip("."), domain,
          profile.row_count, profile.col_count, file_size, table_name,
          _col_schema_json(profile.columns)))

    # Create dataset record
    cur.execute("""
        INSERT INTO datasets (dataset_id, asset_id, workspace_id, filename, file_type,
                             file_size_bytes, row_count, col_count, quality_score)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (dataset_id) DO UPDATE SET
            row_count = EXCLUDED.row_count,
            col_count = EXCLUDED.col_count,
            quality_score = EXCLUDED.quality_score,
            uploaded_at = NOW()
    """, (dataset_id, asset_id, workspace_id, filename, ext.lstrip("."),
          file_size, profile.row_count, profile.col_count, profile.quality_score))

    # Idempotent re-ingest: same file (same dataset_id) uploaded again must
    # not duplicate column/quality metadata rows. Clear prior children first;
    # assets/datasets rows are upserted below.
    cur.execute("DELETE FROM dataset_columns WHERE dataset_id = %s", (dataset_id,))
    cur.execute("DELETE FROM data_quality_results WHERE dataset_id = %s", (dataset_id,))

    # Store column metadata
    for cp in profile.columns:
        cur.execute("""
            INSERT INTO dataset_columns (dataset_id, column_name, dtype, null_count,
                                        null_pct, unique_count, semantic_type,
                                        sample_values, min_val, max_val, mean_val)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
        """, (dataset_id, cp.name, cp.dtype, cp.null_count, cp.null_pct,
              cp.unique_count, cp.semantic_type, __import__('json').dumps(cp.sample_values[:5]),
              cp.min_val, cp.max_val, cp.mean_val))

    # Store quality issues
    for issue in profile.issues:
        cur.execute("""
            INSERT INTO data_quality_results (dataset_id, issue_type, severity, column_name,
                                             count, message)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (dataset_id, issue["type"], issue["severity"],
              issue.get("column"), issue["count"], issue["message"]))

    # Create physical PostgreSQL table
    _create_physical_table(cur, df, table_name)

    # Insert data
    _insert_data(cur, df, table_name)

    # Auto-generate semantic mappings
    mappings = auto_map_columns(profile.columns)
    for m in mappings:
        cur.execute("""
            INSERT INTO semantic_mappings (workspace_id, asset_id, table_name, source_column,
                                          canonical_concept, concept_type, confidence,
                                          mapping_method, approved)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (asset_id, source_column) DO UPDATE SET
                canonical_concept = EXCLUDED.canonical_concept,
                concept_type = EXCLUDED.concept_type,
                confidence = EXCLUDED.confidence,
                updated_at = NOW()
        """, (workspace_id, asset_id, table_name, m["source_column"],
              m["canonical_concept"], m["concept_type"], m["confidence"],
              m["mapping_method"], m["approved"]))

    # Update asset semantic status
    has_approved = any(m["approved"] for m in mappings)
    cur.execute("""
        UPDATE assets SET semantic_status = %s WHERE asset_id = %s
    """, ("mapped" if has_approved else "pending", asset_id))

    return asset_id, profile


def _col_schema_json(columns: List[ColumnProfile]) -> str:
    """Generate JSON schema for columns."""
    import json
    return json.dumps([{
        "name": c.name, "dtype": c.dtype, "semantic_type": c.semantic_type,
        "null_pct": c.null_pct, "unique_count": c.unique_count,
    } for c in columns])


def _create_physical_table(cur, df: pd.DataFrame, table_name: str):
    """Create a PostgreSQL table from a DataFrame."""
    _sanitize_sql_identifier(table_name)

    # Map pandas dtypes to PostgreSQL types
    type_map = {
        "int64": "BIGINT",
        "int32": "INTEGER",
        "float64": "DOUBLE PRECISION",
        "float32": "REAL",
        "object": "TEXT",
        "bool": "BOOLEAN",
        "datetime64[ns]": "TIMESTAMP",
    }

    col_defs = []
    for col in df.columns:
        safe_col = _safe_column_name(col)
        pg_type = type_map.get(str(df[col].dtype), "TEXT")
        col_defs.append(f'"{safe_col}" {pg_type}')

    create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(col_defs)})'
    cur.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    cur.execute(create_sql)


def _insert_data(cur, df: pd.DataFrame, table_name: str):
    """Bulk insert DataFrame data into PostgreSQL."""
    safe_cols = [_safe_column_name(c) for c in df.columns]
    placeholders = ", ".join(["%s"] * len(safe_cols))
    cols_str = ", ".join(f'"{c}"' for c in safe_cols)

    insert_sql = f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({placeholders})'

    # Convert DataFrame to list of tuples, handling NaN
    data = []
    for _, row in df.iterrows():
        values = []
        for val in row:
            if pd.isna(val):
                values.append(None)
            elif isinstance(val, (np.integer,)):
                values.append(int(val))
            elif isinstance(val, (np.floating,)):
                values.append(float(val))
            else:
                values.append(str(val) if val is not None else None)
        data.append(tuple(values))

    # Batch insert
    batch_size = 1000
    for i in range(0, len(data), batch_size):
        batch = data[i:i + batch_size]
        cur.executemany(insert_sql, batch)


def _profile_to_dict(p: DatasetProfile) -> dict:
    return {
        "dataset_id": p.dataset_id,
        "filename": p.filename,
        "file_type": p.file_type,
        "file_size_bytes": p.file_size_bytes,
        "row_count": p.row_count,
        "col_count": p.col_count,
        "duplicate_rows": p.duplicate_rows,
        "quality_score": p.quality_score,
        "uploaded_at": p.uploaded_at,
        "sheet_name": p.sheet_name,
        "columns": [
            {
                "name": c.name, "dtype": c.dtype, "null_count": c.null_count,
                "null_pct": c.null_pct, "unique_count": c.unique_count,
                "sample_values": c.sample_values, "min_val": c.min_val,
                "max_val": c.max_val, "mean_val": c.mean_val,
                "semantic_type": c.semantic_type,
            }
            for c in p.columns
        ],
        "issues": p.issues,
    }


# ═══════════════════════════════════════════════════════════════════════
# ASSET REGISTRY CRUD
# ═══════════════════════════════════════════════════════════════════════

def list_datasets(workspace_id: str = DEFAULT_WORKSPACE) -> List[dict]:
    """List all uploaded datasets with summary info."""
    conn = _get_pg_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT a.asset_id, a.name, a.type, a.source_type, a.status, a.domain,
                   a.row_count, a.column_count, a.size_bytes, a.table_name,
                   a.created_at, a.updated_at, a.semantic_status,
                   d.dataset_id, d.filename, d.file_type, d.file_size_bytes,
                   d.quality_score, d.version
            FROM assets a
            LEFT JOIN datasets d ON d.asset_id = a.asset_id AND d.is_current = TRUE
            WHERE a.workspace_id = %s AND a.status != 'deleted' AND a.source_type != 'seed' AND a.type = 'structured'
            ORDER BY a.created_at DESC
        """, (workspace_id,))
        cols = [desc[0] for desc in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

        # Group by filename to combine sheets
        by_filename = {}
        for r in rows:
            fn = r.get("filename") or r.get("name", "unknown")
            if fn not in by_filename:
                by_filename[fn] = {
                    "dataset_id": r["asset_id"],
                    "filename": fn,
                    "file_type": r.get("file_type") or r.get("source_type", ""),
                    "file_size_bytes": r.get("file_size_bytes") or r.get("size_bytes", 0),
                    "total_rows": r.get("row_count", 0),
                    "total_columns": r.get("column_count", 0),
                    "quality_score": r.get("quality_score"),
                    "uploaded_at": r.get("created_at", ""),
                    "domain": r.get("domain", "unknown"),
                    "status": r.get("status", "ready"),
                    "semantic_status": r.get("semantic_status", "pending"),
                    "sheet_count": 0,
                    "sheets": [],
                }
            by_filename[fn]["sheet_count"] += 1
            if r.get("sheet_name"):
                by_filename[fn]["sheets"].append(r["sheet_name"])
            # Sum rows for multi-sheet files
            by_filename[fn]["total_rows"] = max(by_filename[fn]["total_rows"], r.get("row_count", 0))

        return list(by_filename.values())
    finally:
        conn.close()


def get_dataset(dataset_id: str, workspace_id: str = DEFAULT_WORKSPACE) -> Optional[dict]:
    """Get full dataset info including profile and preview.

    Workspace-scoped: a dataset is only visible within its owning workspace.
    """
    conn = _get_pg_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT a.*, d.filename, d.file_type, d.file_size_bytes, d.quality_score, d.version
            FROM assets a
            LEFT JOIN datasets d ON d.asset_id = a.asset_id AND d.is_current = TRUE
            WHERE a.asset_id = %s AND a.workspace_id = %s
        """, (dataset_id, workspace_id))
        cols = [desc[0] for desc in cur.description]
        row = cur.fetchone()
        if not row:
            return None
        asset = dict(zip(cols, row))

        # Get columns
        cur.execute("""
            SELECT column_name, dtype, null_count, null_pct, unique_count,
                   semantic_type, sample_values, min_val, max_val, mean_val
            FROM dataset_columns WHERE dataset_id = %s
        """, (dataset_id,))
        col_cols = [desc[0] for desc in cur.description]
        columns = [dict(zip(col_cols, r)) for r in cur.fetchall()]

        # Get semantic mappings
        cur.execute("""
            SELECT source_column, canonical_concept, concept_type, confidence, mapping_method, approved
            FROM semantic_mappings WHERE asset_id = %s
        """, (dataset_id,))
        map_cols = [desc[0] for desc in cur.description]
        mappings = [dict(zip(map_cols, r)) for r in cur.fetchall()]

        # Get quality issues
        cur.execute("""
            SELECT issue_type, severity, column_name, count, message
            FROM data_quality_results WHERE dataset_id = %s
        """, (dataset_id,))
        q_cols = [desc[0] for desc in cur.description]
        issues = [dict(zip(q_cols, r)) for r in cur.fetchall()]

        # Preview data
        table_name = asset.get("table_name")
        preview = []
        if table_name:
            try:
                _sanitize_sql_identifier(table_name)
                cur.execute(f'SELECT * FROM "{table_name}" LIMIT 20')
                p_cols = [desc[0] for desc in cur.description]
                preview = [dict(zip(p_cols, r)) for r in cur.fetchall()]
            except Exception:
                pass

        return {
            "asset_id": asset.get("asset_id"),
            "name": asset.get("name"),
            "type": asset.get("type"),
            "source_type": asset.get("source_type"),
            "status": asset.get("status"),
            "domain": asset.get("domain"),
            "table_name": table_name,
            "row_count": asset.get("row_count"),
            "column_count": asset.get("column_count"),
            "size_bytes": asset.get("size_bytes"),
            "semantic_status": asset.get("semantic_status"),
            "created_at": str(asset.get("created_at", "")),
            "columns": columns,
            "mappings": mappings,
            "issues": issues,
            "preview": preview,
            "quality_score": asset.get("quality_score"),
        }
    finally:
        conn.close()


def delete_dataset(dataset_id: str, workspace_id: str = DEFAULT_WORKSPACE) -> bool:
    """Delete a dataset, its physical table, and all metadata.

    Workspace-scoped: an asset owned by another workspace cannot be deleted
    from here (returns False → caller reports 404).
    """
    conn = _get_pg_connection()
    try:
        conn.autocommit = False
        cur = conn.cursor()

        # Get table name — must be owned by the requesting workspace
        cur.execute("SELECT table_name FROM assets WHERE asset_id = %s AND workspace_id = %s",
                    (dataset_id, workspace_id))
        row = cur.fetchone()
        if not row:
            return False

        table_name = row[0]

        # Drop physical table
        if table_name:
            try:
                _sanitize_sql_identifier(table_name)
                cur.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            except Exception as e:
                logger.warning(f"Failed to drop table: {e}")

        # Delete related records
        cur.execute("DELETE FROM dataset_columns WHERE dataset_id = %s", (dataset_id,))
        cur.execute("DELETE FROM data_quality_results WHERE dataset_id = %s", (dataset_id,))
        cur.execute("DELETE FROM semantic_mappings WHERE asset_id = %s", (dataset_id,))
        cur.execute("DELETE FROM datasets WHERE dataset_id = %s", (dataset_id,))

        # Hard-delete the asset record
        cur.execute("DELETE FROM assets WHERE asset_id = %s", (dataset_id,))

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# DYNAMIC ANALYTICS ENGINE
# ═══════════════════════════════════════════════════════════════════════

def reconcile_alias_mappings(workspace_id: str = DEFAULT_WORKSPACE) -> int:
    """Idempotently backfill semantic mappings for physical columns that match a
    canonical measure/dimension alias but were ingested under an older alias list
    (e.g. promo_pct → discount). Never downgrades an existing approved mapping.

    Returns the number of mapping rows added/upgraded.
    """
    added = 0
    try:
        conn = _get_pg_connection()
    except Exception:
        return 0
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT a.asset_id, a.table_name FROM assets a
            WHERE a.workspace_id = %s AND a.status = 'ready' AND a.table_name IS NOT NULL
        """, (workspace_id,))
        assets = cur.fetchall()
        for asset_id, table_name in assets:
            try:
                _sanitize_sql_identifier(table_name)
                cur.execute(f'SELECT column_name FROM information_schema.columns WHERE table_name = %s', (table_name,))
            except Exception:
                continue
            for (col,) in cur.fetchall():
                name_lower = str(col).lower().replace(" ", "_").replace("-", "_")
                best_concept, best_type, best_conf = None, None, 0.0
                for concept, info in CANONICAL_DIMENSIONS.items():
                    for alias in info["aliases"]:
                        if alias == name_lower:
                            if 0.95 > best_conf:
                                best_concept, best_type, best_conf = concept, info["type"], 0.95
                            break
                        if alias in name_lower and 0.7 > best_conf:
                            best_concept, best_type, best_conf = concept, info["type"], 0.7
                for concept, info in CANONICAL_MEASURES.items():
                    for alias in info["aliases"]:
                        conf = 0.95 if alias == name_lower else (0.7 if alias in name_lower else 0.0)
                        if conf and any(s in name_lower for s in ("_date", "_time", "_day", "_id")):
                            conf = min(conf, 0.4)
                        if conf > best_conf:
                            best_concept, best_type, best_conf = concept, info["type"], conf
                if not best_concept or best_conf < 0.7:
                    continue
                cur.execute(
                    "SELECT canonical_concept, concept_type, confidence FROM semantic_mappings "
                    "WHERE asset_id = %s AND source_column = %s", (asset_id, col))
                existing = cur.fetchone()
                if existing and existing[2] is not None and existing[2] >= best_conf:
                    continue
                if existing:
                    cur.execute("""
                        UPDATE semantic_mappings SET canonical_concept = %s, concept_type = %s,
                               confidence = %s, approved = TRUE, updated_at = NOW()
                        WHERE asset_id = %s AND source_column = %s
                    """, (best_concept, best_type, best_conf, asset_id, col))
                else:
                    cur.execute("""
                        INSERT INTO semantic_mappings (workspace_id, asset_id, table_name, source_column,
                                                      canonical_concept, concept_type, confidence,
                                                      mapping_method, approved)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'reconcile', TRUE)
                    """, (workspace_id, asset_id, table_name, col, best_concept, best_type, best_conf))
                added += 1
        conn.commit()
        return added
    except Exception:
        conn.rollback()
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def discover_available_data(workspace_id: str = DEFAULT_WORKSPACE) -> dict:
    """Discover all available tables, columns, and semantic mappings for a workspace.
    
    Raises RuntimeError on database failure — never silently returns empty data.
    An empty result means the workspace has no assets, not that the DB is down.
    """
    try:
        conn = _get_pg_connection()
    except Exception as e:
        raise RuntimeError(f"Database unavailable — cannot discover data: {e}")
    try:
        cur = conn.cursor()

        # Get all active assets with their tables
        cur.execute("""
            SELECT a.asset_id, a.name, a.table_name, a.domain, a.row_count, a.type
            FROM assets a
            WHERE a.workspace_id = %s AND a.status = 'ready' AND a.table_name IS NOT NULL
        """, (workspace_id,))
        cols = [desc[0] for desc in cur.description]
        assets = [dict(zip(cols, r)) for r in cur.fetchall()]

        # No legacy table scanning — workspace data only

        # Get all semantic mappings
        cur.execute("""
            SELECT table_name, source_column, canonical_concept, concept_type, confidence
            FROM semantic_mappings
            WHERE workspace_id = %s AND confidence >= 0.5
        """, (workspace_id,))
        map_cols = [desc[0] for desc in cur.description]
        mappings = [dict(zip(map_cols, r)) for r in cur.fetchall()]

        # Build concept → table/column lookup
        measures = {}
        dimensions = {}
        for m in mappings:
            key = m["canonical_concept"]
            entry = {"table": m["table_name"], "column": m["source_column"],
                     "confidence": m["confidence"]}
            if m["concept_type"] == "measure":
                measures.setdefault(key, []).append(entry)
            else:
                dimensions.setdefault(key, []).append(entry)

        return {
            "assets": assets,
            "legacy_tables": [],
            "mappings": mappings,
            "available_measures": measures,
            "available_dimensions": dimensions,
        }
    finally:
        conn.close()


def get_available_kpis(workspace_id: str = DEFAULT_WORKSPACE) -> List[dict]:
    """Dynamically determine what KPIs are available based on uploaded data."""
    data = discover_available_data(workspace_id)
    measures = data["available_measures"]
    dimensions = data["available_dimensions"]

    kpis = []

    # Revenue-related KPI
    if "revenue" in measures:
        entries = measures["revenue"]
        tbl = entries[0]["table"]
        col = entries[0]["column"]
        _sanitize_sql_identifier(tbl)
        _sanitize_sql_identifier(col)
        kpis.append({
            "id": "total_revenue",
            "label": "Total Revenue",
            "formula": f'SUM("{col}")',
            "table": tbl,
            "column": col,
            "format": "currency",
        })

    # Quantity KPI
    if "quantity" in measures:
        entries = measures["quantity"]
        tbl = entries[0]["table"]
        col = entries[0]["column"]
        _sanitize_sql_identifier(tbl)
        _sanitize_sql_identifier(col)
        kpis.append({
            "id": "total_quantity",
            "label": "Total Units",
            "formula": f'SUM("{col}")',
            "table": tbl,
            "column": col,
            "format": "number",
        })

    # Profit KPI
    if "profit" in measures:
        entries = measures["profit"]
        tbl = entries[0]["table"]
        col = entries[0]["column"]
        _sanitize_sql_identifier(tbl)
        _sanitize_sql_identifier(col)
        kpis.append({
            "id": "total_profit",
            "label": "Total Profit",
            "formula": f'SUM("{col}")',
            "table": tbl,
            "column": col,
            "format": "currency",
        })
    elif "revenue" in measures and "cost" in measures:
        # Can calculate profit
        rev = measures["revenue"][0]
        cost = measures["cost"][0]
        if rev["table"] == cost["table"]:
            _sanitize_sql_identifier(rev["table"])
            _sanitize_sql_identifier(rev["column"])
            _sanitize_sql_identifier(cost["column"])
            kpis.append({
                "id": "total_profit",
                "label": "Gross Profit",
                "formula": f'SUM("{rev["column"]}" - "{cost["column"]}")',
                "table": rev["table"],
                "format": "currency",
            })

    # Spend KPI
    if "spend" in measures:
        entries = measures["spend"]
        tbl = entries[0]["table"]
        col = entries[0]["column"]
        _sanitize_sql_identifier(tbl)
        _sanitize_sql_identifier(col)
        kpis.append({
            "id": "total_spend",
            "label": "Total Spend",
            "formula": f'SUM("{col}")',
            "table": tbl,
            "column": col,
            "format": "currency",
        })

    # Conversions KPI
    if "conversions" in measures:
        entries = measures["conversions"]
        tbl = entries[0]["table"]
        col = entries[0]["column"]
        _sanitize_sql_identifier(tbl)
        _sanitize_sql_identifier(col)
        kpis.append({
            "id": "total_conversions",
            "label": "Total Conversions",
            "formula": f'SUM("{col}")',
            "table": tbl,
            "column": col,
            "format": "number",
        })

    # Row count as fallback "records" KPI
    for asset in data["assets"]:
        kpis.append({
            "id": f"records_{asset['asset_id']}",
            "label": f"Records — {asset['name']}",
            "formula": f'COUNT(*)',
            "table": asset["table_name"],
            "format": "number",
        })

    return kpis


def generate_dynamic_overview(workspace_id: str = DEFAULT_WORKSPACE) -> dict:
    """Generate overview KPIs dynamically from uploaded data."""
    data = discover_available_data(workspace_id)
    kpis = get_available_kpis(workspace_id)

    conn = _get_pg_connection()
    try:
        cur = conn.cursor()
        result = {"kpis": [], "trend": [], "breakdowns": {}}

        # Calculate each KPI
        for kpi in kpis:
            table = kpi.get("table")
            formula = kpi.get("formula")
            if not table or not formula:
                continue
            try:
                _sanitize_sql_identifier(table)
                query = f'SELECT {formula} FROM "{table}"'
                cur.execute(query)
                value = cur.fetchone()[0]
                result["kpis"].append({
                    "id": kpi["id"],
                    "label": kpi["label"],
                    "value": float(value) if value else 0,
                    "format": kpi.get("format", "number"),
                })
            except Exception as e:
                logger.warning(f"Failed to compute KPI {kpi['id']}: {e}")

        # Generate trend data if a date dimension exists
        date_dims = data["available_dimensions"].get("date", [])
        rev_measures = data["available_measures"].get("revenue", [])

        if date_dims and rev_measures:
            # Find a table that has both date and revenue
            for d_entry in date_dims:
                for r_entry in rev_measures:
                    if d_entry["table"] == r_entry["table"]:
                        tbl = d_entry["table"]
                        date_col = d_entry["column"]
                        rev_col = r_entry["column"]
                        try:
                            _sanitize_sql_identifier(tbl)
                            _sanitize_sql_identifier(date_col)
                            _sanitize_sql_identifier(rev_col)
                            cur.execute(f"""
                                SELECT TO_CHAR("{date_col}"::date, 'YYYY-MM') AS month,
                                       SUM("{rev_col}") AS revenue
                                FROM "{tbl}"
                                WHERE "{date_col}" IS NOT NULL
                                GROUP BY month ORDER BY month
                            """)
                            cols = [desc[0] for desc in cur.description]
                            result["trend"] = [dict(zip(cols, r)) for r in cur.fetchall()]
                            break
                        except Exception:
                            pass
                if result["trend"]:
                    break

        # Generate breakdowns by available dimensions
        for dim_name, dim_entries in data["available_dimensions"].items():
            for d_entry in dim_entries:
                for r_entry in rev_measures:
                    if d_entry["table"] == r_entry["table"]:
                        tbl = d_entry["table"]
                        dim_col = d_entry["column"]
                        rev_col = r_entry["column"]
                        try:
                            _sanitize_sql_identifier(tbl)
                            _sanitize_sql_identifier(dim_col)
                            _sanitize_sql_identifier(rev_col)
                            cur.execute(f"""
                                SELECT "{dim_col}" AS dimension,
                                       SUM("{rev_col}") AS revenue
                                FROM "{tbl}"
                                WHERE "{dim_col}" IS NOT NULL
                                GROUP BY dimension ORDER BY revenue DESC
                                LIMIT 20
                            """)
                            cols = [desc[0] for desc in cur.description]
                            result["breakdowns"][dim_name] = [dict(zip(cols, r)) for r in cur.fetchall()]
                        except Exception:
                            pass
                        break

        return result
    finally:
        conn.close()


def dynamic_query(sql_query: str) -> List[dict]:
    """Execute a dynamically generated SQL query safely."""
    # Basic SQL safety check
    forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
                 "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE"]
    upper_q = sql_query.upper().strip()
    for keyword in forbidden:
        if upper_q.startswith(keyword) or f" {keyword} " in upper_q:
            raise ValueError(f"Forbidden SQL operation: {keyword}")

    conn = _get_pg_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql_query)
        cols = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchall()
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


def has_workspace_data(workspace_id: str = DEFAULT_WORKSPACE) -> bool:
    """Check if the workspace has any user-uploaded data assets.
    This is the PRIMARY GATE for preventing silent legacy fallback.
    Returns True only if the workspace has at least one uploaded/active asset."""
    try:
        conn = _get_pg_connection()
    except Exception:
        return False  # No PostgreSQL = no workspace data
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM assets
            WHERE workspace_id = %s
            AND status = 'ready'
            AND source_type != 'seed'
            AND type = 'structured'
        """, (workspace_id,))
        count = cur.fetchone()[0]
        return count > 0
    except Exception:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_workspace_tables(workspace_id: str = DEFAULT_WORKSPACE) -> List[dict]:
    """Get all physical table names for uploaded data in the workspace."""
    try:
        conn = _get_pg_connection()
    except Exception:
        return []
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT asset_id, name, table_name, domain, row_count
            FROM assets
            WHERE workspace_id = %s
            AND status = 'ready'
            AND source_type != 'seed'
            AND table_name IS NOT NULL
        """, (workspace_id,))
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def build_dynamic_semantic_context(workspace_id: str = DEFAULT_WORKSPACE) -> str:
    """Build a text description of the semantic layer for the LLM context."""
    data = discover_available_data(workspace_id)
    lines = ["## Available Data Assets\n"]

    for asset in data["assets"]:
        lines.append(f"- **{asset['name']}** (table: {asset['table_name']}, {asset['row_count']} rows, domain: {asset['domain']})")

    # No legacy tables — workspace data only

    if data["available_measures"]:
        lines.append("\n## Available Measures (metrics)\n")
        for concept, entries in data["available_measures"].items():
            for e in entries:
                lines.append(f"- {concept}: {e['table']}.{e['column']} (confidence: {e['confidence']})")

    if data["available_dimensions"]:
        lines.append("\n## Available Dimensions (grouping columns)\n")
        for concept, entries in data["available_dimensions"].items():
            for e in entries:
                lines.append(f"- {concept}: {e['table']}.{e['column']} (confidence: {e['confidence']})")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# WORKSPACE-AWARE QUERY FUNCTIONS
# These replace legacy hardcoded queries when workspace data exists.
# ═══════════════════════════════════════════════════════════════════════

def _deduplicate_measure_entries(entries: List[dict],
                                 workspace_id: str = DEFAULT_WORKSPACE) -> List[dict]:
    """Deduplicate measure entries that belong to the same source file.
    Multi-sheet Excel uploads create multiple tables sharing a base prefix
    (e.g. 'myfile_abc123__sheet1' and 'myfile_abc123__sheet2').
    This picks the most granular (highest row count) table per base asset
    so each uploaded file is counted exactly once.
    """
    if not entries:
        return []

    # Physical table names are workspace-namespaced ('{ws}__{stem}_{hash}')
    # and multi-sheet siblings append '__{sheet}'. Strip the workspace
    # prefix BEFORE grouping so each uploaded file keeps its own base asset.
    ws_prefix = f"{_safe_table_name(workspace_id)}__"

    # Group by base asset: remainder of table name before first '__' if present
    groups: Dict[str, List[dict]] = {}
    for e in entries:
        tbl = e.get("table", "")
        stripped = tbl[len(ws_prefix):] if tbl.startswith(ws_prefix) else tbl
        base = stripped.split("__")[0] if "__" in stripped else stripped
        groups.setdefault(base, []).append(e)

    deduped: List[dict] = []
    for base, group in groups.items():
        if len(group) == 1:
            deduped.append(group[0])
        else:
            # Pick the table with the most rows (most granular)
            best = group[0]
            best_rows = 0
            for e in group:
                tbl = e.get("table", "")
                try:
                    _sanitize_sql_identifier(tbl)
                    col = e.get("column", "")
                    if col:
                        _sanitize_sql_identifier(col)
                    conn = _get_pg_connection()
                    try:
                        cur = conn.cursor()
                        cur.execute(f'SELECT COUNT(*) FROM "{tbl}"')
                        rc = cur.fetchone()[0] or 0
                        if rc > best_rows:
                            best_rows = rc
                            best = e
                    finally:
                        conn.close()
                except Exception:
                    pass
            deduped.append(best)
    return deduped


def workspace_total_revenue(workspace_id: str = DEFAULT_WORKSPACE) -> Optional[float]:
    """Get total revenue from ALL workspace data (summing across all tables, deduplicated).
    
    Returns None only when workspace genuinely has no revenue data.
    Raises RuntimeError on database failure — never converts DB errors to None.
    """
    data = discover_available_data(workspace_id)
    revenue_entries = data["available_measures"].get("revenue", [])
    if not revenue_entries:
        return None
    entries = _deduplicate_measure_entries(revenue_entries, workspace_id)
    total = 0.0
    conn = None
    try:
        conn = _get_pg_connection()
        cur = conn.cursor()
        for entry in entries:
            table = entry["table"]
            col = entry["column"]
            _sanitize_sql_identifier(table)
            _sanitize_sql_identifier(col)
            cur.execute(f'SELECT SUM("{col}") FROM "{table}"')
            val = cur.fetchone()[0]
            if val:
                total += float(val)
        return total
    except Exception as e:
        raise RuntimeError(f"Revenue calculation failed: {e}")
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def workspace_total_quantity(workspace_id: str = DEFAULT_WORKSPACE) -> Optional[float]:
    """Get total quantity from ALL workspace data (summing across all tables, deduplicated).
    
    Returns None only when workspace genuinely has no quantity data.
    Raises RuntimeError on database failure.
    """
    data = discover_available_data(workspace_id)
    entries = data["available_measures"].get("quantity", [])
    if not entries:
        return None
    entries = _deduplicate_measure_entries(entries, workspace_id)
    total = 0.0
    conn = None
    try:
        conn = _get_pg_connection()
        cur = conn.cursor()
        for entry in entries:
            table = entry["table"]
            col = entry["column"]
            try:
                _sanitize_sql_identifier(table)
                _sanitize_sql_identifier(col)
                cur.execute(f'SELECT SUM("{col}") FROM "{table}"')
                val = cur.fetchone()[0]
                if val:
                    total += float(val)
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                continue
        return total if total else None
    except Exception as e:
        raise RuntimeError(f"Quantity calculation failed: {e}")
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def workspace_total_spend(workspace_id: str = DEFAULT_WORKSPACE) -> Optional[float]:
    """Get total marketing spend from ALL workspace data (summing across all tables, deduplicated).
    
    Returns None only when workspace genuinely has no spend data.
    Raises RuntimeError on database failure.
    """
    data = discover_available_data(workspace_id)
    entries = data["available_measures"].get("spend", [])
    if not entries:
        return None
    entries = _deduplicate_measure_entries(entries, workspace_id)
    total = 0.0
    conn = None
    try:
        conn = _get_pg_connection()
        cur = conn.cursor()
        for entry in entries:
            table = entry["table"]
            col = entry["column"]
            try:
                _sanitize_sql_identifier(table)
                _sanitize_sql_identifier(col)
                cur.execute(f'SELECT SUM("{col}") FROM "{table}"')
                val = cur.fetchone()[0]
                if val:
                    total += float(val)
            except Exception:
                continue
        return total if total else None
    except Exception as e:
        raise RuntimeError(f"Spend calculation failed: {e}")
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


# Measures aggregated with SUM across tables (additive)
_SUM_AGGREGATE_MEASURES = {
    "revenue", "quantity", "spend", "profit", "cost", "impressions",
    "clicks", "conversions", "attribution_revenue", "orders", "ltv",
}
# Measures aggregated with AVG across tables (rate-like: discount %, margin %, price, rating)
_AVG_AGGREGATE_MEASURES = {
    "discount", "margin", "price", "rating", "roas", "discount_pct",
    "margin_pct", "discount_rate", "avg_rating",
}


def workspace_metric_total(metric: str, workspace_id: str = DEFAULT_WORKSPACE) -> Optional[float]:
    """Compute a total for ANY canonical measure across ALL workspace tables.

    SUM-style measures (revenue, quantity, spend, ...) are summed per table then
    across tables. AVG-style measures (discount, margin, ...) are combined as a
    row-count-weighted average so the result equals the average over all rows.

    Returns None when the measure is not present in the workspace.
    Raises RuntimeError on database failure.
    """
    if not metric:
        return None
    data = discover_available_data(workspace_id)
    entries = data["available_measures"].get(metric, [])
    if not entries:
        return None
    entries = _deduplicate_measure_entries(entries, workspace_id)
    is_avg = metric in _AVG_AGGREGATE_MEASURES or (
        metric not in _SUM_AGGREGATE_MEASURES and
        any("discount" in metric or "margin" in metric or "rating" in metric or "roas" in metric or "price" in metric for _ in [0])
    )
    conn = None
    try:
        conn = _get_pg_connection()
        cur = conn.cursor()
        total = 0.0
        weight_total = 0.0
        for entry in entries:
            table = entry["table"]
            col = entry["column"]
            _sanitize_sql_identifier(table)
            _sanitize_sql_identifier(col)
            if is_avg:
                cur.execute(f'SELECT AVG("{col}"), COUNT("{col}") FROM "{table}"')
                avg_val, cnt = cur.fetchone()
                if avg_val is not None and cnt:
                    total += float(avg_val) * float(cnt)
                    weight_total += float(cnt)
            else:
                cur.execute(f'SELECT SUM("{col}") FROM "{table}"')
                val = cur.fetchone()[0]
                if val:
                    total += float(val)
        if is_avg:
            return round(total / weight_total, 2) if weight_total else None
        return round(total, 2) if total else None
    except Exception as e:
        raise RuntimeError(f"Metric ({metric}) calculation failed: {e}")
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def workspace_metric_average(metric: str, workspace_id: str = DEFAULT_WORKSPACE) -> Optional[float]:
    """Row-count-weighted AVG for ANY canonical measure across workspace tables.

    Combines AVG per table weighted by row count so the result equals the
    average over every row in the workspace (e.g. mean revenue per order).
    Returns None when the measure is not present. Raises RuntimeError on DB failure.
    """
    if not metric:
        return None
    data = discover_available_data(workspace_id)
    entries = data["available_measures"].get(metric, [])
    if not entries:
        return None
    entries = _deduplicate_measure_entries(entries, workspace_id)
    conn = None
    try:
        conn = _get_pg_connection()
        cur = conn.cursor()
        total = 0.0
        weight_total = 0.0
        for entry in entries:
            table = entry["table"]
            col = entry["column"]
            _sanitize_sql_identifier(table)
            _sanitize_sql_identifier(col)
            cur.execute(f'SELECT AVG("{col}"), COUNT("{col}") FROM "{table}"')
            avg_val, cnt = cur.fetchone()
            if avg_val is not None and cnt:
                total += float(avg_val) * float(cnt)
                weight_total += float(cnt)
        return round(total / weight_total, 2) if weight_total else None
    except Exception as e:
        raise RuntimeError(f"Metric ({metric}) average failed: {e}")
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def workspace_year_coverage(workspace_id: str = DEFAULT_WORKSPACE) -> List[int]:
    """Distinct calendar years present across workspace date columns.

    Returns [] when no date dimension is mapped. Raises RuntimeError on DB failure
    (never silently reports an empty year set for a DB error).
    """
    try:
        data = discover_available_data(workspace_id)
    except Exception as e:
        raise RuntimeError(f"Year coverage failed: {e}")
    date_entries = data["available_dimensions"].get("date", [])
    if not date_entries:
        return []
    years: set = set()
    conn = None
    try:
        conn = _get_pg_connection()
        cur = conn.cursor()
        for e in date_entries:
            tbl = e["table"]
            col = e["column"]
            try:
                _sanitize_sql_identifier(tbl)
                _sanitize_sql_identifier(col)
                cur.execute(f'SELECT DISTINCT EXTRACT(YEAR FROM "{col}"::date) FROM "{tbl}" WHERE "{col}" IS NOT NULL')
                for row in cur.fetchall():
                    if row[0] is not None:
                        years.add(int(row[0]))
            except Exception:
                continue
        return sorted(years)
    except Exception as e:
        raise RuntimeError(f"Year coverage query failed: {e}")
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def workspace_metric_by_dimension(
    metric: str = "revenue",
    dimension: str = "region",
    workspace_id: str = DEFAULT_WORKSPACE,
    limit: Optional[int] = None,
    order: str = "desc",
) -> List[dict]:
    """Compute a canonical measure grouped by a dimension across ALL workspace tables.

    Rows are merged in Python across tables (each table queried separately, then
    grouped values summed / weighted-averaged by shared dimension value).
    order="desc" sorts high→low (top N); order="asc" sorts low→high (bottom N).
    Returns [] when the measure or dimension is unavailable.
    """
    try:
        data = discover_available_data(workspace_id)
    except Exception:
        return []
    measure_entries = data["available_measures"].get(metric, [])
    dim_entries = data["available_dimensions"].get(dimension, [])
    if not measure_entries or not dim_entries:
        return []

    measure_by_table = {e["table"]: e for e in measure_entries}
    dim_by_table = {e["table"]: e for e in dim_entries}
    common_tables = set(measure_by_table.keys()) & set(dim_by_table.keys())
    if not common_tables:
        return []

    deduped_measure = _deduplicate_measure_entries(measure_entries, workspace_id)
    deduped_tables = {e["table"] for e in deduped_measure}
    target_tables = (common_tables & deduped_tables) or common_tables

    is_avg = metric in _AVG_AGGREGATE_MEASURES or (
        metric not in _SUM_AGGREGATE_MEASURES
        and any(k in metric for k in ("discount", "margin", "rating", "roas", "price"))
    )
    sums: Dict[str, float] = {}
    weights: Dict[str, float] = {}
    try:
        conn = _get_pg_connection()
    except Exception:
        return []
    try:
        cur = conn.cursor()
        for tbl in target_tables:
            m = measure_by_table[tbl]
            d = dim_by_table[tbl]
            m_col = m["column"]
            d_col = d["column"]
            _sanitize_sql_identifier(tbl)
            _sanitize_sql_identifier(m_col)
            _sanitize_sql_identifier(d_col)
            try:
                if is_avg:
                    cur.execute(f"""
                        SELECT "{d_col}" AS dim_val, AVG("{m_col}") AS val, COUNT("{m_col}") AS n
                        FROM "{tbl}" WHERE "{d_col}" IS NOT NULL AND "{m_col}" IS NOT NULL
                        GROUP BY dim_val
                    """)
                    for row in cur.fetchall():
                        key = str(row[0])
                        v = float(row[1] or 0)
                        n = float(row[2] or 0)
                        sums[key] = sums.get(key, 0.0) + v * n
                        weights[key] = weights.get(key, 0.0) + n
                else:
                    cur.execute(f"""
                        SELECT "{d_col}" AS dim_val, SUM("{m_col}") AS val
                        FROM "{tbl}" WHERE "{d_col}" IS NOT NULL
                        GROUP BY dim_val
                    """)
                    for row in cur.fetchall():
                        key = str(row[0])
                        sums[key] = sums.get(key, 0.0) + float(row[1] or 0)
            except Exception:
                continue
        if not sums:
            return []
        rows = []
        for key, val in sums.items():
            if is_avg:
                w = weights.get(key, 0.0)
                if w:
                    rows.append({"dimension": key, metric: round(val / w, 2)})
            else:
                rows.append({"dimension": key, metric: round(val, 2)})
        rows.sort(key=lambda x: x.get(metric, 0), reverse=(order != "asc"))
        if limit:
            rows = rows[:limit]
        return rows
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def workspace_dimension_values(dimension: str, workspace_id: str = DEFAULT_WORKSPACE) -> List[str]:
    """Distinct values for a dimension across ALL workspace tables.

    Returns the actual stored values (original casing, sorted) so query
    resolution can match user language against real data instead of a
    hardcoded vocabulary. Returns [] when the dimension is unavailable.
    """
    try:
        data = discover_available_data(workspace_id)
    except Exception:
        return []
    dim_entries = data["available_dimensions"].get(dimension, [])
    if not dim_entries:
        return []
    by_table = {e["table"]: e for e in dim_entries}
    seen: Dict[str, str] = {}
    conn = None
    try:
        conn = _get_pg_connection()
        cur = conn.cursor()
        for tbl, d in by_table.items():
            d_col = d["column"]
            try:
                _sanitize_sql_identifier(tbl)
                _sanitize_sql_identifier(d_col)
                cur.execute(f'SELECT DISTINCT "{d_col}" AS v FROM "{tbl}" WHERE "{d_col}" IS NOT NULL')
                for row in cur.fetchall():
                    key = str(row[0]).strip()
                    if key:
                        seen.setdefault(key.lower(), key)
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                continue
        return [seen[k] for k in sorted(seen)]
    except Exception:
        return []
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def workspace_revenue_by_dimension(dimension: str, workspace_id: str = DEFAULT_WORKSPACE) -> List[dict]:
    """Get revenue grouped by a dimension across ALL matching tables."""
    try:
        data = discover_available_data(workspace_id)
    except Exception:
        return []
    rev_entries = data["available_measures"].get("revenue", [])
    dim_entries = data["available_dimensions"].get(dimension, [])
    if not rev_entries or not dim_entries:
        return []

    # Build pairs: (rev_table, rev_col, dim_table, dim_col) where both exist in the same table
    rev_by_table = {e["table"]: e for e in rev_entries}
    dim_by_table = {e["table"]: e for e in dim_entries}
    common_tables = set(rev_by_table.keys()) & set(dim_by_table.keys())
    if not common_tables:
        return []

    # Deduplicate revenue entries
    rev_entries_deduped = _deduplicate_measure_entries(rev_entries, workspace_id)
    rev_tables_deduped = {e["table"] for e in rev_entries_deduped}
    # Only use tables that are both in common and deduped
    target_tables = common_tables & rev_tables_deduped
    if not target_tables:
        target_tables = common_tables  # fallback

    merged: Dict[str, float] = {}
    try:
        conn = _get_pg_connection()
    except Exception:
        return []
    try:
        cur = conn.cursor()
        for tbl in target_tables:
            rev = rev_by_table[tbl]
            dim = dim_by_table[tbl]
            rev_col = rev["column"]
            dim_col = dim["column"]
            _sanitize_sql_identifier(tbl)
            _sanitize_sql_identifier(rev_col)
            _sanitize_sql_identifier(dim_col)
            try:
                cur.execute(f"""
                    SELECT "{dim_col}" AS dim_val, SUM("{rev_col}") AS revenue
                    FROM "{tbl}" WHERE "{dim_col}" IS NOT NULL
                    GROUP BY dim_val
                """)
                for row in cur.fetchall():
                    key = str(row[0])
                    merged[key] = merged.get(key, 0.0) + float(row[1] or 0)
            except Exception:
                continue
        if not merged:
            return []
        result = [{"dimension": k, "revenue": round(v, 2)} for k, v in merged.items()]
        result.sort(key=lambda x: x["revenue"], reverse=True)
        return result
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def workspace_metric_trend(metric: str = "revenue", workspace_id: str = DEFAULT_WORKSPACE) -> List[dict]:
    """Get monthly trend for ANY canonical measure across all workspace tables.

    Combines tables that contain BOTH the measure column and a date column,
    merging by YYYY-MM bucket. Returns rows [{month, <metric>: value}].
    """
    try:
        data = discover_available_data(workspace_id)
    except Exception:
        return []
    measure_entries = data["available_measures"].get(metric, [])
    date_entries = data["available_dimensions"].get("date", [])
    if not measure_entries or not date_entries:
        return []
    measure_by_table = {e["table"]: e for e in measure_entries}
    date_by_table = {e["table"]: e for e in date_entries}
    common = set(measure_by_table.keys()) & set(date_by_table.keys())
    if not common:
        return []
    deduped = _deduplicate_measure_entries(measure_entries, workspace_id)
    deduped_tables = {e["table"] for e in deduped}
    target_tables = (common & deduped_tables) or common
    is_avg = metric in _AVG_AGGREGATE_MEASURES or (
        metric not in _SUM_AGGREGATE_MEASURES
        and any(k in metric for k in ("discount", "margin", "rating", "roas", "price"))
    )
    sums: Dict[str, float] = {}
    weights: Dict[str, float] = {}
    try:
        conn = _get_pg_connection()
    except Exception:
        return []
    try:
        cur = conn.cursor()
        for tbl in target_tables:
            m = measure_by_table[tbl]
            d = date_by_table[tbl]
            m_col = m["column"]
            d_col = d["column"]
            _sanitize_sql_identifier(tbl)
            _sanitize_sql_identifier(m_col)
            _sanitize_sql_identifier(d_col)
            try:
                if is_avg:
                    cur.execute(f"""
                        SELECT TO_CHAR("{d_col}"::date, 'YYYY-MM') AS month,
                               AVG("{m_col}") AS val, COUNT("{m_col}") AS n
                        FROM "{tbl}"
                        WHERE "{d_col}" IS NOT NULL AND "{m_col}" IS NOT NULL
                        GROUP BY month ORDER BY month
                    """)
                    for row in cur.fetchall():
                        key = str(row[0])
                        v = float(row[1] or 0)
                        n = float(row[2] or 0)
                        sums[key] = sums.get(key, 0.0) + v * n
                        weights[key] = weights.get(key, 0.0) + n
                else:
                    cur.execute(f"""
                        SELECT TO_CHAR("{d_col}"::date, 'YYYY-MM') AS month,
                               SUM("{m_col}") AS val
                        FROM "{tbl}"
                        WHERE "{d_col}" IS NOT NULL
                        GROUP BY month ORDER BY month
                    """)
                    for row in cur.fetchall():
                        key = str(row[0])
                        sums[key] = sums.get(key, 0.0) + float(row[1] or 0)
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                continue
        if not sums:
            return []
        rows = []
        for key, val in sums.items():
            if is_avg:
                w = weights.get(key, 0.0)
                if w:
                    rows.append({"month": key, metric: round(val / w, 2)})
            else:
                rows.append({"month": key, metric: round(val, 2)})
        rows.sort(key=lambda x: x["month"])
        return rows
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def workspace_revenue_trend(workspace_id: str = DEFAULT_WORKSPACE) -> List[dict]:
    """Get monthly revenue trend from workspace data."""
    try:
        data = discover_available_data(workspace_id)
    except Exception:
        return []
    rev_entries = data["available_measures"].get("revenue", [])
    date_entries = data["available_dimensions"].get("date", [])
    if not rev_entries or not date_entries:
        return []
    for rev in rev_entries:
        for dt in date_entries:
            if rev["table"] == dt["table"]:
                _sanitize_sql_identifier(rev["table"])
                _sanitize_sql_identifier(rev["column"])
                _sanitize_sql_identifier(dt["column"])
                try:
                    conn = _get_pg_connection()
                except Exception:
                    return []
                try:
                    cur = conn.cursor()
                    cur.execute(f"""
                        SELECT TO_CHAR("{dt["column"]}"::date, 'YYYY-MM') AS month,
                               SUM("{rev["column"]}") AS revenue
                        FROM "{rev["table"]}"
                        WHERE "{dt["column"]}" IS NOT NULL
                        GROUP BY month ORDER BY month
                    """)
                    cols = [d[0] for d in cur.description]
                    return [dict(zip(cols, r)) for r in cur.fetchall()]
                except Exception:
                    return []
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
    return []


def workspace_top_entities(limit: int = 10, workspace_id: str = DEFAULT_WORKSPACE) -> List[dict]:
    """Get top entities by revenue across ALL matching tables."""
    try:
        data = discover_available_data(workspace_id)
    except Exception:
        return []
    rev_entries = data["available_measures"].get("revenue", [])
    prod_entries = data["available_dimensions"].get("product", [])
    if not rev_entries:
        return []

    rev_by_table = {e["table"]: e for e in rev_entries}
    prod_by_table = {e["table"]: e for e in prod_entries}
    common_tables = set(rev_by_table.keys()) & set(prod_by_table.keys())
    if not common_tables:
        return []

    rev_entries_deduped = _deduplicate_measure_entries(rev_entries, workspace_id)
    rev_tables_deduped = {e["table"] for e in rev_entries_deduped}
    target_tables = common_tables & rev_tables_deduped
    if not target_tables:
        target_tables = common_tables

    merged: Dict[str, float] = {}
    try:
        conn = _get_pg_connection()
    except Exception:
        return []
    try:
        cur = conn.cursor()
        for tbl in target_tables:
            rev = rev_by_table[tbl]
            prod = prod_by_table[tbl]
            rev_col = rev["column"]
            prod_col = prod["column"]
            _sanitize_sql_identifier(tbl)
            _sanitize_sql_identifier(rev_col)
            _sanitize_sql_identifier(prod_col)
            try:
                cur.execute(f"""
                    SELECT "{prod_col}" AS name, SUM("{rev_col}") AS revenue
                    FROM "{tbl}" WHERE "{prod_col}" IS NOT NULL
                    GROUP BY name
                """)
                for row in cur.fetchall():
                    key = str(row[0])
                    merged[key] = merged.get(key, 0.0) + float(row[1] or 0)
            except Exception:
                continue
        if not merged:
            return []
        sorted_items = sorted(merged.items(), key=lambda x: x[1], reverse=True)
        return [{"name": k, "revenue": round(v, 2)} for k, v in sorted_items[:limit]]
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def workspace_row_count(workspace_id: str = DEFAULT_WORKSPACE) -> int:
    """Get total row count across all workspace assets (COUNT(*), DB-verified)."""
    try:
        data = discover_available_data(workspace_id)
    except Exception:
        return 0
    total = 0
    conn = None
    try:
        conn = _get_pg_connection()
        cur = conn.cursor()
        for asset in data.get("assets", []):
            tbl = asset.get("table_name")
            if not tbl:
                continue
            try:
                _sanitize_sql_identifier(tbl)
                cur.execute(f'SELECT COUNT(*) FROM "{tbl}"')
                total += int(cur.fetchone()[0] or 0)
            except Exception:
                continue
        return total
    except Exception:
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def workspace_column_names(table_name: str) -> List[str]:
    """Get column names for a table."""
    _sanitize_sql_identifier(table_name)
    try:
        conn = _get_pg_connection()
    except Exception:
        return []
    try:
        cur = conn.cursor()
        cur.execute(f'SELECT * FROM "{table_name}" LIMIT 0')
        return [desc[0] for desc in cur.description]
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass
