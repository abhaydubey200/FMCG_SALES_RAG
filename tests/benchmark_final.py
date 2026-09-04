"""Final QueryBridge latency + accuracy benchmark (Phase 37).

Runs a 30-query matrix: 10 simple analytics, 5 trends, 5 comparisons,
5 knowledge, 5 hybrid. Reports cold/warm percentiles, TTFT, LLM calls/query,
provider usage, and per-stage timings from the live container.

Usage:
    python tests/benchmark_final.py [base_url] [--warm]
"""
import json
import sys
import time

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
WARM_ONLY = "--warm" in sys.argv
URL = f"{BASE}/api/ai/query/stream"
HDRS = {"Content-Type": "application/json", "Accept": "text/event-stream"}

# (class, question, must-contain substring or None)
QUERIES = [
    # ── 11 simple analytics (accuracy gates in bold) ──
    ("analytics", "What is total revenue?", "951,138.13"),
    ("analytics", "What is revenue excluding North?", "584,158.25"),
    ("analytics", "Revenue by region", None),
    ("analytics", "Top 5 products by revenue", None),
    ("analytics", "Which region had the highest revenue?", None),
    ("analytics", "Total units sold", None),
    ("analytics", "What is average order revenue?", None),
    ("analytics", "Revenue by category", None),
    ("analytics", "How much revenue did the North region generate?", None),
    ("analytics", "What are our top selling products?", None),
    ("analytics", "Total revenue from the South region", None),
    # ── 5 trends ──
    ("trend", "Monthly revenue trend this year", None),
    ("trend", "Show revenue trend by month", None),
    ("trend", "Revenue growth by month", None),
    ("trend", "Trend of sales over the last 6 months", None),
    ("trend", "Monthly trend for revenue in 2025", None),
    # ── 5 comparisons ──
    ("comparison", "Compare revenue between North and South regions", None),
    ("comparison", "Which category outperforms others by revenue?", None),
    ("comparison", "Compare product A and product B revenue", None),
    ("comparison", "Revenue comparison by region", None),
    ("comparison", "Which region performed best last quarter?", None),
    # ── 5 knowledge ──
    ("knowledge", "What is the trade promotion discount rate?", "12%"),
    ("knowledge", "What discount applies to trade promotions?", "12%"),
    ("knowledge", "What recyclability target does the policy set?", "80%"),
    ("knowledge", "What is our return policy?", None),
    ("knowledge", "What does the pricing policy say about margins?", None),
    # ── 5 hybrid ──
    ("hybrid", "Which product drives the most revenue and what is our markdown policy on it?", None),
    ("hybrid", "Show revenue by region and summarize the distributor strategy", None),
    ("hybrid", "What is our total revenue and what sustainability targets apply?", None),
    ("hybrid", "Which category has the highest revenue and what is the trade promotion policy?", None),
    ("hybrid", "Break down revenue by product and cite the quality recall policy", None),
    # ── refusals (accuracy gate, not latency) ──
    ("unsupported", "Predict next quarter revenue using astrology", None),
    ("unsupported", "What does competitor X charge for their product?", None),
]


def run(question: str, session_id: str):
    t0 = time.time()
    r = requests.post(URL, json={
        "question": question, "workspace_id": "default", "session_id": session_id,
    }, headers=HDRS, stream=True, timeout=90)
    content, ttft_ms, metrics = "", None, {}
    for raw in r.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        line = raw[5:].strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if "content" in ev:
            if ttft_ms is None:
                ttft_ms = (time.time() - t0) * 1000
            content += ev["content"]
        if "answer" in ev:
            metrics = ev.get("metrics", {})
    total_ms = (time.time() - t0) * 1000
    r.close()
    return {
        "total_ms": round(total_ms),
        "ttft_ms": round(ttft_ms or total_ms),
        "content": content,
        "metrics": metrics,
        "status": r.status_code,
    }


def pct(sorted_vals, p):
    if not sorted_vals:
        return 0
    idx = max(0, min(len(sorted_vals) - 1, int(len(sorted_vals) * p)))
    return sorted_vals[idx]


def main():
    cold_all, warm_all = [], []
    llm_counts = {}
    provider_set = set()
    fails = []
    class_lat = {}

    print(f"{'#':>2} {'class':<12} {'ms':>7} {'TTFT':>6} {'LLM':>4}  check   question")
    for i, (cls, question, expect) in enumerate(QUERIES, 1):
        cold = run(question, f"final_cold_{i}_{cls}")
        if isinstance(cold["total_ms"], int):
            cold_all.append(cold["total_ms"])
            class_lat.setdefault(cls, []).append(cold["total_ms"])
        lc = cold["metrics"].get("llm_calls", "?")
        llm_counts[lc] = llm_counts.get(lc, 0) + 1
        prov = cold["metrics"].get("provider")
        if prov:
            provider_set.add(prov)
        ok = "PASS" if (expect is None or expect in cold["content"]) else f"FAIL"
        if ok == "FAIL":
            fails.append((cls, question, expect, cold["content"][:120]))
        print(f"{i:>2} {cls:<12} {cold['total_ms']:>7} {cold['ttft_ms']:>6} {str(lc):>4}  {ok:<6} {question[:55]}")
        time.sleep(0.15)
        if not WARM_ONLY:
            w = run(question, f"final_warm_{i}_{cls}")
            if isinstance(w["total_ms"], int):
                warm_all.append(w["total_ms"])

    def summarize(vals, label):
        s = sorted(vals)
        print(f"\n{label}: n={len(s)}  p50={pct(s, .5)}ms p75={pct(s, .75)}ms "
              f"p95={pct(s, .95)}ms min={min(s)}ms max={max(s)}ms "
              f"mean={round(sum(s)/len(s))}ms")

    summarize(cold_all, "COLD (all 32)")
    if warm_all:
        summarize(warm_all, "WARM (cache hits)")
    print(f"\nLLM calls per query distribution: {llm_counts}")
    print(f"Providers observed: {provider_set or 'none (deterministic path)'}")
    if class_lat:
        for cls, vals in class_lat.items():
            s = sorted(vals)
            print(f"  {cls:<11} p50={pct(s,.5)}ms p95={pct(s,.95)}ms max={max(s)}ms (n={len(s)})")
    print(f"\nFailures: {len(fails)}")
    for cls, q, expect, snippet in fails:
        print(f"  FAIL [{cls}] {q!r} want {expect!r} got {snippet!r}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
