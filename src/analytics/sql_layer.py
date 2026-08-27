"""
Structured-data access layer.

Minimal passthrough — only get_conn() is used by the application.
All legacy query functions have been removed.
The dynamic engine (src/analytics/dynamic_engine) handles all workspace data access.
"""
from src.database.pg_layer import get_conn
