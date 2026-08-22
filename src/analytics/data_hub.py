"""
Data Hub — CSV/XLSX upload, profiling, validation, and semantic mapping.

Manages uploaded datasets (separate from the pre-built warehouse.db),
profiles them automatically, validates data quality, and maps semantic types.
"""
import io
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src import config

# In-memory dataset store (production would use a database)
_datasets: Dict[str, dict] = {}


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
    semantic_type: str = "unknown"  # revenue, date, category, id, text, percentage, etc.


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


# ── Semantic type detection ──────────────────────────────────────────────

SEMANTIC_PATTERNS = {
    "revenue": ["revenue", "sales", "amount", "income", "profit", "margin", "spend", "cost", "price", "ltv", "cac", "aov"],
    "percentage": ["rate", "ratio", "percent", "pct", "margin", "discount", "ctr", "roas", "growth"],
    "count": ["count", "units", "quantity", "orders", "customers", "impressions", "clicks", "conversions", "reviews"],
    "date": ["date", "time", "created", "updated", "period", "month", "quarter", "year"],
    "id": ["id", "key", "code"],
    "category": ["category", "segment", "channel", "region", "type", "status", "class"],
    "text": ["name", "description", "title", "text", "review", "comment", "note"],
    "rating": ["rating", "score", "stars"],
}

# Semantic definitions for the metric layer
METRIC_DEFINITIONS = {
    "Revenue": "SUM(revenue) — Total sales revenue",
    "Units Sold": "SUM(quantity) — Total units sold",
    "Gross Profit": "SUM(revenue - cost) — Revenue minus cost of goods",
    "Gross Margin": "100 * SUM(revenue - cost) / SUM(revenue) — Profit margin percentage",
    "Average Selling Price": "AVG(selling_price) — Mean selling price",
    "Average Order Value": "SUM(revenue) / COUNT(DISTINCT order_id) — Revenue per order",
    "Discount %": "AVG(discount) — Mean discount percentage applied",
    "ROAS": "SUM(attributed_revenue) / SUM(spend) — Return on ad spend",
    "CTR": "SUM(clicks) / SUM(impressions) — Click-through rate",
    "Conversion Rate": "SUM(conversions) / SUM(clicks) — Conversion rate",
    "CPC": "SUM(spend) / SUM(clicks) — Cost per click",
    "CPA": "SUM(spend) / SUM(conversions) — Cost per acquisition",
    "CAC": "SUM(spend) / COUNT(DISTINCT new_customer_id) — Customer acquisition cost",
    "LTV": "AVG(lifetime_value) — Customer lifetime value",
    "Repeat Purchase Rate": "COUNT(orders > 1) / COUNT(DISTINCT customer_id)",
}

DIMENSION_DEFINITIONS = {
    "Product": "product_id, product_name, category, subcategory",
    "Category": "product category grouping",
    "Subcategory": "subcategory within a category",
    "Customer": "customer_id, segment, region",
    "Customer Segment": "Premium, Regular, Budget, New Customer",
    "Region": "geographic region (North America, Europe, APAC, etc.)",
    "Campaign": "campaign_id, campaign_name, channel",
    "Channel": "marketing channel (Search Ads, Social Media, etc.)",
    "Date": "order_date, start_date, end_date",
}


def _detect_semantic_type(col_name: str, dtype: str, sample_values: list) -> str:
    """Detect the semantic type of a column based on name patterns and data."""
    name_lower = col_name.lower().replace(" ", "_").replace("-", "_")

    # Check name patterns
    for stype, patterns in SEMANTIC_PATTERNS.items():
        for pattern in patterns:
            if pattern in name_lower:
                return stype

    # Heuristic: date-like strings
    if dtype == "object" and sample_values:
        try:
            pd.to_datetime(sample_values[:5])
            return "date"
        except (ValueError, TypeError):
            pass

    # Heuristic: numeric with small range might be rating
    if dtype in ("int64", "float64") and sample_values:
        try:
            vals = [float(v) for v in sample_values if v is not None]
            if vals and 0 < max(vals) <= 5 and len(set(vals)) <= 10:
                return "rating"
        except (ValueError, TypeError):
            pass

    return "unknown"


def _calculate_quality_score(profile: DatasetProfile) -> float:
    """Calculate a data quality score (0-100) from profiling results."""
    score = 100.0

    # Penalize for missing values
    total_cells = profile.row_count * profile.col_count
    if total_cells > 0:
        total_nulls = sum(c.null_count for c in profile.columns)
        null_penalty = (total_nulls / total_cells) * 40  # up to -40 points
        score -= null_penalty

    # Penalize for duplicates
    if profile.row_count > 0:
        dup_penalty = (profile.duplicate_rows / profile.row_count) * 20  # up to -20 points
        score -= dup_penalty

    # Penalize for low unique counts (possible constant columns)
    low_unique_cols = sum(1 for c in profile.columns if c.unique_count <= 1 and profile.row_count > 1)
    if profile.col_count > 0:
        score -= (low_unique_cols / profile.col_count) * 10

    # Penalize for unknown semantic types
    unknown_cols = sum(1 for c in profile.columns if c.semantic_type == "unknown")
    if profile.col_count > 0:
        score -= (unknown_cols / profile.col_count) * 10

    return max(0, min(100, round(score, 1)))


