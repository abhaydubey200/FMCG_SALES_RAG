"""
Query Cache — in-memory LRU cache for deterministic query results.

Caches:
  - SQL query results (same query = same result)
  - RAG search results (same query = same chunks)
  - Full orchestrator responses (same question = same answer)

Uses a simple dict-based LRU with TTL expiration.
No Redis dependency — pure in-memory for zero-latency cache hits.
"""
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

from src import config

logger = logging.getLogger("query_cache")


class TTLCache:
    """Thread-safe in-memory LRU cache with TTL expiration."""

    def __init__(self, max_size: int = 512, default_ttl: int = 300):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def _make_key(self, namespace: str, *args, **kwargs) -> str:
        """Create a deterministic cache key from namespace + arguments."""
        raw = json.dumps({"ns": namespace, "args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, namespace: str, *args, **kwargs) -> Optional[Any]:
        """Get a cached value. Returns None on miss."""
        key = self._make_key(namespace, *args, **kwargs)
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    # Move to end (most recently used)
                    self._cache.move_to_end(key)
                    self._hits += 1
                    return value
                else:
                    # Expired — remove
                    del self._cache[key]
            self._misses += 1
            return None

    def set(self, namespace: str, value: Any, ttl: int = None, *args, **kwargs):
        """Store a value in the cache."""
        ttl = ttl or self._default_ttl
        key = self._make_key(namespace, *args, **kwargs)
        with self._lock:
            # Remove existing entry if present
            if key in self._cache:
                del self._cache[key]
            # Evict oldest if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            self._cache[key] = (value, time.time() + ttl)

    def invalidate(self, namespace: str):
        """Invalidate all entries in a namespace."""
        with self._lock:
            keys_to_remove = [
                k for k, (v, _) in self._cache.items()
                # We can't reverse the hash, so just clear everything
            ]
            # Since we can't namespace-check hashes, just clear the whole cache
            # for simplicity. In production you'd store namespace metadata.
            self._cache.clear()
            logger.info("Cache cleared (namespace: %s)", namespace)

    def clear(self):
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / max(1, total) * 100, 1),
            }


# Global singleton
_query_cache: Optional[TTLCache] = None


def get_query_cache() -> TTLCache:
    global _query_cache
    if _query_cache is None:
        _query_cache = TTLCache(
            max_size=512,
            default_ttl=getattr(config, "QUERY_CACHE_TTL", 300),
        )
    return _query_cache


# ──────────────────────────────────────────────────────────────────────
# Convenience functions
# ──────────────────────────────────────────────────────────────────────

def cache_sql_result(sql: str, result: Any, ttl: int = 300) -> Any:
    """Cache a SQL query result."""
    if not getattr(config, "ENABLE_QUERY_CACHE", True):
        return result
    cache = get_query_cache()
    cache.set("sql", result, ttl, sql)
    return result


def get_cached_sql(sql: str) -> Optional[Any]:
    """Get a cached SQL result."""
    if not getattr(config, "ENABLE_QUERY_CACHE", True):
        return None
    cache = get_query_cache()
    return cache.get("sql", sql)


def cache_rag_result(query: str, result: Any, ttl: int = 600) -> Any:
    """Cache a RAG search result (longer TTL since docs change rarely)."""
    if not getattr(config, "ENABLE_QUERY_CACHE", True):
        return result
    cache = get_query_cache()
    cache.set("rag", result, ttl, query)
    return result


def get_cached_rag(query: str) -> Optional[Any]:
    """Get a cached RAG result."""
    if not getattr(config, "ENABLE_QUERY_CACHE", True):
        return None
    cache = get_query_cache()
    return cache.get("rag", query)


def cache_full_response(question: str, response: Any, ttl: int = 300) -> Any:
    """Cache a full orchestrator response."""
    if not getattr(config, "ENABLE_QUERY_CACHE", True):
        return response
    cache = get_query_cache()
    # Normalize question for caching
    normalized = question.strip().lower()
    cache.set("response", response, ttl, normalized)
    return response


def get_cached_response(question: str) -> Optional[Any]:
    """Get a cached orchestrator response."""
    if not getattr(config, "ENABLE_QUERY_CACHE", True):
        return None
    cache = get_query_cache()
    normalized = question.strip().lower()
    return cache.get("response", normalized)
