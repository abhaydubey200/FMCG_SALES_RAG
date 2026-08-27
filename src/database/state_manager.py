"""
State Manager — Redis-backed transient state + PostgreSQL durable persistence.

Redis handles:
  - Execution state (plan, step status, streaming)
  - Task state (pending/running/completed)
  - Session/trace state
  - Cache (analytics, RAG, workspace)

PostgreSQL handles:
  - Execution plans (durable)
  - Execution steps (durable)
  - Agent executions (durable)
  - Evidence records (durable)
  - Verification results (durable)
  - Conversation history (durable)

Redis failure degrades gracefully — never loses durable data.
"""
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from src import config

logger = logging.getLogger("state_manager")


# ═══════════════════════════════════════════════════════════════════════
# Redis Client (transient state)
# ═══════════════════════════════════════════════════════════════════════

_redis_client = None
_redis_available = False


def _get_redis():
    """Get Redis client — returns None if unavailable."""
    global _redis_client, _redis_available
    if _redis_client is not None and _redis_available:
        return _redis_client
    try:
        import redis as redis_lib
        _redis_client = redis_lib.from_url(config.REDIS_URL, decode_responses=True, socket_timeout=5)
        _redis_client.ping()
        _redis_available = True
        return _redis_client
    except Exception as e:
        logger.warning("Redis unavailable: %s — using in-memory fallback", e)
        _redis_available = False
        return None


def _get_pg_conn():
    """Get a fresh PostgreSQL connection."""
    import psycopg2
    return psycopg2.connect(config.DATABASE_URL)


def _safe_identifier(name: str) -> str:
    """Validate SQL identifier."""
    import re
    if not name or not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValueError(f"Unsafe identifier: {name}")
    return name


# ═══════════════════════════════════════════════════════════════════════
# Redis Transient State
# ═══════════════════════════════════════════════════════════════════════

class TransientState:
    """Redis-backed transient execution state."""

    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        self.r = _get_redis()
        self._prefix = f"trace:{trace_id}:"

    def set(self, key: str, value: Any, ttl: int = 3600):
        full_key = self._prefix + key
        serialized = json.dumps(value, default=str)
        if self.r:
            try:
                self.r.set(full_key, serialized, ex=ttl)
            except Exception as e:
                logger.warning("Redis set failed: %s", e)
        # Always keep in-memory fallback
        if not hasattr(self, '_mem'):
            self._mem = {}
        self._mem[key] = serialized

    def get(self, key: str) -> Optional[Any]:
        full_key = self._prefix + key
        if self.r:
            try:
                val = self.r.get(full_key)
                if val is not None:
                    return json.loads(val)
            except Exception:
                pass
        # Fallback to in-memory
        mem = getattr(self, '_mem', {})
        if key in mem:
            return json.loads(mem[key])
        return None

    def update(self, key: str, updates: Dict[str, Any], ttl: int = 3600):
        current = self.get(key) or {}
        current.update(updates)
        self.set(key, current, ttl)

    def delete(self, key: str):
        full_key = self._prefix + key
        if self.r:
            try:
                self.r.delete(full_key)
            except Exception:
                pass
        mem = getattr(self, '_mem', {})
        mem.pop(key, None)

    def set_execution_state(self, state: str, detail: str = ""):
        self.set("execution_state", {"state": state, "detail": detail, "updated_at": time.time()})

    def set_step_status(self, step_id: str, status: str, output: Any = None, error: str = None):
        self.update("steps", {step_id: {"status": status, "output": output, "error": error, "ts": time.time()}})

    def get_plan_id(self) -> str:
        pid = self.get("plan_id")
        if not pid:
            pid = f"plan_{uuid.uuid4().hex[:10]}"
            self.set("plan_id", pid)
        return pid


# ═══════════════════════════════════════════════════════════════════════
# Durable Persistence (PostgreSQL)
# ═══════════════════════════════════════════════════════════════════════

