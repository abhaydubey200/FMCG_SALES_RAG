"""
PostgreSQL data layer — provides get_conn() for database access.

All legacy query functions (that queried hardcoded seed tables like
products, sales, customers, campaigns, reviews) have been removed.
The application now uses the dynamic engine (src/analytics/dynamic_engine)
for all data access based on uploaded workspace data.
"""
import logging
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional

from src import config

logger = logging.getLogger("pg_layer")


class _CompatConnection:
    """Wrapper that makes psycopg2 connections behave like sqlite3 connections."""
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
