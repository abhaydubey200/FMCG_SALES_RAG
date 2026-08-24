"""
PostgreSQL data layer — replaces SQLite with persistent, production-grade storage.

Uses psycopg2 for synchronous access (FastAPI sync endpoints run on threadpool).
Provides the same interface as sql_layer.py so all existing query functions
work without modification. When DATABASE_URL is set, uses PostgreSQL;
otherwise falls back to SQLite for local development.
"""
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional

from src import config

logger = logging.getLogger("pg_layer")


class _CompatConnection:
    """Wrapper that makes psycopg2 connections behave like sqlite3 connections.
    Provides .execute(query, params) -> cursor and .row_factory."""
    def __init__(self, conn, is_pg):
        self._conn = conn
        self._is_pg = is_pg
        self.row_factory = None

    def execute(self, query, params=None):
        cur = self._conn.cursor()
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        return cur

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    @property
    def closed(self):
        return self._conn.closed

# Try PostgreSQL first, fall back to SQLite
try:
    if config.USE_POSTGRESQL:
        import psycopg2
        import psycopg2.extras
        HAS_PG = True
    else:
        HAS_PG = False
except ImportError:
    HAS_PG = False

_local = threading.local()


_pg_failed_at = 0  # Timestamp of last failure; allows retry after 60s

def _get_pg_conn():
    """Get or create a thread-local PostgreSQL connection."""
    global _pg_failed_at
    import time
    if _pg_failed_at and (time.time() - _pg_failed_at) < 60:
        raise RuntimeError("PostgreSQL connection previously failed, retrying in 60s")
    conn = getattr(_local, "pg_conn", None)
    if conn is None or conn.closed:
        if not config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL not set")
        try:
            conn = psycopg2.connect(config.DATABASE_URL)
            conn.autocommit = False
            _local.pg_conn = conn
            _local.is_pg = True
        except Exception as e:
            _pg_failed_at = time.time()
            raise RuntimeError(f"PostgreSQL connection failed: {e}")
    return conn


def _is_pg_conn() -> bool:
    """Check if current connection is PostgreSQL."""
    return getattr(_local, "is_pg", False)


def _month_expr(col="order_date"):
    """Return SQL for extracting YYYY-MM month string."""
    if _is_pg_conn():
        return f"TO_CHAR({col}, 'YYYY-MM')"
    return f"strftime('%Y-%m', {col})"


def _quarter_expr(col="order_date"):
    """Return SQL for extracting quarter string like 2024-Q1."""
    if _is_pg_conn():
        return f"EXTRACT(YEAR FROM {col}) || '-Q' || ((EXTRACT(MONTH FROM {col})::int - 1) / 3 + 1)"
    return f"strftime('%Y', {col}) || '-Q' || ((CAST(strftime('%m', {col}) AS INTEGER) - 1) / 3 + 1)"


def _get_sqlite_conn():
    """Get or create a thread-local SQLite connection."""
    conn = getattr(_local, "sqlite_conn", None)
    if conn is None:
        conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        _local.sqlite_conn = conn
    return conn


@contextmanager
def get_conn():
    """Yields a thread-local database connection (wrapped for compatibility)."""
    raw_conn = None
    is_pg = False
    if HAS_PG and config.USE_POSTGRESQL:
        try:
            raw_conn = _get_pg_conn()
            is_pg = True
        except Exception:
            logger.warning("PostgreSQL unreachable, falling back to SQLite")
            _local.is_pg = False
            raw_conn = None
    if raw_conn is None:
        _local.is_pg = False
        raw_conn = _get_sqlite_conn()
        conn = _CompatConnection(raw_conn, is_pg=False)
    else:
        _local.is_pg = True
        conn = _CompatConnection(raw_conn, is_pg=True)
    try:
        yield conn
    except Exception:
        try:
            raw_conn.rollback()
        except Exception:
            pass
        raise


def _rows(cursor) -> list:
    """Convert cursor results to list of dicts."""
    if cursor is None:
        return []
    rows = cursor.fetchall()
    if not rows:
        return []
    try:
        return [dict(zip(row.keys(), row)) for row in rows]
    except AttributeError:
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in rows]