class DurableState:
    """PostgreSQL-backed durable execution persistence."""

    @staticmethod
    def persist_plan(trace_id: str, plan: Dict[str, Any], workspace_id: str = "default",
                     conversation_id: str = None) -> str:
        """Persist an execution plan. Returns plan_id."""
        plan_id = f"plan_{uuid.uuid4().hex[:10]}"
        try:
            conn = _get_pg_conn()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO execution_plans (plan_id, trace_id, workspace_id, conversation_id,
                                                  goal, query_type, agents_used, skills_used,
                                                  steps, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    plan_id, trace_id, workspace_id, conversation_id,
                    plan.get("goal", ""), plan.get("query_type", "analytical"),
                    json.dumps(plan.get("agents_used", [])),
                    json.dumps(plan.get("skills_used", [])),
                    json.dumps(plan.get("steps", []), default=str),
                    "created",
                ))
                conn.commit()
            finally:
                conn.close()
            return plan_id
        except Exception as e:
            logger.warning("Failed to persist plan: %s", e)
            return plan_id

    @staticmethod
    def persist_step_execution(plan_id: str, step: Dict[str, Any], agent_id: str,
                                output: Dict[str, Any], duration_ms: float,
                                status: str = "completed", error: str = None):
        """Persist a single step execution."""
        step_id = step.get("step_id", f"step_{uuid.uuid4().hex[:8]}")
        try:
            conn = _get_pg_conn()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO execution_steps (step_id, plan_id, agent_id, tool_id,
                                                  action, input_data, output_data,
                                                  status, duration_ms, error, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    step_id, plan_id, agent_id,
                    step.get("tool"),
                    step.get("action", ""),
                    json.dumps(step.get("input", {}), default=str),
                    json.dumps(output, default=str) if output else None,
                    status, duration_ms, error,
                ))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to persist step: %s", e)

    @staticmethod
    def persist_evidence(trace_id: str, evidence_list: List[Dict[str, Any]]):
        """Persist evidence records."""
        try:
            conn = _get_pg_conn()
            try:
                cur = conn.cursor()
                for ev in evidence_list:
                    cur.execute("""
                        INSERT INTO evidence_records (evidence_id, trace_id, evidence_type,
                                                      source, metric, query_text, result_data,
                                                      confidence, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (evidence_id) DO NOTHING
                    """, (
                        ev.get("evidence_id"), trace_id, ev.get("evidence_type", "unknown"),
                        ev.get("source", ""), ev.get("metric"),
                        ev.get("query"),
                        json.dumps(ev.get("result"), default=str) if ev.get("result") else None,
                        ev.get("confidence", 1.0),
                        json.dumps(ev.get("metadata", {}), default=str),
                    ))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to persist evidence: %s", e)

    @staticmethod
    def persist_verification(trace_id: str, plan_id: str, verification: Dict[str, Any]):
        """Persist verification result."""
        try:
            conn = _get_pg_conn()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO verification_results (trace_id, plan_id, verdict, reason,
                                                      issues, warnings, evidence_count, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    trace_id, plan_id,
                    verification.get("verdict", "UNKNOWN"),
                    verification.get("reason", ""),
                    json.dumps(verification.get("issues", [])),
                    json.dumps(verification.get("warnings", [])),
                    verification.get("evidence_count", 0),
                ))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to persist verification: %s", e)

    @staticmethod
    def persist_agent_execution(trace_id: str, plan_id: str, agent_id: str,
                                 status: str, input_data: Dict = None,
                                 output_data: Dict = None, duration_ms: float = 0,
                                 error: str = None):
        """Persist an agent execution record."""
        try:
            conn = _get_pg_conn()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO agent_executions (trace_id, plan_id, agent_id, status,
                                                   input_data, output_data, duration_ms,
                                                   error, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    trace_id, plan_id, agent_id, status,
                    json.dumps(input_data, default=str) if input_data else None,
                    json.dumps(output_data, default=str) if output_data else None,
                    duration_ms, error,
                ))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to persist agent execution: %s", e)

    @staticmethod
    def get_execution_history(trace_id: str) -> Dict[str, Any]:
        """Retrieve full execution history for a trace."""
        try:
            conn = _get_pg_conn()
            try:
                cur = conn.cursor()
                # Plan
                cur.execute("SELECT * FROM execution_plans WHERE trace_id = %s", (trace_id,))
                plan_cols = [d[0] for d in cur.description] if cur.description else []
                plan_row = cur.fetchone()
                plan = dict(zip(plan_cols, plan_row)) if plan_row else None

                # Steps
                cur.execute("SELECT * FROM execution_steps WHERE plan_id = %s ORDER BY created_at",
                           (plan["plan_id"] if plan else "",))
                step_cols = [d[0] for d in cur.description] if cur.description else []
                steps = [dict(zip(step_cols, r)) for r in cur.fetchall()]

                # Agent executions
                cur.execute("SELECT * FROM agent_executions WHERE trace_id = %s ORDER BY created_at",
                           (trace_id,))
                ae_cols = [d[0] for d in cur.description] if cur.description else []
                agents = [dict(zip(ae_cols, r)) for r in cur.fetchall()]

                # Evidence
                cur.execute("SELECT * FROM evidence_records WHERE trace_id = %s", (trace_id,))
                ev_cols = [d[0] for d in cur.description] if cur.description else []
                evidence = [dict(zip(ev_cols, r)) for r in cur.fetchall()]

                # Verification
                cur.execute("SELECT * FROM verification_results WHERE trace_id = %s ORDER BY created_at DESC LIMIT 1",
                           (trace_id,))
                vr_cols = [d[0] for d in cur.description] if cur.description else []
                vr_row = cur.fetchone()
                verification = dict(zip(vr_cols, vr_row)) if vr_row else None

                return {
                    "plan": plan,
                    "steps": steps,
                    "agent_executions": agents,
                    "evidence": evidence,
                    "verification": verification,
                }
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Failed to get execution history: %s", e)
            return {}


# ═══════════════════════════════════════════════════════════════════════
# Cache Invalidation
# ═══════════════════════════════════════════════════════════════════════

class CacheManager:
    """Redis-backed cache with invalidation support."""

    def __init__(self):
        self.r = _get_redis()

    def invalidate_workspace(self, workspace_id: str = "default"):
        """Invalidate all caches for a workspace."""
        if not self.r:
            return
        try:
            pattern = f"cache:{workspace_id}:*"
            keys = self.r.keys(pattern)
            if keys:
                self.r.delete(*keys)
                logger.info("Invalidated %d cache keys for workspace %s", len(keys), workspace_id)
        except Exception as e:
            logger.warning("Cache invalidation failed: %s", e)

    def invalidate_analytics(self, workspace_id: str = "default"):
        """Invalidate analytics cache for a workspace."""
        if not self.r:
            return
        try:
            pattern = f"cache:{workspace_id}:analytics:*"
            keys = self.r.keys(pattern)
            if keys:
                self.r.delete(*keys)
        except Exception:
            pass

    def invalidate_rag(self):
        """Invalidate RAG cache (affects all workspaces)."""
        if not self.r:
            return
        try:
            pattern = "cache:rag:*"
            keys = self.r.keys(pattern)
            if keys:
                self.r.delete(*keys)
        except Exception:
            pass

    def get(self, key: str) -> Optional[Any]:
        if not self.r:
            return None
        try:
            val = self.r.get(key)
            return json.loads(val) if val else None
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: int = 300):
        if not self.r:
            return
        try:
            self.r.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception:
            pass


# Module-level singletons
_cache_manager = None


def get_cache_manager() -> CacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager
