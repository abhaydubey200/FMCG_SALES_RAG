# QueryBridge — Final Repository Forensics

*Audit date: 2026-09-04 · Repository: FMCG_SALES_RAG (local clone) · Release branch: `release-v2.3-certified` (commit `ef9a94e`)*
*Method: source tracing, import tracing, live-container env/DB inspection, runtime probing — no file assumed active just because it exists.*

```text
ACTIVE ARCHITECTURE
ACTIVE ENDPOINTS
ACTIVE ORCHESTRATOR
ACTIVE ROUTER
ACTIVE LLM PROVIDER
ACTIVE DATABASE
ACTIVE VECTOR STORE
ACTIVE CACHE
DEAD/LEGACY CODE
CONFIGURATION RISKS
```

## ACTIVE ARCHITECTURE

FastAPI (`src/api/main.py`) + agentic orchestrator V2 (`src/agents/orchestrator_v2.py`) +
deterministic router (`src/agents/router.py`, incl. explicit `CAUSAL_ANALYSIS` intent) +
semantic resolver (`src/agents/semantic.py`) + workspace-scoped analytics engine over
PostgreSQL (`src/analytics/dynamic_engine.py`) + TF-IDF RAG pipeline (7 documents /
33 chunks) + Next.js frontend + Nginx. Workspace isolation is enforced end-to-end:
datasets, documents, RAG chunks/retrieval, semantic mappings, conversations, and cache
keys are all scoped by `workspace_id` (see `tests/e2e/test_workspace_isolation.py`).

Runtime path traced from imports and execution:

```text
POST /api/ai/query  →  _get_orchestrator() → Orchestrator (orchestrator_v2)
  → Stage 0  workspace-scoped response cache (in-process LRU, TTL 300)
  → Stage 1  FastRouter.route()                     (deterministic, ~1 ms, 0 LLM; CAUSAL detection)
  → Stage 2  SemanticResolver.resolve()             (deterministic, ~1 ms)
  → Stage 3  per-workspace context (workspace-scoped cache, 60 s)
  → Stage 4  deterministic plan (analytics / rag / hybrid / causal-driver evidence)
  → Stage 5  parallel SQL + RAG execution (agents: analytics, rag)
  → Stage 6  deterministic verification (PASS only when evidence_count ≥ 1 and no step errors)
  → Stage 7  deterministic answer OR exactly one bounded LLM synthesis (provider policy)
  → SSE / JSON response
```

## ACTIVE ENDPOINTS

All endpoints traced in `src/api/main.py` and confirmed live via the running container:

| Endpoint | Purpose |
|---|---|
| `POST /api/ai/query` | Workspace-scoped AI query (JSON answer + metrics) |
| `POST /api/ai/query/stream` | Same via genuine SSE (progressive `token` events) |
| `POST /api/ai/route` | Debug: deterministic routing decision |
| `GET /health` | Status: `llm_backend=groq`, cache + template synthesis on |
| `POST /api/datahub/upload` | Structured dataset ingest (workspace-scoped) |
| `GET /api/datahub/datasets` | List datasets for a workspace |
| `DELETE /api/datahub/datasets/{id}` | Delete dataset (workspace-scoped) |
| `POST /documents/upload` | Unstructured doc upload (workspace-scoped) |
| `GET /api/data-center`, `GET/DELETE /api/data-center/{asset_id}` | Unified asset registry (workspace-filtered) |
| Conversations CRUD | `POST/GET/DELETE /api/conversations...` — all workspace-owned |
| Dashboard / insights / executive-brief / investigation / semantic / data-quality / search | All accept + enforce `workspace_id` |

Legacy `POST /query` (default-workspace alias of `/api/ai/query`) remains for back-compat.

## ACTIVE ORCHESTRATOR

`src/agents/orchestrator_v2.py` is the sole active orchestrator. It owns the
evidence contract, causal evidence pipeline, deterministic answer templates, and
the single bounded LLM-synthesis gate (`_needs_llm_synthesis` → only COMPLEX with
real evidence, exactly 1 call). V1 `src/agents/orchestrator.py` is a dead fallback
(imported only if V2 import raises); its prompt was scrubbed of a hardcoded demo
number (951138.13) during the audit.

