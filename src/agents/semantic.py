"""
Semantic Layer — authoritative resolver for metrics, dimensions, aliases, and grain.

Maps user language to database columns and aggregation logic.

User says: "revenue"     → SELECT SUM(revenue) FROM workspace
User says: "sales"       → SELECT SUM(revenue) FROM workspace  (alias)
User says: "by region"   → GROUP BY region
User says: "total spend" → SELECT SUM(spend) FROM workspace

This module is the SINGLE SOURCE OF TRUTH for:
  - Metric definitions (revenue, sales, units, etc.)
  - Dimension definitions (region, category, product, etc.)
  - Alias resolution (turnover → revenue, qty → quantity)
  - Aggregation rules (SUM for revenue, AVG for margin, COUNT for orders)
  - Grain detection (order-level, daily, monthly, product-level)

NO hardcoded table names — everything is discovered dynamically
from the workspace's actual schema.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("agents.semantic")


@dataclass
class MetricDefinition:
    """Defines a metric with its SQL representation."""
    name: str
    aliases: List[str]
    sql_expression: str  # e.g. "SUM(revenue)" or "COUNT(*)"
    column: str  # raw column name
    aggregation: str  # SUM, AVG, COUNT, etc.
    format: str  # currency, number, percentage
    description: str = ""


@dataclass
class DimensionDefinition:
    """Defines a dimension for GROUP BY."""
    name: str
    aliases: List[str]
    column: str  # raw column name
    description: str = ""


@dataclass
class ResolvedQuery:
    """The resolved semantic plan for a query."""
    metrics: List[MetricDefinition]
    dimensions: List[DimensionDefinition]
    tables: List[str]  # resolved table names
    filters: Dict[str, str] = field(default_factory=dict)
    grain: str = "order"  # order, daily, monthly, product, region
    order_by: str = ""
    limit: int = 100
    needs_rag: bool = False
    rag_query: str = ""


# ──────────────────────────────────────────────────────────────────────
# Default metric/dimension definitions (alias maps)
# ──────────────────────────────────────────────────────────────────────

# These are the canonical metric definitions.
# The resolver maps user language → these → SQL.
_DEFAULT_METRICS = {
    "revenue": MetricDefinition(
        name="revenue", aliases=["revenue", "sales", "income", "turnover", "net sales", "total revenue"],
        sql_expression='SUM("{col}")', column="revenue", aggregation="SUM",
        format="currency", description="Total revenue",
    ),
    "quantity": MetricDefinition(
        name="quantity", aliases=["units", "quantity", "volume", "units sold", "qty"],
        sql_expression='SUM("{col}")', column="quantity", aggregation="SUM",
        format="number", description="Total units/quantity",
    ),
    "spend": MetricDefinition(
        name="spend", aliases=["spend", "marketing spend", "ad spend", "advertising spend", "total spend"],
        sql_expression='SUM("{col}")', column="spend", aggregation="SUM",
        format="currency", description="Total marketing/advertising spend",
    ),
    "margin": MetricDefinition(
        name="margin", aliases=["margin", "gross margin", "profit margin", "margin pct"],
        sql_expression='AVG("{col}")', column="margin", aggregation="AVG",
        format="percentage", description="Average margin percentage",
    ),
    "profit": MetricDefinition(
        name="profit", aliases=["profit", "gross profit", "net profit", "total profit"],
        sql_expression='SUM("{col}")', column="profit", aggregation="SUM",
        format="currency", description="Total profit",
    ),
    "discount": MetricDefinition(
        name="discount", aliases=["discount", "discount rate", "markdown", "promo", "promotion discount"],
        sql_expression='AVG("{col}")', column="discount", aggregation="AVG",
        format="percentage", description="Average discount rate",
    ),
    "roas": MetricDefinition(
        name="roas", aliases=["roas", "return on ad spend"],
        sql_expression='AVG("{col}")', column="roas", aggregation="AVG",
        format="number", description="Return on ad spend",
    ),
    "attributed_revenue": MetricDefinition(
        name="attributed_revenue", aliases=["attributed revenue", "campaign revenue", "ad revenue"],
        sql_expression='SUM("{col}")', column="attributed_revenue", aggregation="SUM",
        format="currency", description="Revenue attributed to campaigns",
    ),
    "orders": MetricDefinition(
        name="orders", aliases=["orders", "order count", "number of orders", "total orders"],
        sql_expression='COUNT(*)', column="*", aggregation="COUNT",
        format="number", description="Total order count",
    ),
    "customers": MetricDefinition(
        name="customers", aliases=["customers", "customer count", "unique customers", "buyer count"],
        sql_expression='COUNT(DISTINCT "{col}")', column="customer_id", aggregation="COUNT_DISTINCT",
        format="number", description="Unique customer count",
    ),
}

_DEFAULT_DIMENSIONS = {
    "region": DimensionDefinition(
        name="region", aliases=["region", "territory", "market", "area", "geography"],
        column="region", description="Geographic region",
    ),
    "category": DimensionDefinition(
        name="category", aliases=["category", "categories", "product category", "product line"],
        column="category", description="Product category",
    ),
    "product": DimensionDefinition(
        name="product", aliases=["product", "products", "product name", "item", "sku"],
        column="product", description="Product name",
    ),
    "month": DimensionDefinition(
        name="month", aliases=["month", "monthly", "time period", "date"],
        column="month", description="Month",
    ),
    "quarter": DimensionDefinition(
        name="quarter", aliases=["quarter", "quarterly", "q1", "q2", "q3", "q4"],
        column="quarter", description="Quarter",
    ),
    "year": DimensionDefinition(
        name="year", aliases=["year", "yearly", "annual", "annually"],
        column="year", description="Year",
    ),
    "segment": DimensionDefinition(
        name="segment", aliases=["segment", "customer segment", "segment name"],
        column="segment", description="Customer segment",
    ),
    "channel": DimensionDefinition(
        name="channel", aliases=["channel", "sales channel", "distribution channel"],
        column="channel", description="Sales channel",
    ),
    "customer": DimensionDefinition(
        name="customer", aliases=["customer", "customers", "buyer", "client"],
        column="customer_id", description="Customer",
    ),
    "campaign": DimensionDefinition(
        name="campaign", aliases=["campaign", "campaign name", "ad campaign"],
        column="campaign_name", description="Marketing campaign",
    ),
    "product_name": DimensionDefinition(
        name="product_name", aliases=["product name", "product", "item name"],
        column="product_name", description="Product name",
    ),
}


class SemanticResolver:
    """
    Resolves user language to semantic plan.
    
    Flow:
        User Query
            → Tokenize & normalize
            → Match metrics (aliases → canonical metric)
            → Match dimensions (aliases → canonical dimension)
            → Detect grain
            → Detect filters (if any)
            → Produce ResolvedQuery
    """

    def __init__(self):
        self._metrics = dict(_DEFAULT_METRICS)
        self._dimensions = dict(_DEFAULT_DIMENSIONS)
        self._dynamic_metrics: Dict[str, MetricDefinition] = {}
        self._dynamic_dimensions: Dict[str, DimensionDefinition] = {}

    def register_metric(self, metric: MetricDefinition):
        """Register a custom metric (e.g. from workspace schema discovery)."""
        self._dynamic_metrics[metric.name] = metric

    def register_dimension(self, dim: DimensionDefinition):
        """Register a custom dimension."""
        self._dynamic_dimensions[dim.name] = dim

    def resolve(self, query: str, route: str = "ANALYTICS") -> ResolvedQuery:
        """
        Resolve a user query into a semantic plan.
        
        Args:
            query: The user's natural language query
            route: The route type from FastRouter
            
        Returns:
            ResolvedQuery with metrics, dimensions, tables, etc.
        """
        text = query.lower().strip()
        
        # ── Match metrics ──
        matched_metrics = self._match_metrics(text)
        
        # ── Match dimensions ──
        matched_dimensions = self._match_dimensions(text)
        
        # ── Detect grain ──
        grain = self._detect_grain(text, matched_dimensions)
        
        # ── Detect if RAG is needed ──
        needs_rag = route in ("KNOWLEDGE", "HYBRID")
        
        # ── Build resolved query ──
        resolved = ResolvedQuery(
            metrics=matched_metrics,
            dimensions=matched_dimensions,
            tables=[],  # Will be populated by workspace discovery
            grain=grain,
            needs_rag=needs_rag,
            rag_query=query if needs_rag else "",
        )
        
        logger.info(
            "Semantic resolve: metrics=%s, dimensions=%s, grain=%s",
            [m.name for m in matched_metrics],
            [d.name for d in matched_dimensions],
            grain,
        )
        
        return resolved

    def _match_metrics(self, text: str) -> List[MetricDefinition]:
        """Find metrics mentioned in the query."""
        all_metrics = {**self._metrics, **self._dynamic_metrics}
        matched = []
        seen = set()
        
        for metric_def in all_metrics.values():
            for alias in metric_def.aliases:
                # Use word boundary matching for short aliases
                if len(alias) <= 3:
                    pattern = r"\b" + re.escape(alias) + r"\b"
                else:
                    pattern = re.escape(alias)
                
                if re.search(pattern, text, re.IGNORECASE):
                    if metric_def.name not in seen:
                        matched.append(metric_def)
                        seen.add(metric_def.name)
                    break
        
        return matched

    def _match_dimensions(self, text: str) -> List[DimensionDefinition]:
        """Find dimensions mentioned in the query."""
        all_dims = {**self._dimensions, **self._dynamic_dimensions}
        matched = []
        seen = set()
        
        # Check for "by X" pattern first (strongest signal)
        by_pattern = re.findall(r"\bby\s+(\w+)", text)
        for dim_word in by_pattern:
            for dim_def in all_dims.values():
                if dim_word in dim_def.aliases or dim_def.column == dim_word:
                    if dim_def.name not in seen:
                        matched.append(dim_def)
                        seen.add(dim_def.name)
                    break
        
        # Also check for dimension names without "by"
        for dim_def in all_dims.values():
            if dim_def.name in seen:
                continue
            for alias in dim_def.aliases:
                if len(alias) <= 3:
                    pattern = r"\b" + re.escape(alias) + r"\b"
                else:
                    pattern = re.escape(alias)
                if re.search(pattern, text, re.IGNORECASE):
                    matched.append(dim_def)
                    seen.add(dim_def.name)
                    break
        
        return matched

    def _detect_grain(self, text: str, dimensions: List[DimensionDefinition]) -> str:
        """Detect the data grain from the query."""
        dim_names = [d.name for d in dimensions]
        
        if "month" in dim_names or "monthly" in text:
            return "monthly"
        if "quarter" in dim_names or "quarterly" in text:
            return "quarterly"
        if "year" in dim_names or "yearly" in text or "annual" in text:
            return "yearly"
        if "product" in dim_names:
            return "product"
        if "region" in dim_names or "category" in dim_names:
            return "dimensional"
        if "customer" in dim_names:
            return "customer"
        
        return "summary"  # Default: summary/aggregate level

    def build_sql(
        self, resolved: ResolvedQuery, table: str = "",
    ) -> str:
        """
        Build a SQL query from the resolved semantic plan.
        
        This is the authoritative SQL generator — it uses the semantic
        layer's metric/dimension definitions to produce correct SQL.
        """
        if not resolved.metrics and not resolved.dimensions:
            return ""
        
        # ── SELECT clause ──
        select_parts = []
        
        # Dimensions first (GROUP BY columns)
        for dim in resolved.dimensions:
            select_parts.append(f'"{dim.column}"')
        
        # Metrics (aggregated)
        for metric in resolved.metrics:
            sql_expr = metric.sql_expression.format(col=metric.column)
            alias = metric.name
            select_parts.append(f"{sql_expr} AS \"{alias}\"")
        
        select_clause = ", ".join(select_parts)
        
        # ── FROM clause ──
        from_clause = f'FROM "{table}"' if table else 'FROM workspace'
        
        # ── GROUP BY clause ──
        group_parts = [f'"{dim.column}"' for dim in resolved.dimensions]
        group_clause = ""
        if group_parts:
            group_clause = "GROUP BY " + ", ".join(group_parts)
        
        # ── ORDER BY clause ──
        order_clause = ""
        if resolved.metrics:
            # Order by the first metric descending
            first_metric = resolved.metrics[0]
            order_clause = f'ORDER BY "{first_metric.name}" DESC'
        
        # ── LIMIT clause ──
        limit_clause = f"LIMIT {resolved.limit}"
        
        # ── Assemble ──
        parts = [f"SELECT {select_clause}", from_clause]
        if group_clause:
            parts.append(group_clause)
        if order_clause:
            parts.append(order_clause)
        if limit_clause:
            parts.append(limit_clause)
        
        return " ".join(parts)


# ──────────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────────

_resolver: Optional[SemanticResolver] = None


def get_semantic_resolver() -> SemanticResolver:
    global _resolver
    if _resolver is None:
        _resolver = SemanticResolver()
    return _resolver