def _validate_data(df: pd.DataFrame, filename: str) -> List[dict]:
    """Detect data quality issues."""
    issues = []

    # Missing values
    for col in df.columns:
        null_count = int(df[col].isna().sum())
        if null_count > 0:
            issues.append({
                "type": "missing_values",
                "severity": "warning" if null_count / len(df) < 0.1 else "error",
                "column": col,
                "count": null_count,
                "message": f"⚠ {null_count} missing values in column '{col}' ({null_count/len(df)*100:.1f}%)",
            })

    # Duplicate rows
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        issues.append({
            "type": "duplicate_rows",
            "severity": "warning",
            "count": dup_count,
            "message": f"⚠ {dup_count} duplicate rows detected",
        })

    # Negative revenue/cost (if columns exist)
    for col in df.columns:
        if df[col].dtype in ("int64", "float64"):
            col_lower = col.lower()
            neg_count = int((df[col] < 0).sum())
            if neg_count > 0 and any(kw in col_lower for kw in ["revenue", "sales", "amount", "cost", "price", "spend"]):
                issues.append({
                    "type": "negative_values",
                    "severity": "warning",
                    "column": col,
                    "count": neg_count,
                    "message": f"⚠ {neg_count} negative values in '{col}' — may indicate returns or data errors",
                })

    # Check for potential ID columns with duplicates
    for col in df.columns:
        col_lower = col.lower()
        if "id" in col_lower:
            dup_ids = int(df[col].duplicated().sum())
            if dup_ids > 0:
                issues.append({
                    "type": "duplicate_ids",
                    "severity": "error",
                    "column": col,
                    "count": dup_ids,
                    "message": f"⚠ {dup_ids} duplicate values in ID column '{col}'",
                })

    return issues


def ingest_file(file_bytes: bytes, filename: str) -> dict:
    """
    Full ingestion pipeline: Upload → Validate → Parse → Profile → Map → Store.
    Returns the full profile and dataset_id.
    """
    ext = Path(filename).suffix.lower()
    file_hash = hashlib.md5(file_bytes).hexdigest()[:12]
    dataset_id = f"{Path(filename).stem}_{file_hash}"

    datasets_info = []

    if ext == ".csv":
        df = pd.read_csv(io.BytesIO(file_bytes))
        profile = _profile_dataset(df, filename, ext, len(file_bytes), dataset_id)
        _datasets[dataset_id] = {
            "id": dataset_id,
            "filename": filename,
            "dataframe": df,
            "profile": profile,
        }
        datasets_info.append(profile)

    elif ext in (".xlsx", ".xls"):
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            sheet_id = f"{dataset_id}__{sheet_name}"
            profile = _profile_dataset(df, filename, ext, len(file_bytes), sheet_id, sheet_name=sheet_name)
            _datasets[sheet_id] = {
                "id": sheet_id,
                "filename": filename,
                "sheet_name": sheet_name,
                "dataframe": df,
                "profile": profile,
            }
            datasets_info.append(profile)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    return {
        "dataset_ids": [d.dataset_id for d in datasets_info],
        "profiles": [_profile_to_dict(p) for p in datasets_info],
        "total_rows": sum(p.row_count for p in datasets_info),
        "total_columns": sum(p.col_count for p in datasets_info),
    }


def _profile_dataset(df: pd.DataFrame, filename: str, ext: str,
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
        cp.semantic_type = _detect_semantic_type(str(col), str(series.dtype), sample)
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
        quality_score=0,  # calculated below
        uploaded_at=datetime.now().isoformat(),
        sheet_name=sheet_name,
        issues=issues,
    )
    profile.quality_score = _calculate_quality_score(profile)
    return profile


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
                "median_val": c.median_val, "semantic_type": c.semantic_type,
            }
            for c in p.columns
        ],
        "issues": p.issues,
    }


def list_datasets() -> List[dict]:
    """List all uploaded datasets with summary info."""
    result = []
    seen_files = set()
    for ds_id, ds in _datasets.items():
        filename = ds["filename"]
        if filename not in seen_files:
            # Summarize all sheets for this file
            file_datasets = {k: v for k, v in _datasets.items() if v["filename"] == filename}
            total_rows = sum(v["profile"].row_count for v in file_datasets.values())
            sheets = [v.get("sheet_name") for v in file_datasets.values()]
            result.append({
                "dataset_id": ds_id,
                "filename": filename,
                "file_type": ds["profile"].file_type,
                "file_size_bytes": ds["profile"].file_size_bytes,
                "total_rows": total_rows,
                "total_columns": ds["profile"].col_count,
                "sheets": sheets if len(sheets) > 1 else None,
                "quality_score": ds["profile"].quality_score,
                "uploaded_at": ds["profile"].uploaded_at,
                "issue_count": len(ds["profile"].issues),
            })
            seen_files.add(filename)
    return result


def get_dataset(dataset_id: str) -> Optional[dict]:
    """Get full dataset info including profile."""
    ds = _datasets.get(dataset_id)
    if not ds:
        return None
    return {
        "profile": _profile_to_dict(ds["profile"]),
        "preview": ds["dataframe"].head(20).to_dict(orient="records"),
        "semantic_mapping": {
            "metrics": METRIC_DEFINITIONS,
            "dimensions": DIMENSION_DEFINITIONS,
        },
    }


def delete_dataset(dataset_id: str) -> bool:
    """Delete a dataset and all its sheets."""
    if dataset_id not in _datasets:
        return False
    filename = _datasets[dataset_id]["filename"]
    to_delete = [k for k, v in _datasets.items() if v["filename"] == filename]
    for k in to_delete:
        del _datasets[k]
    return True
