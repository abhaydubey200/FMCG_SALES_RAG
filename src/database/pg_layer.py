"""
PostgreSQL data layer — provides get_conn() for database access.

All legacy query functions (that queried hardcoded seed tables like
products, sales, customers, campaigns, reviews) have been removed.
The application now uses the dynamic engine (src/analytics/dynamic_engine)
for all data access based on uploaded workspace data.

IMPORTANT: PostgreSQL is REQUIRED. SQLite fallback has been removed to
prevent silent data-splitting between PostgreSQL and SQLite code paths.
"""
import logging
import threading
from contextlib import contextmanager
from typing import Optional

from src import config

logger = logging.getLogger("pg_layer")

try:
    import psycopg2
    import psycopg2.extras
    HAS_PG = True
except ImportError:
    HAS_PG = False
    logger.critical("psycopg2 not installed — PostgreSQL is required")

_local = threading.local()
_pg_failed_at = 0


def _get_pg_conn():
    """Get or create a thread-local PostgreSQL connection."""
    global _pg_failed_at
    import time
    if _pg_failed_at and (time.time() - _pg_failed_at) < 60:
        raise RuntimeError("PostgreSQL connection previously failed, retrying in 60s")
    conn = getattr(_local, "pg_conn", None)
    if conn is None or conn.closed:
        if not config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL not set — PostgreSQL is required")
        try:
            conn = psycopg2.connect(config.DATABASE_URL)
            conn.autocommit = False
            _local.pg_conn = conn
        except Exception as e:
            _pg_failed_at = time.time()
            raise RuntimeError(f"PostgreSQL connection failed: {e}")
    return conn


@contextmanager
def get_conn():
    """Yields a thread-local PostgreSQL connection.

    Raises RuntimeError if PostgreSQL is unavailable.
    Do NOT fall back to SQLite — different code paths using different
    backends causes silent data-splitting.
    """
    if not HAS_PG or not config.USE_POSTGRESQL:
        raise RuntimeError(
            "PostgreSQL is required but not configured. "
            "Set DATABASE_URL to a PostgreSQL connection string."
        )
    raw_conn = _get_pg_conn()
    try:
        yield raw_conn
    except Exception:
        try:
            raw_conn.rollback()
        except Exception:
            pass
        raise