def _execute(conn, query, params=None):
    """Execute query with proper placeholder syntax."""
    if _is_pg_conn():
        # PostgreSQL uses %s placeholders
        return conn.execute(query, params) if params else conn.execute(query)
    else:
        # SQLite uses ? placeholders — convert %s to ?
        if params and "%s" in query:
            query = query.replace("%s", "?")
        return conn.execute(query, params) if params else conn.execute(query)


def _to_dict(row, cursor):
    """Convert a row to dict, handling both sqlite3.Row and psycopg2 tuples."""
    if row is None:
        return None
    try:
        # sqlite3.Row has .keys()
        return dict(zip(row.keys(), row))
    except AttributeError:
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))


def _fetchone(conn, query, params=None):
    """Execute and fetch one row as dict."""
    cur = _execute(conn, query, params)
    if cur is None:
        return None
    row = cur.fetchone()
    return _to_dict(row, cur) if row else None


def _fetchall(conn, query, params=None):
    """Execute and fetch all rows as list of dicts."""
    cur = _execute(conn, query, params)
    if cur is None:
        return []
    rows = cur.fetchall()
    if not rows:
        return []
    try:
        return [dict(zip(row.keys(), row)) for row in rows]
    except AttributeError:
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in rows]


# ═══════════════════════════════════════════════════════════════════════════
# LOOKUPS
# ═══════════════════════════════════════════════════════════════════════════

def find_product_by_name(name: str) -> Optional[dict]:
    with get_conn() as conn:
        return _fetchone(conn,
            "SELECT * FROM products WHERE product_name LIKE %s ORDER BY LENGTH(product_name) ASC LIMIT 1",
            (f"%{name}%",))


def get_product(product_id: str) -> Optional[dict]:
    with get_conn() as conn:
        return _fetchone(conn, "SELECT * FROM products WHERE product_id = %s", (product_id,))


