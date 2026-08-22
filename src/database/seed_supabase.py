"""
Seed Supabase tables from existing SQLite data via REST API.
Run after creating tables in SQL Editor.
"""
import os
import sys
import sqlite3
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.supabase_client import upsert_many, select, count, is_configured


def seed():
    if not is_configured():
        print("Supabase not configured. Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in .env")
        return

    db_path = os.getenv("DB_PATH", "data/warehouse.db")
    if not Path(db_path).exists():
        print(f"SQLite not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Products
    rows = [dict(r) for r in conn.execute("SELECT * FROM products").fetchall()]
    if rows and count("products") == 0:
        # Batch insert (Supabase REST API limit is ~1000 rows per request)
        batch_size = 100
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            upsert_many("products", batch)
        print(f"Products: {len(rows)} rows seeded")
    else:
        print(f"Products: {count('products')} already exist, skipping")

    # Sales
    rows = [dict(r) for r in conn.execute("SELECT * FROM sales").fetchall()]
    if rows and count("sales") == 0:
        batch_size = 500
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            # Remove the 'id' field if present (auto-increment in PG)
            for r in batch:
                r.pop("id", None)
            upsert_many("sales", batch)
        print(f"Sales: {len(rows)} rows seeded")
    else:
        print(f"Sales: {count('sales')} already exist, skipping")

    # Customers
    rows = [dict(r) for r in conn.execute("SELECT * FROM customers").fetchall()]
    if rows and count("customers") == 0:
        batch_size = 200
        for i in range(0, len(rows), batch_size):
            upsert_many("customers", rows[i:i+batch_size])
        print(f"Customers: {len(rows)} rows seeded")
    else:
        print(f"Customers: {count('customers')} already exist, skipping")

    # Campaigns
    rows = [dict(r) for r in conn.execute("SELECT * FROM campaigns").fetchall()]
    if rows and count("campaigns") == 0:
        for r in rows:
            r.pop("id", None)
        batch_size = 100
        for i in range(0, len(rows), batch_size):
            upsert_many("campaigns", rows[i:i+batch_size])
        print(f"Campaigns: {len(rows)} rows seeded")
    else:
        print(f"Campaigns: {count('campaigns')} already exist, skipping")

    # Reviews
    rows = [dict(r) for r in conn.execute("SELECT * FROM reviews").fetchall()]
    if rows and count("reviews") == 0:
        for r in rows:
            r.pop("id", None)
        batch_size = 500
        for i in range(0, len(rows), batch_size):
            upsert_many("reviews", rows[i:i+batch_size])
        print(f"Reviews: {len(rows)} rows seeded")
    else:
        print(f"Reviews: {count('reviews')} already exist, skipping")

    conn.close()
    print("\nSeeding complete!")


if __name__ == "__main__":
    seed()