## ACTIVE ROUTER

`src/agents/router.py` — deterministic FastRouter. Zero-signal queries route to
AMBIGUOUS; causal phrasing (`why`, `what caused`, `drivers of`, `root cause`,
`what explains`, causal tie-break) routes to COMPLEX with a `causal` flag; all
analytics/RAG/hybrid/unsupported classes preserved. 10/10 causal battery + full
regression pass (see `tests/test_causal_routing.py`).

## ACTIVE LLM PROVIDER

- **Primary:** Groq (`GROQ_MODEL=openai/gpt-oss-120b`) via `src/llm/groq_client.py`.
- **Fallback:** NVIDIA (bounded, `LLM_TIMEOUT_SECONDS` capped at 45 s in provider
  policy) — verified live with `GROQ_API_KEY=` cleared: NVIDIA answered in ~3 s.
- **Policy:** `src/llm/provider_policy.py` — Groq synthesis capped at 8 s, one
  bounded retry maximum, NVIDIA fallback, honest failure when both unavailable.
  No Groq→NVIDIA→Groq loops.

## ACTIVE DATABASE

PostgreSQL 16 (container `ragsql-postgres`, named volume). Workspace-scoped tables:
`assets`, `datasets`, `dataset_columns`, `data_quality_results`, `semantic_mappings`,
`documents`, `document_chunks`, `conversations`, `conversation_messages`,
`workspaces`. Certified seed: 3 datasets (North/South/ERP) → total **951,138.13**.
DB failure surfaces as an error, never as an empty workspace (all discovery
functions raise `RuntimeError` instead of returning empty on connection failure).

## ACTIVE VECTOR STORE

TF-IDF in-process vector store (`src/retrieval/vector_store.py`) + BM25 keyword
index + hybrid fusion. Persisted to `data/vector_store.pkl` (git-ignored,
regenerated at startup via `load_knowledge_base()`). Chunks carry `workspace_id`
metadata (re-tagged on load for stale pickles); search is workspace-filtered.
Corpus: 7 documents / 33 chunks across `data/knowledge_base/`.

## ACTIVE CACHE

In-process TTL cache (`src/llm/query_cache.py`) keyed on
`workspace_id|normalized_question` — never cross-workspace. Dataset/document
mutations call `clear_all_caches()` (and workspace-cache clear), so stale data is
never served. Verified: identical question in workspace A (1000) and B (9000)
returns each workspace's own number.

## DEAD/LEGACY CODE

| Path | Status |
|---|---|
| `src/agents/orchestrator.py` | Legacy V1 orchestrator — dead fallback only |
| `src/rag/pipeline.py` (RAGPipeline.answer) | Legacy LLM-per-answer path; V2 uses it only for chunk store/retrieval primitives |
| `src/rag/query_classifier.py`, `src/analytics/sql_layer.py` (SQLite) | V1-era; not on the active V2 path |
| Streamlit app / SQLite `warehouse.db` | Removed/not referenced in README's current runtime |
| `data/vector_store.pkl`, `data/documents/`, `__pycache__/`, `.env` | Generated/secret — git-ignored |
| `fmcg-real-scale-test-data/` | Untracked 26 MB scratch — never committed |

## CONFIGURATION RISKS

- API keys exist only in local `.env` (git-ignored); `.env.example` has placeholders.
- Auth/RBAC is not implemented — `workspace_id` is client-supplied. All service
  boundaries validate it (never silently falls back to another workspace), but a
  real multi-tenant deployment must derive workspace from an authenticated
  context (documented in README Security).
- Complex LLM synthesis is bounded (<10 s measured p95 ~1.9 s); NVIDIA fallback
  depends on `LLM_API_KEY` being present.
- `docker compose` forwards `GROQ_API_KEY`/`LLM_API_KEY` from `.env` only — a
  fresh clone without keys runs deterministic paths but cannot synthesize.
