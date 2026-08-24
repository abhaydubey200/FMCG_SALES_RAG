"""
Seed PostgreSQL with synthetic data.
Generates data using the existing data_generator, then loads into PostgreSQL.
Uses psycopg2 directly to avoid SQLite fallback issues.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src import config


def seed():
    """Generate synthetic data and load into PostgreSQL."""
    import psycopg2

    # Step 1: Generate SQLite data if not exists
    if not config.DB_PATH.exists():
        print("Generating synthetic data...")
        from src.ingestion.data_generator import build_database
        build_database()
        print(f"SQLite database created at {config.DB_PATH}")

    # Step 2: Connect directly to PostgreSQL
    db_url = config.DATABASE_URL
    print(f"Loading data into PostgreSQL ({db_url.split('@')[-1] if '@' in db_url else 'configured'})...")

    import sqlite3
    sqlite_conn = sqlite3.connect(str(config.DB_PATH))
    sqlite_conn.row_factory = sqlite3.Row

    pg_conn = psycopg2.connect(db_url)
    pg_conn.autocommit = False
    cur = pg_conn.cursor()

    # Products
    rows = [dict(r) for r in sqlite_conn.execute("SELECT * FROM products").fetchall()]
    if rows:
        for r in rows:
            cur.execute(
                """INSERT INTO products (product_id, product_name, category, subcategory, price, cost, rating, review_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (product_id) DO NOTHING""",
                (r["product_id"], r["product_name"], r["category"], r.get("subcategory"),
                 r["price"], r["cost"], r.get("rating"), r.get("review_count", 0))
            )
        print(f"  Products: {len(rows)} rows")

    # Sales
    rows = [dict(r) for r in sqlite_conn.execute("SELECT * FROM sales").fetchall()]
    if rows:
        cur.execute("SELECT COUNT(*) FROM sales")
        if cur.fetchone()[0] == 0:
            for r in rows:
                cur.execute(
                    """INSERT INTO sales (order_id, product_id, customer_id, order_date, quantity,
                       selling_price, revenue, cost, discount)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (r.get("order_id", ""), r["product_id"], r.get("customer_id", ""),
                     r["order_date"], r["quantity"], r["selling_price"],
                     r["revenue"], r["cost"], r["discount"])
                )
            print(f"  Sales: {len(rows)} rows")
        else:
            print(f"  Sales: already seeded")

    # Customers
    rows = [dict(r) for r in sqlite_conn.execute("SELECT * FROM customers").fetchall()]
    if rows:
        for r in rows:
            cur.execute(
                """INSERT INTO customers (customer_id, segment, region, acquisition_channel,
                   first_purchase_date, lifetime_value)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (customer_id) DO NOTHING""",
                (r["customer_id"], r["segment"], r["region"], r.get("acquisition_channel", ""),
                 r.get("first_purchase_date"), r.get("lifetime_value"))
            )
        print(f"  Customers: {len(rows)} rows")

    # Campaigns
    rows = [dict(r) for r in sqlite_conn.execute("SELECT * FROM campaigns").fetchall()]
    if rows:
        cur.execute("SELECT COUNT(*) FROM campaigns")
        if cur.fetchone()[0] == 0:
            for r in rows:
                cur.execute(
                    """INSERT INTO campaigns (campaign_id, campaign_name, product_id, channel,
                       start_date, end_date, impressions, clicks, spend, conversions, attributed_revenue)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (r["campaign_id"], r["campaign_name"], r["product_id"], r["channel"],
                     r["start_date"], r["end_date"], r["impressions"], r["clicks"],
                     r["spend"], r["conversions"], r["attributed_revenue"])
                )
            print(f"  Campaigns: {len(rows)} rows")
        else:
            print(f"  Campaigns: already seeded")

    # Reviews
    rows = [dict(r) for r in sqlite_conn.execute("SELECT * FROM reviews").fetchall()]
    if rows:
        cur.execute("SELECT COUNT(*) FROM reviews")
        if cur.fetchone()[0] == 0:
            for r in rows:
                cur.execute(
                    """INSERT INTO reviews (review_id, product_id, customer_id, rating,
                       review_text, review_date)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (r.get("review_id", ""), r["product_id"], r.get("customer_id", ""),
                     r["rating"], r.get("review_text", ""), r.get("review_date"))
                )
            print(f"  Reviews: {len(rows)} rows")
        else:
            print(f"  Reviews: already seeded")

    pg_conn.commit()

    # Verify
    cur.execute("SELECT COUNT(*) FROM products")
    print(f"\n=== VERIFICATION ===")
    for t in ["products", "sales", "customers", "campaigns", "reviews"]:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        count = cur.fetchone()[0]
        status = "OK" if count > 0 else "EMPTY"
        print(f"  {t:15s}: {count:>6} rows [{status}]")

    cur.close()
    pg_conn.close()
    sqlite_conn.close()

    print("\nSeeding complete!")


if __name__ == "__main__":
    seed()
