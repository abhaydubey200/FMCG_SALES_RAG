"""
Supabase client — uses the REST API (works from any network).

The direct PostgreSQL endpoint (db.*.supabase.co) is IPv6-only and
unreachable from many local environments. The REST API
(https://*.supabase.co) works everywhere via HTTPS.

This module provides:
- CRUD operations via PostgREST
- File storage via Supabase Storage
- Vector search via RPC functions
"""
import os
import json
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")

_client = None


def get_client():
    """Get or create the Supabase client (REST API)."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("Supabase not configured. Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in .env")
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def is_configured() -> bool:
    """Check if Supabase is properly configured."""
    return bool(SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL.startswith("http"))


# ═══════════════════════════════════════════════════════════════════════════
# CRUD Operations (via PostgREST)
# ═══════════════════════════════════════════════════════════════════════════

def upsert(table: str, data: dict) -> Optional[dict]:
    """Insert or update a row."""
    try:
        client = get_client()
        result = client.table(table).upsert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        return None


def upsert_many(table: str, rows: List[dict]) -> bool:
    """Bulk insert/update rows."""
    try:
        client = get_client()
        client.table(table).upsert(rows).execute()
        return True
    except Exception as e:
        return False


def select(table: str, filters: dict = None, order: str = None,
           limit: int = None, offset: int = None) -> List[dict]:
    """Query rows."""
    try:
        client = get_client()
        q = client.table(table).select("*")
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        if order:
            desc = order.startswith("-")
            col = order.lstrip("-")
            q = q.order(col, desc=desc)
        if limit:
            q = q.limit(limit)
        if offset:
            q = q.offset(offset)
        result = q.execute()
        return result.data or []
    except Exception as e:
        return []


def delete(table: str, filters: dict) -> bool:
    """Delete rows matching filters."""
    try:
        client = get_client()
        q = client.table(table).delete()
        for k, v in filters.items():
            q = q.eq(k, v)
        q.execute()
        return True
    except Exception as e:
        return False


def count(table: str, filters: dict = None) -> int:
    """Count rows."""
    try:
        client = get_client()
        q = client.table(table).select("*", count="exact")
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        result = q.execute()
        return result.count or 0
    except Exception as e:
        return 0


# ═══════════════════════════════════════════════════════════════════════════
# Storage Operations
# ═══════════════════════════════════════════════════════════════════════════

def upload_file(bucket: str, path: str, file_bytes: bytes,
                content_type: str = "application/octet-stream") -> Optional[str]:
    """Upload a file to Supabase Storage. Returns the public URL."""
    try:
        client = get_client()
        result = client.storage.from_(bucket).upload(
            path, file_bytes,
            file_options={"content-type": content_type, "upsert": "true"}
        )
        if result:
            url = client.storage.from_(bucket).get_public_url(path)
            return url
    except Exception as e:
        pass
    return None


def download_file(bucket: str, path: str) -> Optional[bytes]:
    """Download a file from Supabase Storage."""
    try:
        client = get_client()
        return client.storage.from_(bucket).download(path)
    except Exception as e:
        return None


def list_files(bucket: str, folder: str = "") -> List[dict]:
    """List files in a storage bucket."""
    try:
        client = get_client()
        return client.storage.from_(bucket).list(folder) or []
    except Exception as e:
        return []


def delete_file(bucket: str, paths: List[str]) -> bool:
    """Delete files from storage."""
    try:
        client = get_client()
        client.storage.from_(bucket).remove(paths)
        return True
    except Exception as e:
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Health Check
# ═══════════════════════════════════════════════════════════════════════════

def health_check() -> dict:
    """Check Supabase connectivity."""
    if not is_configured():
        return {"status": "not_configured", "message": "SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY not set"}
    try:
        client = get_client()
        # Try a simple query
        client.table("documents").select("document_id").limit(1).execute()
        return {"status": "healthy", "url": SUPABASE_URL}
    except Exception as e:
        err_msg = str(e)
        if "does not exist" in err_msg or "relation" in err_msg:
            return {"status": "connected", "message": "Supabase reachable, tables not yet created",
                    "url": SUPABASE_URL}
        return {"status": "error", "error": err_msg[:200], "url": SUPABASE_URL}
