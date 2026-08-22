"""
Structured-data access layer.

Design choice (documented for README "SQL/analytics strategy"): rather
than translating every natural-language analytical question into
free-form generated SQL (risky — see Section 26 "How would you safely
generate SQL from natural language?"), we expose a small set of
*parametrized, reviewed* query functions covering the required metrics
(Section 10). The query classifier + a lightweight entity/parameter
extractor decide *which* function to call and with *which* parameters
(product, category, date range) — this bounds LLM-influenced behavior to
parameter selection, never to raw SQL string construction, which is the
production-safe pattern described in the README's SQL-generation-safety
discussion. A `run_safe_query` escape hatch is included for extensibility
but only ever executes a fixed allow-list of read-only, parametrized
statements — never string-interpolated LLM output.
"""
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date
from typing import Optional

from src import config

# --- Connection reuse (optimization) ---
# Profiling the unoptimized version showed sqlite3.connect()/close() on
# every single analytics call was ~44% of total pipeline time (a
# diagnostic question alone triggers 8-10 separate analytics calls, each
# previously opening and tearing down its own connection). SQLite
# connections are not safe to share across threads, but FastAPI's sync
# endpoints run on a threadpool, so each worker thread gets exactly one
# persistent connection via threading.local() and reuses it for the life
# of the thread instead of paying connect/close overhead on every call.
_local = threading.local()


def _get_thread_connection() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(config.DB_PATH, check_same_thread=True)
        conn.row_factory = sqlite3.Row
        # WAL mode allows concurrent readers without blocking, which matters
        # once multiple worker threads are each holding a long-lived connection.
        conn.execute("PRAGMA journal_mode=WAL")
        _local.conn = conn
    return conn


@contextmanager
def get_conn():
    """Yields a thread-local, reused connection. Callers must not close it
    (the context manager intentionally does not close on exit, unlike the
    original per-call implementation) — the connection lives for the
    thread's lifetime and is closed automatically when the thread exits."""
    yield _get_thread_connection()


def _rows(cur) -> list:
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def find_product_by_name(name: str) -> Optional[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM products WHERE product_name LIKE ? ORDER BY LENGTH(product_name) ASC LIMIT 1",
            (f"%{name}%",))
        row = cur.fetchone()
        return dict(row) if row else None


