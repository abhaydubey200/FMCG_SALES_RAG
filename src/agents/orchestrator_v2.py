"""
Orchestrator V2 — Production-hardened agentic pipeline.

Architecture:
    Question
        ↓
    Cache Check (~0ms)
        ↓
    Fast Router (~1ms, deterministic)
        ↓
    Semantic Resolver (~1ms, deterministic)
        ↓
    ┌──────────────┬──────────────┐
    │ Analytics    │ RAG          │
    │ (SQL)        │ (Retrieval)  │
    └──────────────┴──────────────┘  ← PARALLEL
            ↓
        Evidence Contract
            ↓
    ONE LLM SYNTHESIS (or template fallback)
            ↓
        SSE Answer

Key optimizations vs V1:
  - 0 LLM calls for simple analytics (template synthesis)
  - 1 LLM call for complex queries (Groq ~100-500ms)
  - Deterministic routing replaces LLM-based intent classification
  - Semantic Layer resolves metrics/dimensions/aliases
  - SQL + RAG execute in parallel for hybrid queries
  - Evidence Contract standardizes all evidence types
  - Per-stage latency measurement
"""
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.agents.evidence import Evidence, EvidenceGraph, StructuredEvidence, DocumentEvidence
from src.agents.registry import AgentMessage, get_agent_registry
from src.agents.router import FastRouter, RouteResult, get_router
from src.agents.semantic import SemanticResolver, ResolvedQuery, get_semantic_resolver
from src.agents.skills import get_skill_registry
from src.agents.tools import get_tool_registry
from src.llm.query_cache import (
    get_cached_response, cache_full_response,
    get_cached_rag, cache_rag_result,
    get_cached_sql, cache_sql_result,
    get_query_cache,
)

logger = logging.getLogger("agents.orchestrator")

MAX_RETRIES = 1
MAX_PARALLEL_WORKERS = 4
MAX_EXECUTION_TIME_SECONDS = 60

# Workspace context cache (deterministic — same workspace = same context)
_workspace_ctx_cache = None
_workspace_ctx_ts = 0
WORKSPACE_CTX_TTL = 60  # seconds


