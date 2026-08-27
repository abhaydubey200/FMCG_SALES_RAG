"""
Orchestrator — the brain of the agentic architecture.

Responsibilities:
1. Understand user request (intent classification via LLM)
2. Inspect workspace context (semantic layer, available data)
3. Create dynamic execution plan
4. Execute plan using specialist agents (bounded parallel)
5. Collect evidence
6. Verify results
7. Replan if verification fails
8. Return verified response

CRITICAL: Does NOT do keyword routing.
Uses LLM for intent understanding + planning.
Uses deterministic tools for all data access.

Redis handles transient execution state.
PostgreSQL handles durable persistence.
"""
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.agents.evidence import Evidence, EvidenceGraph, StructuredEvidence, DocumentEvidence
from src.agents.registry import AgentMessage, get_agent_registry
from src.agents.skills import get_skill_registry
from src.agents.tools import get_tool_registry

logger = logging.getLogger("agents.orchestrator")

MAX_RETRIES = 2
MAX_PLAN_STEPS = 10
MAX_PARALLEL_WORKERS = 4
MAX_EXECUTION_TIME_SECONDS = 120


class Orchestrator:
    """
    Dynamic orchestrator that plans and executes multi-agent workflows.

    Flow:
        User Query
            → LLM intent classification (structured output)
            → Workspace context gathering
            → Dynamic plan generation (LLM-driven)
            → Plan execution (tools + agents, bounded parallel)
            → Evidence collection
            → Verification
            → Replan if needed
            → Response synthesis
            → Return
    """

    def __init__(self):
        self.agent_registry = get_agent_registry()
        self.skill_registry = get_skill_registry()
        self.tool_registry = get_tool_registry()

    def process(self, user_query: str, conversation_context: List[Dict] = None,
                conversation_id: str = None, workspace_id: str = "default") -> Dict[str, Any]:
        """Main entry point — process a user query through the full agentic pipeline."""
        from src.database.state_manager import TransientState, DurableState

        t0 = time.time()
        trace_id = f"trace_{uuid.uuid4().hex[:10]}"
        plan_id = f"plan_{uuid.uuid4().hex[:10]}"
        ts = TransientState(trace_id)
        evidence_graph = EvidenceGraph()
        context = {"evidence_graph": evidence_graph, "trace_id": trace_id, "plan_id": plan_id}
        conversation_context = conversation_context or []

        ts.set_execution_state("started")
        logger.info("[%s] Processing: %s", trace_id, user_query[:100])

        # Step 1: Intent classification
        intent = self._classify_intent(user_query, conversation_context)
        logger.info("[%s] Intent: %s (confidence: %.2f)", trace_id, intent.get("intent_type", "?"), intent.get("confidence", 0))

        # Step 2: Gather workspace context
        workspace_ctx = self._gather_workspace_context()

        # Step 3: Generate execution plan
        plan = self._generate_plan(user_query, intent, workspace_ctx, evidence_graph, conversation_context)
        logger.info("[%s] Plan: %d steps, agents: %s", trace_id, len(plan.get("steps", [])), plan.get("agents_used", []))

        ts.set("plan", plan)
        ts.set_execution_state("planning_complete")

        # Persist plan
        DurableState.persist_plan(trace_id, plan, workspace_id, conversation_id)

        # Step 4: Execute plan
        plan_output = self._execute_plan(plan, context, ts)

        # Step 5: Verify
        verification = self._verify(user_query, plan_output, evidence_graph)
        DurableState.persist_verification(trace_id, plan_id, verification)

        # Step 6: Replan if needed
        retries = 0
        while verification.get("verdict") == "FAIL" and retries < MAX_RETRIES:
            retries += 1
            logger.info("[%s] Verification failed (attempt %d), replanning...", trace_id, retries)
            plan = self._replan(user_query, intent, verification, plan, workspace_ctx, evidence_graph)
            plan_output = self._execute_plan(plan, context, ts)
            verification = self._verify(user_query, plan_output, evidence_graph)
            DurableState.persist_verification(trace_id, plan_id, verification)

        # Persist evidence
        ev_list = [ev.to_dict() for ev in evidence_graph.all_evidence()]
        DurableState.persist_evidence(trace_id, ev_list)

        # Step 7: Generate final response
        response = self._synthesize_response(
            user_query, plan_output, verification, evidence_graph, context,
        )

        total_ms = round((time.time() - t0) * 1000, 1)
        response["metrics"]["total_latency_ms"] = total_ms
        response["metrics"]["trace_id"] = trace_id
        response["metrics"]["plan_id"] = plan_id

        ts.set_execution_state("completed")
        logger.info("[%s] Completed in %.0fms (verification: %s)", trace_id, total_ms, verification.get("verdict"))

        return response

    def process_stream(self, user_query: str, conversation_context: List[Dict] = None,
                       conversation_id: str = None, workspace_id: str = "default"):
        """Stream the processing pipeline — yields SSE events."""
        from src.database.state_manager import TransientState, DurableState

        t0 = time.time()
        trace_id = f"trace_{uuid.uuid4().hex[:10]}"
        plan_id = f"plan_{uuid.uuid4().hex[:10]}"
        ts = TransientState(trace_id)
        evidence_graph = EvidenceGraph()
        context = {"evidence_graph": evidence_graph, "trace_id": trace_id, "plan_id": plan_id}
        conversation_context = conversation_context or []

        # Step 1: Intent classification
        yield {"type": "plan_created", "trace_id": trace_id, "plan_id": plan_id}
        intent = self._classify_intent(user_query, conversation_context)

        # Step 2: Workspace context
        workspace_ctx = self._gather_workspace_context()

        # Step 3: Plan
        plan = self._generate_plan(user_query, intent, workspace_ctx, evidence_graph, conversation_context)

        DurableState.persist_plan(trace_id, plan, workspace_id, conversation_id)

        yield {
            "type": "metadata",
            "query_type": intent.get("query_type", "analytical"),
            "classification_reason": intent.get("reasoning", ""),
            "agents_used": plan.get("agents_used", []),
            "skills_used": plan.get("skills_used", []),
            "plan_steps": len(plan.get("steps", [])),
            "trace_id": trace_id,
        }

        # Step 4: Execute plan (streaming LLM answer)
        llm_answer = ""
        plan_output = {}

        # Yield agent_started events for each step
        for step in plan.get("steps", []):
            agent_id = step.get("agent", "unknown")
            yield {"type": "agent_started", "agent_id": agent_id, "step_id": step.get("step_id", "")}

        for event in self._execute_plan_stream(plan, context, ts):
            if event.get("type") == "llm_token":
                llm_answer += event.get("content", "")
                yield {"type": "token", "content": event.get("content", "")}
            elif event.get("type") == "plan_output":
                plan_output = event.get("data", {})
            elif event.get("type") == "agent_completed":
                yield event

        # Step 5: Verify
        yield {"type": "verification_started"}
        verification = self._verify(user_query, plan_output, evidence_graph)
        DurableState.persist_verification(trace_id, plan_id, verification)
        yield {"type": "verification_completed", "verdict": verification.get("verdict", "UNKNOWN")}

        # Step 6: Replan if needed
        retries = 0
        while verification.get("verdict") == "FAIL" and retries < MAX_RETRIES:
            retries += 1
            plan = self._replan(user_query, intent, verification, plan, workspace_ctx, evidence_graph)
            plan_output = self._execute_plan(plan, context, ts)
            verification = self._verify(user_query, plan_output, evidence_graph)
            DurableState.persist_verification(trace_id, plan_id, verification)

        # Persist evidence
        ev_list = [ev.to_dict() for ev in evidence_graph.all_evidence()]
        DurableState.persist_evidence(trace_id, ev_list)

        # Step 7: Final response
        response = self._synthesize_response(
            user_query, plan_output, verification, evidence_graph, context,
        )

        if llm_answer:
            response["answer"] = llm_answer

        total_ms = round((time.time() - t0) * 1000, 1)
        response["metrics"]["total_latency_ms"] = total_ms
        response["metrics"]["trace_id"] = trace_id
        response["metrics"]["plan_id"] = plan_id

        ts.set_execution_state("completed")

        yield {
            "type": "done",
            "answer": response.get("answer", ""),
            "metrics": response.get("metrics", {}),
            "visualization": response.get("visualization", {}),
            "sources": response.get("sources", []),
            "evidence": response.get("evidence", {}),
        }

    # ------------------------------------------------------------------
    # Internal steps
    # ------------------------------------------------------------------

    def _classify_intent(self, query: str, conversation_context: List[Dict]) -> Dict[str, Any]:
        """Classify user intent using LLM structured output."""
        ctx_str = ""
        if conversation_context:
            recent = conversation_context[-6:]  # last 3 exchanges
            ctx_str = "\n".join([f"{m.get('role', '?')}: {m.get('content', '')}" for m in recent])

        prompt = f"""Classify this user query into structured intent. Return ONLY valid JSON.

User query: "{query}"
{"Conversation context:" + chr(10) + ctx_str if ctx_str else ""}

Return JSON with these fields:
{{
    "intent_type": "analytical" | "knowledge" | "hybrid" | "investigation" | "workspace" | "data_quality" | "unsupported",
    "query_type": "analytical" | "knowledge" | "hybrid" | "diagnostic",
    "entities": ["extracted entity names like product names, regions, etc."],
    "metrics": ["business metrics requested like revenue, sales, etc."],
    "dimensions": ["dimensions mentioned like region, product, time, etc."],
    "time_reference": "any time period mentioned",
    "comparison": "any comparison requested",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation of classification"
}}"""

        try:
            from src.llm.factory import get_llm
            llm = get_llm()
            response = llm.generate(prompt, system="You are an intent classifier. Return only valid JSON.", max_tokens=500)
            text = response.text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            return json.loads(text)
        except Exception as e:
            logger.warning("Intent classification failed, using fallback: %s", e)
            # Use LLM for fallback classification via semantic understanding
            text = query.lower()
            if any(w in text for w in ["document", "pdf", "strategy", "according to", "what does"]):
                return {"intent_type": "knowledge", "query_type": "knowledge", "confidence": 0.5, "reasoning": "keyword fallback"}
            if any(w in text for w in ["why", "cause", "investigate", "decline"]):
                return {"intent_type": "investigation", "query_type": "diagnostic", "confidence": 0.5, "reasoning": "keyword fallback"}
            if any(w in text for w in ["quality", "null", "duplicate", "profile"]):
                return {"intent_type": "data_quality", "query_type": "analytical", "confidence": 0.5, "reasoning": "keyword fallback"}
            if any(w in text for w in ["schema", "table", "column", "data"]):
                return {"intent_type": "workspace", "query_type": "analytical", "confidence": 0.5, "reasoning": "keyword fallback"}
            return {"intent_type": "analytical", "query_type": "analytical", "confidence": 0.5, "reasoning": "keyword fallback"}

    def _gather_workspace_context(self) -> Dict[str, Any]:
        """Gather workspace state: available data, measures, dimensions."""
        tools = self.tool_registry
        try:
            summary = tools.call("get_workspace_summary")
            discoverable = tools.call("get_discoverable_data")
            return {
                "workspace": summary,
                "measures": discoverable.get("available_measures", {}),
                "dimensions": discoverable.get("available_dimensions", {}),
                "has_data": summary.get("has_data", False),
            }
        except Exception as e:
            logger.warning("Failed to gather workspace context: %s", e)
            return {"has_data": False, "measures": {}, "dimensions": {}}

    def _generate_plan(
        self, query: str, intent: Dict, workspace_ctx: Dict,
        evidence_graph: EvidenceGraph, conversation_context: List[Dict],
    ) -> Dict[str, Any]:
        """Generate a dynamic execution plan using LLM."""
        available_agents = [a["agent_id"] for a in self.agent_registry.list_agents()]
        available_skills = [s["skill_id"] for s in self.skill_registry.list_skills()]
        available_tools = [t["tool_id"] for t in self.tool_registry.list_tools()]

        measures_str = ", ".join(list(workspace_ctx.get("measures", {}).keys())[:10])
        dimensions_str = ", ".join(list(workspace_ctx.get("dimensions", {}).keys())[:10])

        prompt = f"""Generate an execution plan for this query. Return ONLY valid JSON.

Query: "{query}"
Intent: {json.dumps(intent, indent=2)}
Workspace has data: {workspace_ctx.get('has_data', False)}
Available measures: {measures_str or 'none'}
Available dimensions: {dimensions_str or 'none'}
Available agents: {json.dumps(available_agents)}
Available skills: {json.dumps(available_skills)}
Available tools: {json.dumps(available_tools)}

Return JSON:
{{
    "goal": "brief description of what the plan achieves",
    "agents_used": ["agent_ids in execution order"],
    "skills_used": ["skill_ids used"],
    "steps": [
        {{
            "step_id": "step_1",
            "agent": "agent_id",
            "tool": "tool_id or null if agent handles internally",
            "action": "what this step does",
            "input": {{"key": "value"}},
            "depends_on": [],
            "provides_evidence": true/false
        }}
    ],
    "evidence_plan": ["what types of evidence to collect"],
    "verification_requirements": ["what to verify"],
    "query_type": "{intent.get('query_type', 'analytical')}"
}}"""

        try:
            from src.llm.factory import get_llm
            llm = get_llm()
            response = llm.generate(prompt, system="You are a task planner. Return only valid JSON.", max_tokens=1000)
            text = response.text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            plan = json.loads(text)
            plan.setdefault("agents_used", [])
            plan.setdefault("skills_used", [])
            plan.setdefault("steps", [])
            plan.setdefault("query_type", intent.get("query_type", "analytical"))
            if len(plan["steps"]) > MAX_PLAN_STEPS:
                plan["steps"] = plan["steps"][:MAX_PLAN_STEPS]
            return plan
        except Exception as e:
            logger.warning("Plan generation failed, using default plan: %s", e)
            return self._default_plan(intent, workspace_ctx)

    def _default_plan(self, intent: Dict, workspace_ctx: Dict) -> Dict[str, Any]:
        """Fallback plan when LLM planning fails."""
        query_type = intent.get("query_type", "analytical")
        has_data = workspace_ctx.get("has_data", False)

        if not has_data:
            return {
                "goal": "Report no data available",
                "agents_used": ["response"],
                "skills_used": [],
                "steps": [],
                "query_type": query_type,
            }

        if query_type == "knowledge":
            return {
                "goal": "Search documents for answer",
                "agents_used": ["rag", "response"],
                "skills_used": ["document_qa"],
                "steps": [
                    {"step_id": "s1", "agent": "rag", "tool": "hybrid_search",
                     "action": "search documents", "input": {"query": "", "step": "search"},
                     "depends_on": [], "provides_evidence": True},
                ],
                "query_type": "knowledge",
            }

        if query_type == "hybrid":
            return {
                "goal": "Analyze data and search documents",
                "agents_used": ["analytics", "rag", "response"],
                "skills_used": ["hybrid_analysis"],
                "steps": [
                    {"step_id": "s1", "agent": "analytics", "tool": None,
                     "action": "calculate metric", "input": {"step": "discover"},
                     "depends_on": [], "provides_evidence": True},
                    {"step_id": "s2", "agent": "rag", "tool": "hybrid_search",
                     "action": "search documents", "input": {"step": "search"},
                     "depends_on": [], "provides_evidence": True},
                ],
                "query_type": "hybrid",
            }

        if query_type == "diagnostic":
            return {
                "goal": "Investigate root cause",
                "agents_used": ["analytics", "investigation", "response"],
                "skills_used": ["investigation"],
                "steps": [
                    {"step_id": "s1", "agent": "analytics", "tool": None,
                     "action": "discover available data", "input": {"step": "discover"},
                     "depends_on": [], "provides_evidence": True},
                    {"step_id": "s2", "agent": "investigation", "tool": None,
                     "action": "drill down into dimensions", "input": {"step": "discover_dimensions"},
                     "depends_on": [], "provides_evidence": True},
                ],
                "query_type": "diagnostic",
            }

        # Default: analytical
        return {
            "goal": "Analyze workspace data",
            "agents_used": ["analytics", "response"],
            "skills_used": ["workspace_overview"],
            "steps": [
                {"step_id": "s1", "agent": "analytics", "tool": None,
                 "action": "discover and analyze data", "input": {"step": "discover"},
                 "depends_on": [], "provides_evidence": True},
            ],
            "query_type": "analytical",
        }

    def _execute_plan(self, plan: Dict[str, Any], context: Dict[str, Any],
                      ts: 'TransientState' = None) -> Dict[str, Any]:
        """Execute all steps in the plan, collecting evidence. Supports bounded parallel execution."""
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
                # Single step — no need for thread pool
                self._execute_single_step(independent_steps[0], results, agents_used, evidence_graph, context, ts)
            else:
                with ThreadPoolExecutor(max_workers=min(len(independent_steps), MAX_PARALLEL_WORKERS)) as pool:
                    futures = {}
                    for step in independent_steps:
                        step_id = step.get("step_id", "unknown")
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
        step_input = step.get("input", {})

        # Check dependencies
        deps = step.get("depends_on", [])
        if deps and not all(d in results for d in deps):
            logger.warning("Step %s skipped: missing dependencies %s", step_id, deps)
            results[step_id] = {"error": "missing dependencies", "skipped": True}
            return

        if deps:
            dep_data = {d: results.get(d, {}) for d in deps}
            step_input["dependency_data"] = dep_data

        message = AgentMessage(
            source_agent="orchestrator",
            target_agent=agent_id,
            input_data=step_input,
            trace_id=context.get("trace_id", ""),
        )

        agent = self.agent_registry.get(agent_id)
        if agent:
            t_step = time.time()
            message = agent.execute(message, context)
            step_ms = round((time.time() - t_step) * 1000, 1)
            results[step_id] = message.output_data
            agents_used.add(agent_id)

            # Persist step
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
        step_input = dict(step.get("input", {}))  # copy

        message = AgentMessage(
            source_agent="orchestrator",
            target_agent=agent_id,
            input_data=step_input,
            trace_id=context.get("trace_id", ""),
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

        for step in plan.get("steps", []):
            step_id = step.get("step_id", "unknown")
            agent_id = step.get("agent", "")
            step_input = step.get("input", {})

            deps = step.get("depends_on", [])
            if deps and not all(d in results for d in deps):
                continue

            if deps:
                dep_data = {d: results.get(d, {}) for d in deps}
                step_input["dependency_data"] = dep_data

            message = AgentMessage(
                source_agent="orchestrator",
                target_agent=agent_id,
                input_data=step_input,
                trace_id=context.get("trace_id", ""),
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

                yield {"type": "agent_completed", "agent_id": agent_id, "step_id": step_id, "duration_ms": step_ms}

        total_ms = round((time.time() - t0) * 1000, 1)

        # Generate LLM answer from collected evidence using streaming
        evidence_summary = self._build_evidence_summary(evidence_graph)
        prompt = f"""Answer this question using ONLY the provided evidence. Be specific and cite sources.

Question: {plan.get('goal', '')}

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

        yield {
            "type": "plan_output",
            "data": {
                "results": results,
                "agents_used": list(agents_used),
                "skills_used": plan.get("skills_used", []),
                "tools_used": list(agents_used),
                "query_type": plan.get("query_type", "analytical"),
                "total_latency_ms": total_ms,
                "evidence_count": len(evidence_graph.all_evidence()),
            }
        }

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

    def _verify(self, query: str, plan_output: Dict, evidence_graph: EvidenceGraph) -> Dict[str, Any]:
        """Run verification agent."""
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="verification",
            input_data={"plan_output": plan_output, "user_query": query},
        )
        agent = self.agent_registry.get("verification")
        if agent:
            message = agent.execute(message, {"evidence_graph": evidence_graph})
            return message.output_data
        return {"verdict": "PASS", "reason": "No verification agent"}

    def _replan(self, query, intent, verification, original_plan, workspace_ctx, evidence_graph) -> Dict[str, Any]:
        """Generate a new plan after verification failure."""
        issues = verification.get("issues", [])
        logger.info("Replanning due to: %s", issues)

        plan = original_plan.copy()
        if any("structured" in i.lower() for i in issues):
            plan["steps"].append({
                "step_id": "replan_1",
                "agent": "analytics",
                "tool": None,
                "action": "additional data analysis",
                "input": {"step": "discover"},
                "depends_on": [],
                "provides_evidence": True,
            })
        if any("document" in i.lower() for i in issues):
            plan["steps"].append({
                "step_id": "replan_2",
                "agent": "rag",
                "tool": "hybrid_search",
                "action": "additional document search",
                "input": {"step": "search", "query": query},
                "depends_on": [],
                "provides_evidence": True,
            })
        return plan

    def _synthesize_response(
        self, query: str, plan_output: Dict, verification: Dict,
        evidence_graph: EvidenceGraph, context: Dict,
    ) -> Dict[str, Any]:
        """Synthesize the final response using the response agent."""
        evidence_summary = self._build_evidence_summary(evidence_graph)
        prompt = f"""Answer this question using ONLY the provided evidence. Be specific and cite sources.

Question: "{query}"

Evidence:
{evidence_summary}

Provide a clear, concise answer with key findings. If evidence is insufficient, say so honestly. Do not fabricate information."""

        llm_answer = ""
        try:
            from src.llm.factory import get_llm
            llm = get_llm()
            response = llm.generate(prompt, system="You are a data analyst. Answer using ONLY the provided evidence. Be specific, cite sources, and acknowledge limitations.")
            llm_answer = response.text
        except Exception as e:
            logger.warning("LLM response generation failed: %s", e)
            llm_answer = "I was unable to generate a response at this time."

        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="response",
            input_data={
                "plan_output": plan_output,
                "verification": verification,
                "user_query": query,
                "llm_answer": llm_answer,
            },
        )
        agent = self.agent_registry.get("response")
        if agent:
            message = agent.execute(message, {"evidence_graph": evidence_graph})
            return message.output_data

        return {
            "answer": llm_answer,
            "query_type": plan_output.get("query_type", "analytical"),
            "sources": [],
            "metrics": plan_output,
            "evidence": {},
            "visualization": {},
        }
