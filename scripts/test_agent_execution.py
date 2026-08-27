"""
Test script that proves agents, tools, and skills actually execute.

Usage:
    python scripts/test_agent_execution.py

Calls the API with a query and prints the full execution trace.
"""
import json
import sys
import requests

API_BASE = "http://localhost:8000"


def test_query(question: str):
    print(f"\n{'='*70}")
    print(f"QUERY: {question}")
    print(f"{'='*70}\n")

    # Call the agentic endpoint
    resp = requests.post(f"{API_BASE}/api/ai/query", json={
        "question": question,
        "workspace_id": "default"
    }, timeout=120)

    if resp.status_code != 200:
        print(f"ERROR: HTTP {resp.status_code}")
        print(resp.text[:500])
        return

    data = resp.json()

    # Print the answer
    print("ANSWER:")
    print("-" * 40)
    print(data.get("answer", "No answer"))
    print()

    # Print execution metrics
    metrics = data.get("metrics", {})
    print("EXECUTION METRICS:")
    print("-" * 40)
    print(f"  Trace ID:    {metrics.get('trace_id', 'N/A')}")
    print(f"  Plan ID:     {metrics.get('plan_id', 'N/A')}")
    print(f"  Query Type:  {data.get('query_type', 'N/A')}")
    print(f"  Latency:     {metrics.get('total_latency_ms', 'N/A')}ms")
    print()

    # Print agents that actually executed
    agents_used = metrics.get("agents_used", [])
    print(f"AGENTS EXECUTED ({len(agents_used)}):")
    print("-" * 40)
    if agents_used:
        for i, agent in enumerate(agents_used, 1):
            print(f"  {i}. {agent}")
    else:
        print("  (none)")
    print()

    # Print skills used
    skills_used = metrics.get("skills_used", [])
    print(f"SKILLS USED ({len(skills_used)}):")
    print("-" * 40)
    if skills_used:
        for i, skill in enumerate(skills_used, 1):
            print(f"  {i}. {skill}")
    else:
        print("  (none)")
    print()

    # Print evidence collected
    evidence = data.get("evidence", {})
    ev_items = evidence.get("items", [])
    print(f"EVIDENCE COLLECTED ({len(ev_items)} items):")
    print("-" * 40)
    for i, ev in enumerate(ev_items[:5], 1):
        ev_type = ev.get("type", "unknown")
        source = ev.get("source", "N/A")
        print(f"  {i}. [{ev_type}] source: {source}")
        if ev.get("sql_query"):
            print(f"     SQL: {ev['sql_query'][:100]}")
        if ev.get("text"):
            print(f"     Text: {ev['text'][:100]}...")
    print()

    # Print sources
    sources = data.get("sources", [])
    print(f"SOURCES ({len(sources)}):")
    print("-" * 40)
    for i, src in enumerate(sources, 1):
        print(f"  {i}. [{src.get('type', '?')}] {src.get('source', 'N/A')}")
    print()

    # Print visualization
    viz = data.get("visualization", {})
    kpis = viz.get("kpis", [])
    charts = viz.get("charts", [])
    print(f"VISUALIZATION:")
    print("-" * 40)
    print(f"  KPIs:   {len(kpis)}")
    print(f"  Charts: {len(charts)}")
    for kpi in kpis:
        print(f"    - {kpi.get('label', '?')}: {kpi.get('value', '?')}")
    for chart in charts:
        print(f"    - {chart.get('type', '?')}: {chart.get('title', '?')} ({len(chart.get('data', []))} data points)")
    print()


def main():
    print("QueryBridge — Agent/Tool/Skill Execution Test")
    print("=" * 70)

    # Check API health
    try:
        health = requests.get(f"{API_BASE}/health", timeout=5).json()
        print(f"API Status: {health.get('status', 'unknown')}")
    except Exception as e:
        print(f"ERROR: Cannot reach API at {API_BASE}: {e}")
        sys.exit(1)

    # Test 1: Simple analytical query (should use analytics agent)
    test_query("What are total sales?")

    # Test 2: Ranking query (should use analytics + investigation)
    test_query("Which product generated the highest revenue?")

    # Test 3: Trend query (should use analytics with visualization)
    test_query("Show the monthly sales trend.")

    # Test 4: Diagnostic query (should use investigation agent)
    test_query("Why did sales decline?")

    # Test 5: Knowledge query (should use RAG agent if documents exist)
    test_query("What does our strategy document recommend?")

    # Test 6: Hybrid query (should use multiple agents)
    test_query("Combine sales data and strategy recommendations.")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