class Orchestrator:
    """
    V2 Orchestrator — fast, deterministic, single-LLM-synthesis pipeline.
    
    Flow:
        User Query
            → Cache check (~0ms)
            → Fast Router (~1ms, deterministic)
            → Semantic Resolver (~1ms, deterministic)
            → Workspace context (cached)
            → Execution plan (deterministic, no LLM)
            → Parallel SQL + RAG execution
            → Evidence collection
            → Verification (fast path when evidence clear)
            → Template synthesis (0 LLM calls) OR ONE LLM synthesis
            → Return
    """

    def __init__(self):
        self.agent_registry = get_agent_registry()
        self.skill_registry = get_skill_registry()
        self.tool_registry = get_tool_registry()
        self.router = get_router()
        self.semantic = get_semantic_resolver()

    def process(self, user_query: str, conversation_context: List[Dict] = None,
                conversation_id: str = None, workspace_id: str = "default") -> Dict[str, Any]:
        """Main entry point — process a user query through the V2 pipeline."""
        from src.database.state_manager import TransientState, DurableState

        # ── Stage 0: Cache check (~0ms) ──
        cached = get_cached_response(user_query)
        if cached is not None:
            logger.info("Cache HIT for query: %s", user_query[:60])
            cached["metrics"]["cache_hit"] = True
            return cached

        t0 = time.time()
        trace_id = f"trace_{uuid.uuid4().hex[:10]}"
        plan_id = f"plan_{uuid.uuid4().hex[:10]}"
        ts = TransientState(trace_id)
        evidence_graph = EvidenceGraph()
        context = {"evidence_graph": evidence_graph, "trace_id": trace_id,
                    "plan_id": plan_id, "user_query": user_query}
        conversation_context = conversation_context or []
        latency_stages = {}

        ts.set_execution_state("started")
        logger.info("[%s] Processing: %s", trace_id, user_query[:100])

        # ── Stage 1: Fast Router (~1ms, deterministic) ──
        t1 = time.time()
        route_result = self.router.route(user_query, conversation_context)
        latency_stages["router_ms"] = round((time.time() - t1) * 1000, 1)
        logger.info("[%s] Route: %s (confidence: %.2f, %.1fms)", trace_id,
                     route_result.route, route_result.confidence, latency_stages["router_ms"])

        # ── Stage 2: Semantic Resolver (~1ms, deterministic) ──
        t2 = time.time()
        resolved = self.semantic.resolve(user_query, route_result.route)
        latency_stages["semantic_ms"] = round((time.time() - t2) * 1000, 1)

        # ── Stage 3: Workspace context (cached) ──
        t3 = time.time()
        workspace_ctx = self._gather_workspace_context()
        latency_stages["workspace_ms"] = round((time.time() - t3) * 1000, 1)

        # ── Stage 4: Build execution plan (deterministic, no LLM) ──
        t4 = time.time()
        plan = self._build_plan(route_result, resolved, workspace_ctx, user_query)
        latency_stages["planning_ms"] = round((time.time() - t4) * 1000, 1)
        logger.info("[%s] Plan: %d steps, route=%s", trace_id, len(plan.get("steps", [])), route_result.route)

        ts.set("plan", plan)
        DurableState.persist_plan(trace_id, plan, workspace_id, conversation_id)

        # ── Stage 5: Execute plan (parallel SQL + RAG) ──
        t5 = time.time()
        plan_output = self._execute_plan(plan, context, ts)
        latency_stages["execution_ms"] = round((time.time() - t5) * 1000, 1)

        # ── Stage 6: Verification (fast path) ──
        t6 = time.time()
        verification = self._verify(user_query, plan_output, evidence_graph)
        latency_stages["verification_ms"] = round((time.time() - t6) * 1000, 1)

        # ── Stage 7: Synthesis (template or ONE LLM call) ──
        t7 = time.time()
        response = self._synthesize_response(
            user_query, plan_output, verification, evidence_graph, context,
            route_result=route_result, resolved=resolved,
        )
        latency_stages["synthesis_ms"] = round((time.time() - t7) * 1000, 1)

        # ── Persist evidence ──
        ev_list = [ev.to_dict() for ev in evidence_graph.all_evidence()]
        DurableState.persist_evidence(trace_id, ev_list)
        DurableState.persist_verification(trace_id, plan_id, verification)

        # ── Finalize ──
        total_ms = round((time.time() - t0) * 1000, 1)
        response["metrics"]["total_latency_ms"] = total_ms
        response["metrics"]["trace_id"] = trace_id
        response["metrics"]["plan_id"] = plan_id
        response["metrics"]["cache_hit"] = False
        response["metrics"]["route"] = route_result.route
        response["metrics"]["route_confidence"] = route_result.confidence
        response["metrics"]["latency_stages"] = latency_stages
        response["metrics"]["llm_calls"] = 1 if route_result.needs_llm else 0

        ts.set_execution_state("completed")
        logger.info("[%s] Completed in %.0fms (route=%s, verification=%s, stages=%s)",
                     trace_id, total_ms, route_result.route,
                     verification.get("verdict"), json.dumps(latency_stages))

        # ── Cache the result ──
        cache_full_response(user_query, response)

        return response

    def process_stream(self, user_query: str, conversation_context: List[Dict] = None,
                       conversation_id: str = None, workspace_id: str = "default"):
        """Stream the V2 pipeline — yields SSE events with real-time progress."""
        from src.database.state_manager import TransientState, DurableState

        # ── Cache check ──
        cached = get_cached_response(user_query)
        if cached is not None:
            logger.info("Cache HIT for streaming query: %s", user_query[:60])
            yield {"type": "plan_created", "trace_id": f"trace_{uuid.uuid4().hex[:10]}",
                   "plan_id": f"plan_{uuid.uuid4().hex[:10]}"}
            yield {"type": "metadata", "query_type": cached.get("query_type", "cached"),
                   "classification_reason": "cache hit", "agents_used": [],
                   "skills_used": [], "plan_steps": 0, "trace_id": "cache"}
            answer = cached.get("answer", "")
            words = answer.split(" ")
            for i, word in enumerate(words):
                prefix = " " if i > 0 else ""
                yield {"type": "token", "content": prefix + word}
            yield {"type": "done", "answer": answer,
                   "metrics": {**cached.get("metrics", {}), "cache_hit": True},
                   "visualization": cached.get("visualization", {}),
                   "sources": cached.get("sources", []),
                   "evidence": cached.get("evidence", {})}
            return

        t0 = time.time()
        trace_id = f"trace_{uuid.uuid4().hex[:10]}"
        plan_id = f"plan_{uuid.uuid4().hex[:10]}"
        ts = TransientState(trace_id)
        evidence_graph = EvidenceGraph()
        context = {"evidence_graph": evidence_graph, "trace_id": trace_id,
                    "plan_id": plan_id, "user_query": user_query}
        conversation_context = conversation_context or []
        latency_stages = {}

        # ── Stage 1: Fast Router ──
        yield {"type": "plan_created", "trace_id": trace_id, "plan_id": plan_id}
        yield {"type": "progress", "stage": "routing", "message": "Routing your question..."}
        t1 = time.time()
        route_result = self.router.route(user_query, conversation_context)
        latency_stages["router_ms"] = round((time.time() - t1) * 1000, 1)

        # ── Stage 2: Semantic Resolver ──
        yield {"type": "progress", "stage": "semantic", "message": "Resolving terms..."}
        t2 = time.time()
        resolved = self.semantic.resolve(user_query, route_result.route)
        latency_stages["semantic_ms"] = round((time.time() - t2) * 1000, 1)

        # ── Stage 3: Workspace context ──
        yield {"type": "progress", "stage": "context", "message": "Discovering data..."}
        t3 = time.time()
        workspace_ctx = self._gather_workspace_context()
        latency_stages["workspace_ms"] = round((time.time() - t3) * 1000, 1)

        # ── Metadata ──
        yield {"type": "metadata", "query_type": route_result.route.lower(),
               "classification_reason": route_result.reasoning,
               "agents_used": [], "skills_used": [], "plan_steps": 0,
               "trace_id": trace_id, "route": route_result.route,
               "resolved_metrics": [m.name for m in resolved.metrics],
               "resolved_dimensions": [d.name for d in resolved.dimensions]}

        # ── Stage 4: Build plan ──
        yield {"type": "progress", "stage": "planning", "message": "Creating execution plan..."}
        t4 = time.time()
        plan = self._build_plan(route_result, resolved, workspace_ctx, user_query)
        latency_stages["planning_ms"] = round((time.time() - t4) * 1000, 1)
        DurableState.persist_plan(trace_id, plan, workspace_id, conversation_id)

        # ── Stage 5: Execute plan ──
        yield {"type": "progress", "stage": "execution", "message": "Running analytics and retrieval..."}
        for step in plan.get("steps", []):
            yield {"type": "agent_started", "agent_id": step.get("agent", "unknown"),
                   "step_id": step.get("step_id", "")}

        llm_answer = ""
        plan_output = {}
        t5 = time.time()

        for event in self._execute_plan_stream(plan, context, ts):
            if event.get("type") == "llm_token":
                llm_answer += event.get("content", "")
                yield {"type": "token", "content": event.get("content", "")}
            elif event.get("type") == "plan_output":
                plan_output = event.get("data", {})
            elif event.get("type") == "agent_completed":
                yield event

        latency_stages["execution_ms"] = round((time.time() - t5) * 1000, 1)

        # ── Stage 6: Verification ──
        yield {"type": "verification_started"}
        yield {"type": "progress", "stage": "verification", "message": "Verifying results..."}
        t6 = time.time()
        verification = self._verify(user_query, plan_output, evidence_graph)
        latency_stages["verification_ms"] = round((time.time() - t6) * 1000, 1)
        DurableState.persist_verification(trace_id, plan_id, verification)
        yield {"type": "verification_completed", "verdict": verification.get("verdict", "UNKNOWN")}

        # ── Stage 7: Synthesis ──
        if llm_answer and len(llm_answer.strip()) > 10:
            # LLM already produced answer during streaming
            response = {"answer": llm_answer, "query_type": plan_output.get("query_type", "analytical"),
                        "sources": [], "metrics": plan_output, "evidence": {}, "visualization": {}}
        else:
            yield {"type": "progress", "stage": "synthesis", "message": "Generating answer..."}
            t7 = time.time()
            response = self._synthesize_response(
                user_query, plan_output, verification, evidence_graph, context,
                route_result=route_result, resolved=resolved,
            )
            latency_stages["synthesis_ms"] = round((time.time() - t7) * 1000, 1)

        # ── Persist evidence ──
        ev_list = [ev.to_dict() for ev in evidence_graph.all_evidence()]
        DurableState.persist_evidence(trace_id, ev_list)

        # ── Finalize ──
        total_ms = round((time.time() - t0) * 1000, 1)
        response["metrics"]["total_latency_ms"] = total_ms
        response["metrics"]["trace_id"] = trace_id
        response["metrics"]["plan_id"] = plan_id
        response["metrics"]["route"] = route_result.route
        response["metrics"]["latency_stages"] = latency_stages

        ts.set_execution_state("completed")
        cache_full_response(user_query, response)

        yield {"type": "done", "answer": response.get("answer", ""),
               "metrics": response.get("metrics", {}),
               "visualization": response.get("visualization", {}),
               "sources": response.get("sources", []),
               "evidence": response.get("evidence", {})}

    # ──────────────────────────────────────────────────────────────────
    # Plan building (deterministic, no LLM)
    # ──────────────────────────────────────────────────────────────────

    def _build_plan(
        self, route: RouteResult, resolved: ResolvedQuery,
        workspace_ctx: Dict, user_query: str,
    ) -> Dict[str, Any]:
        """Build an execution plan deterministically from route + resolved query."""
        route_type = route.route
        has_data = workspace_ctx.get("has_data", False)

        if not has_data and route_type not in ("KNOWLEDGE",):
            return {
                "goal": "Report no data available",
                "agents_used": ["response"],
                "skills_used": [],
                "steps": [],
                "query_type": route_type.lower(),
            }

        # ── ANALYTICS ──
        if route_type == "ANALYTICS":
            steps = []
            # Step 1: Always discover data first
            steps.append({
                "step_id": "s1", "agent": "analytics", "tool": None,
                "action": "discover and analyze data",
                "input": {"step": "discover"},
                "depends_on": [], "provides_evidence": True,
            })
            # Step 2: If specific metrics/dimensions, compute them
            if resolved.metrics:
                metric = resolved.metrics[0].name
                dims = [d.name for d in resolved.dimensions] if resolved.dimensions else None
                steps.append({
                    "step_id": "s2", "agent": "analytics", "tool": "calculate_metric",
                    "action": f"calculate {metric}",
                    "input": {"step": "calculate", "metric": metric, "dimensions": dims},
                    "depends_on": [], "provides_evidence": True,
                })
            elif resolved.dimensions:
                steps.append({
                    "step_id": "s2", "agent": "analytics", "tool": "sql_generate",
                    "action": f"revenue by {resolved.dimensions[0].name}",
                    "input": {"step": "sql", "metric": "revenue",
                              "dimensions": [d.name for d in resolved.dimensions]},
                    "depends_on": [], "provides_evidence": True,
                })
            return {
                "goal": "Analyze workspace data",
                "agents_used": ["analytics"],
                "skills_used": ["workspace_overview"],
                "steps": steps,
                "query_type": "analytical",
            }

        # ── KNOWLEDGE ──
        if route_type == "KNOWLEDGE":
            return {
                "goal": "Search documents for answer",
                "agents_used": ["rag"],
                "skills_used": ["document_qa"],
                "steps": [
                    {"step_id": "s1", "agent": "rag", "tool": "hybrid_search",
                     "action": "search documents", "input": {"query": user_query, "step": "search"},
                     "depends_on": [], "provides_evidence": True},
                ],
                "query_type": "knowledge",
            }

        # ── HYBRID (parallel SQL + RAG) ──
        if route_type == "HYBRID":
            steps = [
                {"step_id": "s1", "agent": "analytics", "tool": None,
                 "action": "calculate metric", "input": {"step": "discover"},
                 "depends_on": [], "provides_evidence": True},
                {"step_id": "s2", "agent": "rag", "tool": "hybrid_search",
                 "action": "search documents", "input": {"query": user_query, "step": "search"},
                 "depends_on": [], "provides_evidence": True},
            ]
            # Add specific metric calculation if resolved
            if resolved.metrics:
                metric = resolved.metrics[0].name
                steps.append({
                    "step_id": "s3", "agent": "analytics", "tool": "calculate_metric",
                    "action": f"calculate {metric}",
                    "input": {"step": "calculate", "metric": metric},
                    "depends_on": [], "provides_evidence": True,
                })
            return {
                "goal": "Analyze data and search documents",
                "agents_used": ["analytics", "rag"],
                "skills_used": ["hybrid_analysis"],
                "steps": steps,
                "query_type": "hybrid",
            }

        # ── COMPLEX (investigation) ──
        if route_type == "COMPLEX":
            return {
                "goal": "Investigate root cause",
                "agents_used": ["analytics", "rag"],
                "skills_used": ["investigation"],
                "steps": [
                    {"step_id": "s1", "agent": "analytics", "tool": None,
                     "action": "discover available data", "input": {"step": "discover"},
                     "depends_on": [], "provides_evidence": True},
                    {"step_id": "s2", "agent": "rag", "tool": "hybrid_search",
                     "action": "search documents for context",
                     "input": {"query": user_query, "step": "search"},
                     "depends_on": [], "provides_evidence": True},
                ],
                "query_type": "diagnostic",
            }

        # ── AMBIGUOUS / UNSUPPORTED ──
        return {
            "goal": "Handle ambiguous/unsupported query",
            "agents_used": [],
            "skills_used": [],
            "steps": [],
            "query_type": route_type.lower(),
        }

    # ──────────────────────────────────────────────────────────────────
    # Workspace context (cached)
    # ──────────────────────────────────────────────────────────────────

    def _gather_workspace_context(self) -> Dict[str, Any]:
        """Gather workspace state. Cached for TTL."""
        global _workspace_ctx_cache, _workspace_ctx_ts
        now = time.time()
        if _workspace_ctx_cache is not None and (now - _workspace_ctx_ts) < WORKSPACE_CTX_TTL:
            return _workspace_ctx_cache

        tools = self.tool_registry
        try:
            summary = tools.call("get_workspace_summary")
            discoverable = tools.call("get_discoverable_data")
            result = {
                "workspace": summary,
                "measures": discoverable.get("available_measures", {}),
                "dimensions": discoverable.get("available_dimensions", {}),
                "has_data": summary.get("has_data", False),
            }
            _workspace_ctx_cache = result
            _workspace_ctx_ts = now
            return result
        except Exception as e:
            logger.warning("Failed to gather workspace context: %s", e)
            return {"has_data": False, "measures": {}, "dimensions": {}}

    # ──────────────────────────────────────────────────────────────────
    # Plan execution (parallel)
    # ──────────────────────────────────────────────────────────────────

    def _execute_plan(self, plan: Dict[str, Any], context: Dict[str, Any],
                      ts=None) -> Dict[str, Any]:
        """Execute all steps in the plan, collecting evidence. Parallel where possible."""
        evidence_graph: EvidenceGraph = context["evidence_graph"]
        results = {}
        agents_used = set()
        t0 = time.time()

        # Separate steps into independent (no deps) and dependent
        independent_steps = []
        dependent_steps = []

        for step in plan.get("steps", []):
            deps = step.get("depends_on", [])
            if not deps:
                independent_steps.append(step)
            else:
                dependent_steps.append(step)

        # Execute independent steps in parallel (bounded)
        if independent_steps:
            if len(independent_steps) == 1:
                self._execute_single_step(independent_steps[0], results, agents_used,
                                          evidence_graph, context, ts)
            else:
                with ThreadPoolExecutor(max_workers=min(len(independent_steps), MAX_PARALLEL_WORKERS)) as pool:
                    futures = {}
                    for step in independent_steps:
                        future = pool.submit(
                            self._execute_single_step_return, step, evidence_graph, context
                        )
                        futures[future] = step

                    for future in as_completed(futures, timeout=MAX_EXECUTION_TIME_SECONDS):
                        step = futures[future]
                        step_id = step.get("step_id", "unknown")
                        agent_id = step.get("agent", "")
                        try:
                            message, ev_items = future.result()
                            results[step_id] = message.output_data
                            if agent_id:
                                agents_used.add(agent_id)
                            for ev in ev_items:
                                evidence_graph.add(ev)
                        except Exception as e:
                            logger.error("Parallel step %s failed: %s", step_id, e)
                            results[step_id] = {"error": str(e)}

        # Execute dependent steps sequentially
        for step in dependent_steps:
            self._execute_single_step(step, results, agents_used, evidence_graph, context, ts)

        total_ms = round((time.time() - t0) * 1000, 1)
        return {
            "results": results,
            "agents_used": list(agents_used),
            "skills_used": plan.get("skills_used", []),
            "tools_used": list(agents_used),
            "query_type": plan.get("query_type", "analytical"),
            "total_latency_ms": total_ms,
            "evidence_count": len(evidence_graph.all_evidence()),
        }

    def _execute_single_step(self, step: Dict, results: Dict, agents_used: set,
                              evidence_graph: EvidenceGraph, context: Dict, ts=None):
        """Execute a single step, updating results and evidence in place."""
        step_id = step.get("step_id", "unknown")
        agent_id = step.get("agent", "")
        step_input = dict(step.get("input", {}))

        if agent_id == "rag" and not step_input.get("query"):
            step_input["query"] = context.get("user_query", "")

        deps = step.get("depends_on", [])
        if deps and not all(d in results for d in deps):
            logger.warning("Step %s skipped: missing dependencies %s", step_id, deps)
            results[step_id] = {"error": "missing dependencies", "skipped": True}
            return

        if deps:
            dep_data = {d: results.get(d, {}) for d in deps}
            step_input["dependency_data"] = dep_data

        message = AgentMessage(
            source_agent="orchestrator", target_agent=agent_id,
            input_data=step_input, trace_id=context.get("trace_id", ""),
        )

        agent = self.agent_registry.get(agent_id)
        if agent:
            t_step = time.time()
            message = agent.execute(message, context)
            step_ms = round((time.time() - t_step) * 1000, 1)
            results[step_id] = message.output_data
            agents_used.add(agent_id)

            from src.database.state_manager import DurableState
            DurableState.persist_step_execution(
                context.get("plan_id", ""), step, agent_id,
                message.output_data, step_ms,
                status=message.status, error=message.error
            )
            DurableState.persist_agent_execution(
                context.get("trace_id", ""), context.get("plan_id", ""),
                agent_id, message.status,
                input_data=step_input, output_data=message.output_data,
                duration_ms=step_ms, error=message.error
            )

            if ts:
                ts.set_step_status(step_id, message.status, message.output_data, message.error)

            if step.get("provides_evidence"):
                self._collect_evidence(message, step, evidence_graph)
        else:
            logger.warning("Agent '%s' not found, skipping step %s", agent_id, step_id)
            results[step_id] = {"error": f"Agent '{agent_id}' not found"}

    def _execute_single_step_return(self, step: Dict, evidence_graph: EvidenceGraph, context: Dict):
        """Execute a single step and return (message, evidence_items) for thread-safe parallel use."""
        step_id = step.get("step_id", "unknown")
        agent_id = step.get("agent", "")
        step_input = dict(step.get("input", {}))

        if agent_id == "rag" and not step_input.get("query"):
            step_input["query"] = context.get("user_query", "")

        message = AgentMessage(
            source_agent="orchestrator", target_agent=agent_id,
            input_data=step_input, trace_id=context.get("trace_id", ""),
        )

        agent = self.agent_registry.get(agent_id)
        ev_items = []

        if agent:
            message = agent.execute(message, context)
            if step.get("provides_evidence"):
                ev_items = self._extract_evidence_items(message, step)
        else:
            message.status = "failed"
            message.error = f"Agent '{agent_id}' not found"

        return message, ev_items

    def _execute_plan_stream(self, plan: Dict[str, Any], context: Dict[str, Any], ts=None):
        """Execute plan with streaming — yields LLM tokens for the response step."""
        evidence_graph: EvidenceGraph = context["evidence_graph"]
        results = {}
        agents_used = set()
        t0 = time.time()

        # Execute independent steps in parallel for streaming too
        independent_steps = []
        dependent_steps = []
        for step in plan.get("steps", []):
            if not step.get("depends_on", []):
                independent_steps.append(step)
            else:
                dependent_steps.append(step)

        # Parallel execution of independent steps
        if len(independent_steps) > 1:
            with ThreadPoolExecutor(max_workers=min(len(independent_steps), MAX_PARALLEL_WORKERS)) as pool:
                futures = {}
                for step in independent_steps:
                    future = pool.submit(
                        self._execute_single_step_return, step, evidence_graph, context
                    )
                    futures[future] = step
                for future in as_completed(futures, timeout=MAX_EXECUTION_TIME_SECONDS):
                    step = futures[future]
                    step_id = step.get("step_id", "unknown")
                    agent_id = step.get("agent", "")
                    try:
                        message, ev_items = future.result()
                        results[step_id] = message.output_data
                        if agent_id:
                            agents_used.add(agent_id)
                        for ev in ev_items:
                            evidence_graph.add(ev)
                        yield {"type": "agent_completed", "agent_id": agent_id,
                               "step_id": step_id, "duration_ms": 0}
                    except Exception as e:
                        logger.error("Parallel step %s failed: %s", step_id, e)
                        results[step_id] = {"error": str(e)}
        elif independent_steps:
            # Single step — sequential
            for step in independent_steps:
                step_id = step.get("step_id", "unknown")
                agent_id = step.get("agent", "")
                step_input = step.get("input", {})
                if agent_id == "rag" and not step_input.get("query"):
                    step_input["query"] = context.get("user_query", "")
                message = AgentMessage(
                    source_agent="orchestrator", target_agent=agent_id,
                    input_data=step_input, trace_id=context.get("trace_id", ""),
                )
                agent = self.agent_registry.get(agent_id)
                if agent:
                    t_step = time.time()
                    message = agent.execute(message, context)
                    step_ms = round((time.time() - t_step) * 1000, 1)
                    results[step_id] = message.output_data
                    agents_used.add(agent_id)
                    from src.database.state_manager import DurableState
                    DurableState.persist_agent_execution(
                        context.get("trace_id", ""), context.get("plan_id", ""),
                        agent_id, message.status,
                        input_data=step_input, output_data=message.output_data,
                        duration_ms=step_ms
                    )
                    if step.get("provides_evidence"):
                        self._collect_evidence(message, step, evidence_graph)
                    yield {"type": "agent_completed", "agent_id": agent_id,
                           "step_id": step_id, "duration_ms": step_ms}

        # Dependent steps sequentially
        for step in dependent_steps:
            step_id = step.get("step_id", "unknown")
            agent_id = step.get("agent", "")
            step_input = step.get("input", {})
            deps = step.get("depends_on", [])
            if deps:
                dep_data = {d: results.get(d, {}) for d in deps}
                step_input["dependency_data"] = dep_data
            message = AgentMessage(
                source_agent="orchestrator", target_agent=agent_id,
                input_data=step_input, trace_id=context.get("trace_id", ""),
            )
            agent = self.agent_registry.get(agent_id)
            if agent:
                t_step = time.time()
                message = agent.execute(message, context)
                step_ms = round((time.time() - t_step) * 1000, 1)
                results[step_id] = message.output_data
                agents_used.add(agent_id)
                if step.get("provides_evidence"):
                    self._collect_evidence(message, step, evidence_graph)
                yield {"type": "agent_completed", "agent_id": agent_id,
                       "step_id": step_id, "duration_ms": step_ms}

        total_ms = round((time.time() - t0) * 1000, 1)

        # ── ONE LLM synthesis call (streaming) ──
        # First try template synthesis (~0ms)
        template_answer = self._template_synthesize(
            context.get("user_query", ""), evidence_graph
        )
        if template_answer:
            yield {"type": "llm_token", "content": template_answer}
        else:
            # ONE LLM call for synthesis (Groq ~100-500ms)
            evidence_summary = self._build_evidence_summary(evidence_graph)
            user_q = context.get("user_query", "")
            prompt = f"""Answer this question using ONLY the provided evidence. Be specific and cite sources.

Question: {user_q}

Evidence:
{evidence_summary}

Provide a clear, concise answer. If the evidence is insufficient, say so honestly."""

            try:
                from src.llm.factory import get_llm
                llm = get_llm()
                system = "You are a data analyst. Answer using ONLY the provided evidence. Be specific, cite sources, and acknowledge limitations."
                for token in llm.generate_stream(prompt, system=system):
                    yield {"type": "llm_token", "content": token}
            except Exception as e:
                logger.warning("LLM streaming failed: %s", e)
                try:
                    from src.llm.factory import get_llm
                    llm = get_llm()
                    response = llm.generate(prompt, system="You are a data analyst.")
                    yield {"type": "llm_token", "content": response.text}
                except Exception:
                    yield {"type": "llm_token", "content": "I was unable to generate a response."}

        yield {"type": "plan_output", "data": {
            "results": results, "agents_used": list(agents_used),
            "skills_used": plan.get("skills_used", []),
            "tools_used": list(agents_used),
            "query_type": plan.get("query_type", "analytical"),
            "total_latency_ms": total_ms,
            "evidence_count": len(evidence_graph.all_evidence()),
        }}

    # ──────────────────────────────────────────────────────────────────
    # Evidence extraction
    # ──────────────────────────────────────────────────────────────────

    def _extract_evidence_items(self, message: AgentMessage, step: Dict) -> List[Evidence]:
        """Extract evidence from agent output (thread-safe, returns list)."""
        output = message.output_data
        if not output:
            return []

        step_id = step.get("step_id", "")
        agent_id = step.get("agent", "")
        items = []

        if "rows" in output and output.get("rows"):
            items.append(StructuredEvidence(
                source=output.get("table", "workspace"),
                sql_query=output.get("sql", ""),
                result=output["rows"][:50],
                columns=output.get("columns", []),
                rows_affected=output.get("row_count", 0),
                metadata={"agent": agent_id, "step": step_id},
            ))

        if "chunks" in output:
            for chunk in output["chunks"]:
                items.append(DocumentEvidence(
                    source=chunk.get("document_name", chunk.get("source", "")),
                    document_id=chunk.get("document_id", ""),
                    text=chunk.get("text", "")[:500],
                    relevance_score=chunk.get("relevance_score", 0),
                    metadata={"agent": agent_id, "step": step_id},
                ))

        if "data" in output and output.get("data"):
            items.append(StructuredEvidence(
                source=output.get("table", "workspace"),
                query=f"{output.get('metric', '?')} from {output.get('table', '?')}",
                result=output["data"][:50],
                metadata={"agent": agent_id, "step": step_id, "resolved_to": output.get("resolved_to")},
            ))

        if "comparisons" in output:
            items.append(StructuredEvidence(
                source="period_comparison",
                query=f"period comparison for {output.get('metric', '?')}",
                result=output["comparisons"],
                metadata={"agent": agent_id, "step": step_id},
            ))

        if "available_dimensions" in output:
            items.append(StructuredEvidence(
                source="workspace_discovery",
                query="available dimensions",
                result=[output],
                metadata={"agent": agent_id, "step": step_id},
            ))

        if "dynamic_kpis" in output and output["dynamic_kpis"]:
            items.append(StructuredEvidence(
                source="dynamic_kpis", query="workspace KPIs",
                result=output["dynamic_kpis"],
                metadata={"agent": agent_id, "step": step_id},
            ))

        if "breakdowns" in output and output["breakdowns"]:
            for dim_name, dim_data in output["breakdowns"].items():
                if dim_data:
                    items.append(StructuredEvidence(
                        source=f"breakdown_{dim_name}",
                        query=f"revenue by {dim_name}",
                        result=dim_data[:50],
                        metadata={"agent": agent_id, "step": step_id, "dimension": dim_name},
                    ))

        return items

    def _collect_evidence(self, message: AgentMessage, step: Dict, evidence_graph: EvidenceGraph):
        """Extract evidence from agent output and add to evidence graph."""
        for ev in self._extract_evidence_items(message, step):
            evidence_graph.add(ev)

    def _build_evidence_summary(self, evidence_graph: EvidenceGraph) -> str:
        """Build a text summary of all evidence for LLM context."""
        parts = []
        for ev in evidence_graph.all_evidence():
            if ev.evidence_type == "structured" and ev.result:
                if isinstance(ev.result, list) and ev.result:
                    parts.append(f"[Structured Data] Query: {ev.query or 'N/A'}\nResults ({len(ev.result)} rows): {json.dumps(ev.result[:5], default=str)}")
            elif ev.evidence_type == "unstructured" and ev.text:
                parts.append(f"[Document: {ev.source}] {ev.text[:300]}")
        return "\n\n".join(parts) if parts else "No evidence collected."

    # ──────────────────────────────────────────────────────────────────
    # Template-based synthesis (~0ms, no LLM)
    # ──────────────────────────────────────────────────────────────────

    def _template_synthesize(self, query: str, evidence_graph: EvidenceGraph) -> Optional[str]:
        """Template-based synthesis — ~0ms, no LLM call.

        Returns a formatted answer when evidence is clear and deterministic.
        Returns None when evidence is ambiguous and LLM synthesis is needed.
        """
        from src import config as _cfg

        if not getattr(_cfg, "ENABLE_TEMPLATE_SYNTHESIS", True):
            return None

        structured = evidence_graph.structured_evidence()
        document_ev = evidence_graph.document_evidence()

        if not structured and not document_ev:
            return None

        # ── Pure data queries (analytical) ──
        if structured and not document_ev:
            parts = []
            for ev in structured:
                if ev.result and isinstance(ev.result, list) and ev.result:
                    query_label = ev.query or "query"
                    rows = ev.result[:20]
                    parts.append(f"**{query_label}:**")
                    if len(rows) == 1 and isinstance(rows[0], dict):
                        for k, v in rows[0].items():
                            if isinstance(v, float):
                                prefix = "$" if any(w in k.lower() for w in ["revenue", "spend", "profit", "margin"]) else ""
                                parts.append(f"  {k}: {prefix}{v:,.2f}")
                            else:
                                parts.append(f"  {k}: {v}")
                    else:
                        for row in rows[:10]:
                            if isinstance(row, dict):
                                label = row.get("region") or row.get("category") or row.get("product_name") or row.get("month") or ""
                                vals = [f"{k}: {v:,.2f}" if isinstance(v, float) else f"{k}: {v}" for k, v in row.items() if k != label and v is not None]
                                parts.append(f"  {label}: {', '.join(vals[:3])}" if label else f"  {', '.join(vals[:3])}")
                    if len(rows) > 10:
                        parts.append(f"  ... and {len(rows) - 10} more rows")
            if parts:
                parts.append("\n*Sources: workspace data*")
                return "\n".join(parts)

        # ── Pure knowledge queries ──
        if document_ev and not structured:
            parts = ["**From the knowledge base:**"]
            for ev in document_ev[:3]:
                text = ev.text or ""
                snippet = text if len(text) < 300 else text[:297] + "..."
                parts.append(f"- {snippet}")
            parts.append(f"\n**Source:** {document_ev[0].source}" if document_ev else "")
            return "\n".join(parts)

        return None

    # ──────────────────────────────────────────────────────────────────
    # Verification (fast path)
    # ──────────────────────────────────────────────────────────────────

    def _verify(self, query: str, plan_output: Dict, evidence_graph: EvidenceGraph) -> Dict[str, Any]:
        """Verify results. Fast path for clear evidence."""
        evidence_count = len(evidence_graph.all_evidence())
        plan_errors = sum(1 for v in plan_output.get("results", {}).values()
                          if isinstance(v, dict) and "error" in v)

        if evidence_count >= 1 and plan_errors == 0:
            return {"verdict": "PASS", "reason": "Clear evidence, no errors"}

        # Full verification for error cases
        message = AgentMessage(
            source_agent="orchestrator", target_agent="verification",
            input_data={"plan_output": plan_output, "user_query": query},
        )
        agent = self.agent_registry.get("verification")
        if agent:
            message = agent.execute(message, {"evidence_graph": evidence_graph})
            return message.output_data
        return {"verdict": "PASS", "reason": "No verification agent"}