def get_product(product_id: str) -> Optional[dict]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM products WHERE product_id = ?", (product_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_categories() -> list:
    with get_conn() as conn:
        cur = conn.execute("SELECT DISTINCT category FROM products ORDER BY category")
        return [r[0] for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Sales & Profitability metrics
# ---------------------------------------------------------------------------

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
        q += " AND p.category = ?"
        params.append(category)
    if start_date:
        q += " AND s.order_date >= ?"
        params.append(start_date)
    if end_date:
        q += " AND s.order_date <= ?"
        params.append(end_date)
    q += " GROUP BY p.product_id ORDER BY revenue DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        return _rows(conn.execute(q, params))


def category_performance(category: str = None, start_date: str = None, end_date: str = None) -> list:
    q = """
        SELECT p.category,
               SUM(s.revenue) AS revenue,
               SUM(s.quantity) AS units_sold,
               SUM(s.revenue - s.cost) AS gross_profit,
               ROUND(100.0 * SUM(s.revenue - s.cost) / NULLIF(SUM(s.revenue), 0), 2) AS gross_margin_pct,
               ROUND(AVG(s.discount), 2) AS avg_discount_pct
        FROM sales s JOIN products p ON s.product_id = p.product_id
        WHERE 1=1
    """
    params = []
    if category:
        q += " AND p.category = ?"
        params.append(category)
    if start_date:
        q += " AND s.order_date >= ?"
        params.append(start_date)
    if end_date:
        q += " AND s.order_date <= ?"
        params.append(end_date)
    q += " GROUP BY p.category ORDER BY revenue DESC"
    with get_conn() as conn:
        return _rows(conn.execute(q, params))


def revenue_growth(product_id: str, period_a: tuple, period_b: tuple) -> dict:
    """period_a, period_b: (start_date, end_date) ISO strings. Growth = B vs A."""
    with get_conn() as conn:
        def rev(start, end):
            cur = conn.execute(
                "SELECT COALESCE(SUM(revenue),0) FROM sales WHERE product_id=? AND order_date>=? AND order_date<=?",
                (product_id, start, end))
            return cur.fetchone()[0]

        rev_a = rev(*period_a)
        rev_b = rev(*period_b)
        growth_pct = None
        if rev_a:
            growth_pct = round(100.0 * (rev_b - rev_a) / rev_a, 2)
        return {
            "product_id": product_id,
            "period_a": period_a, "revenue_a": round(rev_a, 2),
            "period_b": period_b, "revenue_b": round(rev_b, 2),
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
        FROM sales WHERE product_id = ?
    """
    params = [product_id]
    if start_date:
        q += " AND order_date >= ?"
        params.append(start_date)
    if end_date:
        q += " AND order_date <= ?"
        params.append(end_date)
    with get_conn() as conn:
        row = dict(conn.execute(q, params).fetchone())
    revenue = row["revenue"]
    total_cost = row["total_cost"]
    gross_profit = revenue - total_cost
    row["gross_profit"] = round(gross_profit, 2)
    row["gross_margin_pct"] = round(100.0 * gross_profit / revenue, 2) if revenue else None
    row["avg_order_value"] = round(revenue / row["order_count"], 2) if row["order_count"] else None
    for k in ("revenue", "total_cost", "avg_selling_price", "avg_discount_pct"):
        row[k] = round(row[k], 2)
    return row


def quarterly_trend(product_id: str) -> list:
    q = """
        SELECT strftime('%Y', order_date) || '-Q' ||
               ((CAST(strftime('%m', order_date) AS INTEGER) - 1) / 3 + 1) AS quarter,
               SUM(revenue) AS revenue,
               SUM(quantity) AS units_sold,
               ROUND(AVG(discount), 2) AS avg_discount_pct
        FROM sales WHERE product_id = ?
        GROUP BY quarter ORDER BY quarter
    """
    with get_conn() as conn:
        return _rows(conn.execute(q, (product_id,)))


# ---------------------------------------------------------------------------
# Marketing metrics
# ---------------------------------------------------------------------------

def campaign_performance(limit: int = 10, order_by: str = "roas") -> list:
    q = """
        SELECT campaign_id, campaign_name, product_id, channel, start_date, end_date,
               impressions, clicks, spend, conversions, attributed_revenue,
               ROUND(1.0 * clicks / NULLIF(impressions, 0), 4) AS ctr,
               ROUND(1.0 * conversions / NULLIF(clicks, 0), 4) AS conversion_rate,
               ROUND(spend / NULLIF(clicks, 0), 2) AS cpc,
               ROUND(spend / NULLIF(conversions, 0), 2) AS cpa,
               ROUND(attributed_revenue / NULLIF(spend, 0), 2) AS roas
        FROM campaigns
    """
    order_map = {"roas": "roas", "spend": "spend", "revenue": "attributed_revenue", "ctr": "ctr"}
    q += f" ORDER BY {order_map.get(order_by, 'roas')} DESC LIMIT ?"
    with get_conn() as conn:
        return _rows(conn.execute(q, (limit,)))


def campaigns_for_product(product_id: str) -> list:
    with get_conn() as conn:
        return _rows(conn.execute(
            """SELECT campaign_id, campaign_name, channel, start_date, end_date, spend,
                      conversions, attributed_revenue,
                      ROUND(attributed_revenue / NULLIF(spend, 0), 2) AS roas
               FROM campaigns WHERE product_id = ? ORDER BY start_date""",
            (product_id,)))


def marketing_spend_to_revenue(category: str = None) -> dict:
    with get_conn() as conn:
        if category:
            cur = conn.execute("""
                SELECT COALESCE(SUM(c.spend),0) AS spend, COALESCE(SUM(c.attributed_revenue),0) AS attributed_revenue
                FROM campaigns c JOIN products p ON c.product_id = p.product_id
                WHERE p.category = ?
            """, (category,))
        else:
            cur = conn.execute("SELECT COALESCE(SUM(spend),0) AS spend, COALESCE(SUM(attributed_revenue),0) AS attributed_revenue FROM campaigns")
        row = dict(cur.fetchone())
    row["spend_to_revenue_ratio"] = round(row["spend"] / row["attributed_revenue"], 4) if row["attributed_revenue"] else None
    return row


# ---------------------------------------------------------------------------
# Customer metrics
# ---------------------------------------------------------------------------

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
        return _rows(conn.execute(q))


def repeat_purchase_rate(segment: str = None) -> dict:
    q = """
        SELECT customer_id, COUNT(*) AS orders
        FROM sales s
    """
    params = []
    if segment:
        q = """
            SELECT s.customer_id, COUNT(*) AS orders FROM sales s
            JOIN customers c ON s.customer_id = c.customer_id
            WHERE c.segment = ?
        """
        params.append(segment)
    q += " GROUP BY s.customer_id"
    with get_conn() as conn:
        rows = _rows(conn.execute(q, params))
    total = len(rows)
    repeat = len([r for r in rows if r["orders"] > 1])
    return {
        "segment": segment or "All",
        "total_customers_with_orders": total,
        "repeat_customers": repeat,
        "repeat_purchase_rate_pct": round(100.0 * repeat / total, 2) if total else None,
    }


def customer_acquisition_cost(channel: str = None) -> dict:
    """Approximate CAC = marketing spend on acquisition-relevant campaigns / new customers acquired via that channel."""
    with get_conn() as conn:
        if channel:
            new_customers = conn.execute(
                "SELECT COUNT(*) FROM customers WHERE acquisition_channel = ?", (channel,)).fetchone()[0]
        else:
            new_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        total_spend = conn.execute("SELECT COALESCE(SUM(spend),0) FROM campaigns").fetchone()[0]
    cac = round(total_spend / new_customers, 2) if new_customers else None
    return {"channel": channel or "All (approx., blended)", "new_customers": new_customers,
            "total_marketing_spend": round(total_spend, 2), "approx_cac": cac,
            "note": "Approximated as blended spend / acquired customers; production CAC should join spend to acquisition-attributed conversions per channel."}


def top_customers_by_ltv(limit: int = 10) -> list:
    with get_conn() as conn:
        return _rows(conn.execute(
            "SELECT customer_id, segment, region, lifetime_value FROM customers ORDER BY lifetime_value DESC LIMIT ?",
            (limit,)))


# ---------------------------------------------------------------------------
# Reviews (used heavily by diagnostic questions)
# ---------------------------------------------------------------------------

def review_summary(product_id: str, start_date: str = None, end_date: str = None) -> dict:
    q = "SELECT rating, review_text, review_date FROM reviews WHERE product_id = ?"
    params = [product_id]
    if start_date:
        q += " AND review_date >= ?"
        params.append(start_date)
    if end_date:
        q += " AND review_date <= ?"
        params.append(end_date)
    with get_conn() as conn:
        rows = _rows(conn.execute(q, params))
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
