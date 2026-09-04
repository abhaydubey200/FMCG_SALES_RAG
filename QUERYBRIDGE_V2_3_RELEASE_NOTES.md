# QueryBridge V2.3 Release Notes

*Release branch: `release-v2.3-certified` · Commit: `ef9a94e` · Date: 2026-09-04*

## What this release is

V2.3 resolves the four blockers recorded in the V2.2 production audit
(`QUERYBRIDGE_FINAL_PRODUCTION_CERTIFICATION.md`, verdict: NOT VERIFIED) without
redesigning the working V2.1/V2.2 architecture. Every previously PASSing result
was preserved and re-verified; the final verdict is now
**VERIFIED — PRODUCTION-CREDIBLE RELEASE**.

## Blocker resolutions

### 1. Release reproducibility (Blocker 1) — RESOLVED

The certified state is committed to `release-v2.3-certified` (previously all
work was uncommitted on `qb-phase1-state`). A true fresh-clone test was run:

```
git clone --branch release-v2.3-certified <repo> → clean directory
cp .env.example .env  (+ provider test keys — no .env/volumes/pickles copied)
docker compose down -v && docker compose build --no-cache && docker compose up -d
```

The clean build auto-seeded 3 datasets + 7 documents / 33 chunks and reproduced
every certified number: **951,138.13 · 366,979.88 · 328,460.90 · 255,697.35 ·
584,158.25 · 12% · 80%** · SQL security suite · workspace isolation · causal
routing · streaming · NVIDIA fallback.

### 2. End-to-end workspace isolation (Blocker 2) — RESOLVED

`workspace_id` is now enforced across every user-owned entity and every
read/write/list/delete path:

- structured datasets, uploaded files, dataset metadata, semantic mappings,
  metrics/dimensions/aliases
- knowledge documents, chunks, vector/RAG records
- conversations + messages, cache entries, data-center assets, insights

Mandatory A/B test: Workspace A revenue=1000, Workspace B revenue=9000. Both ask
"What is total revenue?" → A gets 1000, B gets 9000, never crossed — verified
across SQL, cache, RAG (10% vs 20% promo documents), conversations, listing,
search, delete. Same dataset names / document names / questions across A and B
are fully isolated (`tests/e2e/test_workspace_isolation.py`, 7/7 PASS).

Also fixed: identical file content uploaded to two workspaces previously
collided on `dataset_id` — dataset ids are now workspace-namespaced, and
re-ingestion is idempotent (upsert + child-row cleanup, no duplicate ingestion).

### 3. Causal query routing (Blocker 3) — RESOLVED

The router now has explicit `CAUSAL_ANALYSIS` intent: `why`, `what caused`,
`caused by`, `reason for`, `driver(s) of`, `what drove`, `root cause`,
`explain the decline/increase`, plus a causal tie-break — causal questions no
longer masquerade as plain revenue retrieval. The orchestrator gathers driver
evidence (discount, quantity, spend by region/product) and the synthesis prompt
mandates:

- OBSERVED facts vs INFERRED causes are labeled separately
- a cause is only claimed when evidence supports it
- otherwise: "the available data supports the change, but it does not provide
  enough evidence to establish the cause" — no invented causality

Verified: 10/10 causal questions route to COMPLEX with exactly 1 LLM call and
honest observed/inferred answers; non-causal routing is unchanged.

### 4. Complex latency (Blocker 4) — RESOLVED

The 12.9 s complex-query outlier was a slow, uncapped Groq synthesis. The
provider policy now caps Groq synthesis at **8 s** (healthy calls ~1–2 s are
unaffected) with a bounded NVIDIA fallback — no retry loops. Measured after the
fix: complex p50 1.6 s / p95 1.9 s / max 1.9 s, well under the 10 s target.

## Verified performance

| Metric | Value |
|---|---|
| Deterministic accuracy | 33/33 PASS, 0 LLM calls |
| Cold p50 / p95 | 166 ms / 337 ms |
| Warm (cache) p50 | 29 ms |
| Complex p95 (1 LLM call) | 1.9 s |
| Concurrency (10×) | 10/10, 0 errors |
| Streaming TTFT | 63 ms (135 progressive token events) |
| NVIDIA fallback | ~3 s with Groq disabled |

## New tests

- `tests/test_causal_routing.py` — causal intent routing + honesty
- `tests/e2e/test_workspace_isolation.py` — cross-workspace A/B matrix
- Exclusion/unknown-region ground truths in `tests/e2e/test_revenue_ground_truth.py`
  and `tests/benchmark_final.py`

## Files touched (highlights)

`src/agents/router.py`, `src/agents/orchestrator_v2.py`, `src/agents/tools/*`,
`src/agents/specialists/rag_agent.py`, `src/analytics/dynamic_engine.py`,
`src/ingestion/document_loader.py`, `src/retrieval/{vector_store,keyword_search,
hybrid_retriever}.py`, `src/llm/provider_policy.py`, `src/api/main.py`,
`src/config.py`, `README.md`, `.env.example`, tests (above). Full list in the
certification report §20.

## Known limitations

- No auth/RBAC yet — `workspace_id` is client-supplied and validated at every
  service boundary; multi-tenant production should derive it from an
  authenticated session (see README Security).
- Groq simple synthesis measured 1.4–2.2 s (vendor claims of ~0.5–1.2 s are not
  reproduced); latency targets are still met with margin.
- Causal analysis is evidence-grounded, not a full time-series causal engine.

## How to run

```bash
git clone --branch release-v2.3-certified <repo-url>
cd <repo>
cp .env.example .env    # add GROQ_API_KEY (and optionally LLM_API_KEY for NVIDIA fallback)
docker compose up -d    # first build takes a while
# UI: http://localhost:3000  ·  API: http://localhost:8000/docs
```
