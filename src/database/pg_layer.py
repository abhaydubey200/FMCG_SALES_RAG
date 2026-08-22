"""
PostgreSQL data layer — replaces SQLite with persistent, production-grade storage.

Uses psycopg2 for synchronous access (FastAPI sync endpoints run on threadpool).
Provides the same interface as sql_layer.py so all existing query functions
work without modification.
"""
import os
import threading
from contextlib import contextmanager
from typing import Optional

import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL", "")

_local = threading.local()


def get_pg_conn():
    """Get or create a thread-local PostgreSQL connection."""
    conn = getattr(_local, "conn", None)
    if conn is None or conn.closed:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL not set")
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        _local.conn = conn
    return conn


@contextmanager
def get_conn():
    """Yields a thread-local PostgreSQL connection (same interface as sql_layer.get_conn)."""
    conn = get_pg_conn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise


def _rows(cursor) -> list:
    """Convert psycopg2 cursor results to list of dicts."""
    return [dict(row) for row in cursor.fetchall()]