def list_categories() -> list:
    with get_conn() as conn:
        rows = _fetchall(conn, "SELECT DISTINCT category FROM products ORDER BY category")
        return [r.get("category", list(r.values())[0]) if isinstance(r, dict) else r[0] for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# SALES & PROFITABILITY
# ═══════════════════════════════════════════════════════════════════════════

def top_products_by_revenue(limit: int = 5, category: str = None,
                             start_date: str = None, end_date: str = None) -> list:
    q = """
        SELECT p.product_id, p.product_name, p.category,
               SUM(s.revenue) AS revenue,
               SUM(s.quantity) AS units_sold,
               ROUND(AVG(s.selling_price), 2) AS avg_selling_price
        FROM sales s JOIN products p ON s.product_id = p.product_id
        WHERE 1=1
    """
    params = []
    if category:
        q += " AND p.category = %s"
        params.append(category)
    if start_date:
        q += " AND s.order_date >= %s"
        params.append(start_date)
    if end_date:
        q += " AND s.order_date <= %s"
        params.append(end_date)
    q += " GROUP BY p.product_id, p.product_name, p.category ORDER BY revenue DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn:
        return _rows(_execute(conn, q, params))


def category_performance(category: str = None, start_date: str = None, end_date: str = None) -> list:
    q = """
        SELECT p.category,
               SUM(s.revenue) AS revenue,
               SUM(s.quantity) AS units_sold,
               SUM(s.revenue - s.cost) AS gross_profit,
               ROUND((100.0 * SUM(s.revenue - s.cost) / NULLIF(SUM(s.revenue), 0)), 2) AS gross_margin_pct,
               ROUND(AVG(s.discount), 2) AS avg_discount_pct
        FROM sales s JOIN products p ON s.product_id = p.product_id
        WHERE 1=1
    """
    params = []
    if category:
        q += " AND p.category = %s"
        params.append(category)
    if start_date:
        q += " AND s.order_date >= %s"
        params.append(start_date)
    if end_date:
        q += " AND s.order_date <= %s"
        params.append(end_date)
    q += " GROUP BY p.category ORDER BY revenue DESC"
    with get_conn() as conn:
        return _rows(_execute(conn, q, params))


def revenue_growth(product_id: str, period_a: tuple, period_b: tuple) -> dict:
    with get_conn() as conn:
        def rev(start, end):
            row = _fetchone(conn,
                "SELECT COALESCE(SUM(revenue),0) FROM sales WHERE product_id=%s AND order_date>=%s AND order_date<=%s",
                (product_id, start, end))
            if not row:
                return 0
            # The dict key is the column expression or 'coalesce'
            val = list(row.values())[0]
            return val if val else 0

        rev_a = rev(*period_a)
        rev_b = rev(*period_b)
        growth_pct = None
        if rev_a:
            growth_pct = round(100.0 * float(rev_b - rev_a) / float(rev_a), 2)
        return {
            "product_id": product_id,
            "period_a": period_a, "revenue_a": round(float(rev_a), 2),
            "period_b": period_b, "revenue_b": round(float(rev_b), 2),
            "growth_pct": growth_pct,
        }


def product_metrics(product_id: str, start_date: str = None, end_date: str = None) -> dict:
    q = """
        SELECT
            COUNT(*) AS order_count,
            COALESCE(SUM(quantity), 0) AS units_sold,
            COALESCE(SUM(revenue), 0) AS revenue,
            COALESCE(SUM(cost), 0) AS total_cost,
            COALESCE(AVG(selling_price), 0) AS avg_selling_price,
            COALESCE(AVG(discount), 0) AS avg_discount_pct
        FROM sales WHERE product_id = %s
    """
    params = [product_id]
    if start_date:
        q += " AND order_date >= %s"
        params.append(start_date)
    if end_date:
        q += " AND order_date <= %s"
        params.append(end_date)
    with get_conn() as conn:
        row = _fetchone(conn, q, params)
    revenue = float(row["revenue"] or 0)
    total_cost = float(row["total_cost"] or 0)
    gross_profit = revenue - total_cost
    row["gross_profit"] = round(gross_profit, 2)
    row["gross_margin_pct"] = round(100.0 * gross_profit / revenue, 2) if revenue else None
    row["avg_order_value"] = round(revenue / int(row["order_count"]), 2) if row["order_count"] else None
    for k in ("revenue", "total_cost", "avg_selling_price", "avg_discount_pct"):
        row[k] = round(float(row[k] or 0), 2)
    return row


def quarterly_trend(product_id: str) -> list:
    q = f"""
        SELECT
            {_quarter_expr('order_date')} AS quarter,
            SUM(revenue) AS revenue,
            SUM(quantity) AS units_sold,
            ROUND(AVG(discount), 2) AS avg_discount_pct
        FROM sales WHERE product_id = %s
        GROUP BY quarter ORDER BY quarter
    """
    with get_conn() as conn:
        return _rows(_execute(conn, q, (product_id,)))


# ═══════════════════════════════════════════════════════════════════════════
# MARKETING METRICS
# ═══════════════════════════════════════════════════════════════════════════

def campaign_performance(limit: int = 10, order_by: str = "roas") -> list:
    q = """
        SELECT campaign_id, campaign_name, product_id, channel, start_date, end_date,
               impressions, clicks, spend, conversions, attributed_revenue,
               ROUND((1.0 * clicks / NULLIF(impressions, 0)), 4) AS ctr,
               ROUND((1.0 * conversions / NULLIF(clicks, 0)), 4) AS conversion_rate,
               ROUND((spend / NULLIF(clicks, 0)), 2) AS cpc,
               ROUND((spend / NULLIF(conversions, 0)), 2) AS cpa,
               ROUND((attributed_revenue / NULLIF(spend, 0)), 2) AS roas
        FROM campaigns
    """
    order_map = {"roas": "roas", "spend": "spend", "revenue": "attributed_revenue", "ctr": "ctr"}
    q += f" ORDER BY {order_map.get(order_by, 'roas')} DESC LIMIT %s"
    with get_conn() as conn:
        return _rows(_execute(conn, q, (limit,)))


def campaigns_for_product(product_id: str) -> list:
    with get_conn() as conn:
        return _rows(_execute(conn,
            """SELECT campaign_id, campaign_name, channel, start_date, end_date, spend,
                      conversions, attributed_revenue,
                      ROUND((attributed_revenue / NULLIF(spend, 0)), 2) AS roas
               FROM campaigns WHERE product_id = %s ORDER BY start_date""",
            (product_id,)))


def marketing_spend_to_revenue(category: str = None) -> dict:
    with get_conn() as conn:
        if category:
            row = _fetchone(conn, """
                SELECT COALESCE(SUM(c.spend),0) AS spend, COALESCE(SUM(c.attributed_revenue),0) AS attributed_revenue
                FROM campaigns c JOIN products p ON c.product_id = p.product_id
                WHERE p.category = %s
            """, (category,))
        else:
            row = _fetchone(conn,
                "SELECT COALESCE(SUM(spend),0) AS spend, COALESCE(SUM(attributed_revenue),0) AS attributed_revenue FROM campaigns")
    row["spend_to_revenue_ratio"] = round(row["spend"] / row["attributed_revenue"], 4) if row["attributed_revenue"] else None
    return row


# ═══════════════════════════════════════════════════════════════════════════
# CUSTOMER METRICS
# ═══════════════════════════════════════════════════════════════════════════

def segment_revenue() -> list:
    q = """
        SELECT c.segment,
               COUNT(DISTINCT c.customer_id) AS customers,
               COALESCE(SUM(s.revenue), 0) AS revenue,
               ROUND(AVG(c.lifetime_value), 2) AS avg_ltv
        FROM customers c LEFT JOIN sales s ON c.customer_id = s.customer_id
        GROUP BY c.segment ORDER BY revenue DESC
    """
    with get_conn() as conn:
        return _rows(_execute(conn, q))


def repeat_purchase_rate(segment: str = None) -> dict:
    if segment:
        q = """
            SELECT s.customer_id, COUNT(*) AS orders FROM sales s
            JOIN customers c ON s.customer_id = c.customer_id
            WHERE c.segment = %s
            GROUP BY s.customer_id
        """
        params = (segment,)
    else:
        q = "SELECT customer_id, COUNT(*) AS orders FROM sales s GROUP BY s.customer_id"
        params = None
    with get_conn() as conn:
        rows = _rows(_execute(conn, q, params))
    total = len(rows)
    repeat = len([r for r in rows if r["orders"] > 1])
    return {
        "segment": segment or "All",
        "total_customers_with_orders": total,
        "repeat_customers": repeat,
        "repeat_purchase_rate_pct": round(100.0 * repeat / total, 2) if total else None,
    }


def customer_acquisition_cost(channel: str = None) -> dict:
    with get_conn() as conn:
        if channel:
            new_customers = _fetchone(conn,
                "SELECT COUNT(*) FROM customers WHERE acquisition_channel = %s", (channel,))[0]
        else:
            new_customers = _fetchone(conn, "SELECT COUNT(*) FROM customers")[0]
        total_spend = _fetchone(conn, "SELECT COALESCE(SUM(spend),0) FROM campaigns")[0]
    cac = round(total_spend / new_customers, 2) if new_customers else None
    return {"channel": channel or "All (approx., blended)", "new_customers": new_customers,
            "total_marketing_spend": round(total_spend, 2), "approx_cac": cac}


def top_customers_by_ltv(limit: int = 10) -> list:
    with get_conn() as conn:
        return _rows(_execute(conn,
            "SELECT customer_id, segment, region, lifetime_value FROM customers ORDER BY lifetime_value DESC LIMIT %s",
            (limit,)))


def total_sales_summary() -> dict:
    with get_conn() as conn:
        row = _fetchone(conn, """
            SELECT COALESCE(SUM(revenue), 0) AS total_revenue,
                   COALESCE(SUM(quantity), 0) AS total_units,
                   COUNT(*) AS total_orders,
                   COALESCE(SUM(revenue - cost), 0) AS gross_profit,
                   ROUND(AVG(selling_price), 2) AS avg_selling_price,
                   ROUND(AVG(discount), 2) AS avg_discount
            FROM sales
        """)
        row["gross_margin_pct"] = round(100.0 * float(row["gross_profit"]) / float(row["total_revenue"]), 2) if row["total_revenue"] else 0
        row["avg_order_value"] = round(float(row["total_revenue"]) / int(row["total_orders"]), 2) if row["total_orders"] else 0
        return row


def revenue_by_region() -> list:
    with get_conn() as conn:
        return _rows(_execute(conn, """
            SELECT c.region,
                   COUNT(DISTINCT c.customer_id) AS customers,
                   COALESCE(SUM(s.revenue), 0) AS revenue,
                   COALESCE(SUM(s.quantity), 0) AS units_sold,
                   ROUND(AVG(s.selling_price), 2) AS avg_selling_price
            FROM sales s JOIN customers c ON s.customer_id = c.customer_id
            GROUP BY c.region ORDER BY revenue DESC
        """))


def monthly_revenue_trend() -> list:
    with get_conn() as conn:
        return _rows(_execute(conn, f"""
            SELECT {_month_expr('order_date')} AS month,
                   SUM(revenue) AS revenue,
                   SUM(quantity) AS units_sold,
                   SUM(revenue - cost) AS profit
            FROM sales
            GROUP BY month ORDER BY month
        """))


def customer_segment_summary() -> list:
    with get_conn() as conn:
        return _rows(_execute(conn, """
            SELECT c.segment,
                   COUNT(DISTINCT c.customer_id) AS customers,
                   ROUND(AVG(c.lifetime_value), 2) AS avg_ltv,
                   COALESCE(SUM(s.revenue), 0) AS revenue,
                   COALESCE(SUM(s.quantity), 0) AS units_sold
            FROM customers c LEFT JOIN sales s ON c.customer_id = s.customer_id
            GROUP BY c.segment ORDER BY revenue DESC
        """))


def campaign_summary() -> list:
    with get_conn() as conn:
        return _rows(_execute(conn, """
            SELECT campaign_name, channel, SUM(spend) AS spend,
                   SUM(attributed_revenue) AS revenue,
                   SUM(conversions) AS conversions,
                   ROUND((SUM(attributed_revenue) * 1.0 / NULLIF(SUM(spend), 0)), 2) AS roas
            FROM campaigns
            GROUP BY campaign_id, campaign_name, channel
            ORDER BY roas DESC
        """))


def discount_margin_analysis() -> list:
    with get_conn() as conn:
        return _rows(_execute(conn, """
            SELECT
                CASE
                    WHEN discount = 0 THEN '0%% (No discount)'
                    WHEN discount BETWEEN 0.01 AND 5 THEN '1-5%%'
                    WHEN discount BETWEEN 5.01 AND 10 THEN '5-10%%'
                    WHEN discount BETWEEN 10.01 AND 15 THEN '10-15%%'
                    WHEN discount > 15 THEN '15%%+'
                    ELSE 'Other'
                END AS discount_band,
                COUNT(*) AS orders,
                SUM(revenue) AS total_revenue,
                ROUND(AVG(revenue - cost), 2) AS avg_profit,
                ROUND((100.0 * AVG(revenue - cost) / NULLIF(AVG(revenue), 0)), 2) AS avg_margin_pct
            FROM sales
            GROUP BY discount_band ORDER BY MIN(discount)
        """))


# ═══════════════════════════════════════════════════════════════════════════
# REVIEWS
# ═══════════════════════════════════════════════════════════════════════════

def review_summary(product_id: str, start_date: str = None, end_date: str = None) -> dict:
    q = "SELECT rating, review_text, review_date FROM reviews WHERE product_id = %s"
    params = [product_id]
    if start_date:
        q += " AND review_date >= %s"
        params.append(start_date)
    if end_date:
        q += " AND review_date <= %s"
        params.append(end_date)
    with get_conn() as conn:
        rows = _rows(_execute(conn, q, params))
    if not rows:
        return {"product_id": product_id, "review_count": 0}
    avg_rating = round(sum(r["rating"] for r in rows) / len(rows), 2)
    negative = [r for r in rows if r["rating"] <= 2]
    return {
        "product_id": product_id,
        "review_count": len(rows),
        "avg_rating": avg_rating,
        "negative_review_count": len(negative),
        "negative_review_pct": round(100.0 * len(negative) / len(rows), 2),
        "sample_negative_reviews": [r["review_text"] for r in negative[:5]],
    }
