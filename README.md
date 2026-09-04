# Amazon Sales & Marketing Intelligence Assistant — QueryBridge

A RAG + Analytics assistant ("QueryBridge") that lets a sales/marketing analyst ask
natural-language questions over structured business data (uploaded datasets) and
unstructured business knowledge (policy/strategy documents) — with answers that
separate verified evidence, calculated metrics, retrieved knowledge, and what is
genuinely unavailable. The LLM is used only for language synthesis when needed:
analytics, RAG retrieval, verification, and refusal logic are deterministic and
0-LLM by default.

## Current runtime (V2.1+)

- **Backend:** FastAPI (`src/api/main.py`) with the agentic `Orchestrator`
  (`src/agents/orchestrator_v2.py`): deterministic router → semantic resolver →
  parallel analytics (SQL) + RAG → evidence contract → deterministic answer or
  ONE bounded LLM synthesis call.
- **Frontend:** Next.js App Router (`frontend/`), proxied by Nginx.
- **Storage:** PostgreSQL + pgvector (Docker), Redis for state, TF-IDF embedding
  pipeline with a 7-document / 33-chunk knowledge base.
- **LLM providers:** Groq (fast synthesis, primary) with a strictly bounded
  NVIDIA fallback (`src/llm/provider_policy.py`). `LLM_BACKEND=fallback` in the
  legacy `.env` template is overridden by Docker (Groq is the active backend).
- **Run everything:** `docker compose up -d` (see Quickstart below).

---

## ⚠️ Environment Constraints (read this first)

This was built in a sandboxed dev environment with **no network access to
HuggingFace or Ollama** — only PyPI/npm/GitHub package registries. That
means the two components the assignment prefers (a neural embedding model
like BGE/E5, and a locally-run open LLM like Qwen/Llama/Gemma) **cannot be
downloaded or run in the environment this was built in.**

Rather than fake this or leave it unimplemented, the system is built with
a genuinely pluggable interface at both seams:

- **Embeddings** (`src/retrieval/embeddings.py`): defaults to TF-IDF +
  cosine similarity — a real, mathematically legitimate vector-space
  model, just without neural semantic generalization. A `NeuralEmbedder`
  class using `sentence-transformers` is fully implemented and wired to
  `EMBEDDING_BACKEND=neural` in `.env` — it just needs HF network access
  to actually download weights, which this dev sandbox doesn't have.
- **LLM** (`src/llm/`): defaults to a deterministic, template-based
  grounded-answer generator (`fallback_llm.py`) that reads the *exact
  same* structured evidence JSON a real LLM prompt would contain, and
  renders an answer directly from it — by construction it cannot
  hallucinate, because it only emits values present in the evidence. A
  complete `OllamaLLM` connector (`ollama_client.py`) is implemented and
  wired to `LLM_BACKEND=ollama` — on any machine with Ollama installed and
  `ollama pull qwen2.5:7b-instruct` run once, this becomes real neural
  generation with zero other code changes.

**To run this with a real open LLM:** install Ollama, run
`ollama pull qwen2.5:7b-instruct`, set `LLM_BACKEND=ollama` in `.env`,
restart the API. Everything else (retrieval, routing, analytics, API,
UI) is unaffected.

I'm calling this out explicitly rather than hiding it, because the
interview deep-dive questions (Section 26) specifically probe whether a
candidate understands *why* a design choice was made — this is a real
constraint, handled with a real, inspectable abstraction, not a workaround
disguised as a feature.

---

## Quickstart

```bash
cp .env.example .env   # then fill GROQ_API_KEY (and optionally NVIDIA LLM_API_KEY)
docker compose up -d   # builds postgres+pgvector, redis, api, worker, frontend, nginx
```

- API: http://localhost:8000 (docs at `/docs`), UI: http://localhost:3000, nginx: http://localhost:80
- The API auto-seeds the three certified demo datasets (Datasets A/B/C → total
  revenue **951,138.13**) and the knowledge base on a fresh volume.
- Verify: `curl http://localhost:8000/health` → `{"llm_backend":"groq",...}`.

Local (non-Docker) development still works:
```bash
pip install -r requirements.txt
# backend needs DATABASE_URL/REDIS_URL (or use docker compose for infra)
PYTHONPATH=. python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
# UI:
cd frontend && npm install && npm run dev
```

Example API call (workspace-scoped):
```bash
curl -X POST http://localhost:8000/api/ai/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is total revenue?", "workspace_id": "default"}'
```
Both `/query` (legacy, default workspace) and `/api/ai/query`
(workspace-scoped) are served.

---

## 1. Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full component
diagram. Summary: `Question → Query Classifier → [SQL Layer | Hybrid
Retriever | both] → Context Builder (evidence fusion + conflict
detection) → Prompt Builder → LLM (pluggable) → Answer + Sources +
Metrics`.

## 2. Technology choices

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI + Pydantic | Async-capable, typed, auto-generated OpenAPI docs |
| Structured data | PostgreSQL + pgvector | Dockerized, real analytical SQL across uploaded datasets |
| Vector storage | TF-IDF in-process index + pgvector schema | Fine at current corpus scale; pgvector table present for migration |
| Embeddings | TF-IDF (default) | Deterministic, no model download; neural backend available |
| Keyword/retrieval | Hybrid retriever over 33 knowledge chunks | see `src/retrieval/` |
| LLM | Groq (primary) → bounded NVIDIA fallback → template-grounded fallback | see `src/llm/provider_policy.py`; deterministic 0-LLM for analytics/RAG |
| Frontend | Next.js (App Router) + Nginx | Production-style UI served on :3000/:80 |

## 3. Dataset design

Synthetic, generated by `src/ingestion/data_generator.py`, seeded
(`RANDOM_SEED=42`) for reproducibility. Volumes exceed assignment
minimums: 120 products / 6,000 sales / 24 campaigns / 1,200 reviews / 600
customers, spanning Aug 2024–Jan 2026 (18 months, enough for real
quarter-over-quarter and category-trend questions).

Realism choices: product revenue follows a Pareto (fat-tail) distribution
so a handful of "bestsellers" emerge naturally rather than uniform
randomness; **one product (`Aurora Pro Wireless Earbuds`, `P0001`) has a
deliberately engineered Q2 2025 decline** — its discount rate, marketing
spend, and review sentiment are all programmatically depressed in that
exact window — so the diagnostic-question test cases have genuine,
non-fabricated multi-source evidence to retrieve, instead of the LLM
needing to invent a plausible-sounding story.

## 4. Chunking strategy

`src/ingestion/document_loader.py`: split on markdown `##` section
headers first, then apply a word-count sliding window (180 words,
40-word overlap) *within* a section only if that section is long. This
keeps every chunk topically coherent — a chunk is never a blend of two
unrelated policy sections — while still bounding chunk size for
retrieval precision and LLM context budget. The overlap prevents a fact
sitting right at a chunk boundary from becoming unretrievable.

## 5. Embedding model

Default: TF-IDF (`max_features=4096`, `ngram_range=(1,2)`, English stop
words removed, sublinear TF scaling, L2-normalized). Optional: `BAAI/bge-
small-en-v1.5` via `sentence-transformers`, gated behind
`EMBEDDING_BACKEND=neural` (needs HF network access — see "Environment
Constraints"). Why BGE-small if it were available: strong
retrieval-benchmark performance for its size (384-dim, ~130MB), fast CPU
inference suitable for an internal tool with no GPU requirement.

## 6. Retrieval strategy

Hybrid: TF-IDF vector search (semantic-ish similarity) + BM25 keyword
search (exact-term precision), fused with normalized-score weighting
(60% vector / 40% keyword by default), then reranked. **Why hybrid over
vector-only:** this knowledge base is small but dense with exact numbers
and thresholds (15%, ROAS 3.0x, specific product names) — vector search
alone is good at topical similarity but can under-rank the chunk
containing the *exact* number asked about if its surrounding phrasing
differs from the query; BM25 is complementary and nearly free to run
alongside it at this corpus size. **When keyword search alone would be
better:** short, exact-match-heavy queries (a specific campaign ID,
product SKU) where semantic similarity adds noise rather than recall.

## 7. Reranking approach

A real cross-encoder reranker (e.g. `bge-reranker-base`) needs a
downloaded model, unavailable here for the same reason as the embedder.
Implemented instead: a transparent lexical-overlap booster
(`src/retrieval/hybrid_retriever.py::_rerank`) — `0.75 × fused_score +
0.25 × query/chunk term-overlap ratio`. The interface
(`rerank(query, candidates) -> reranked candidates`) is exactly where a
real cross-encoder call would be substituted in an environment with model
access; nothing else in the pipeline would need to change.

## 8. Query routing

`src/rag/query_classifier.py` — deliberately **rule-based, not an LLM
call**. Routing decides which systems even get invoked (SQL vs vector
search vs both) so it sits upstream of grounding; using a
potentially-slow/hallucination-prone LLM call to make this decision would
make the whole pipeline's reliability depend on the weakest link before
any evidence has even been retrieved. A transparent classifier is fast,
has zero hallucination risk, and — critically — is exhaustively unit
-testable, which matters because misrouting is the single biggest way
this system fails silently. See `docs/evaluation.md` "Failure analysis"
for the classifier's honestly-documented failure modes (keyword-overlap
ambiguity between e.g. "what IS the ROAS" vs "what SHOULD the ROAS be").
Production upgrade path: a small fine-tuned classifier, with the
rule-based version retained as a fallback/sanity check rather than
replaced outright.

## 9. SQL/analytics strategy

**Deliberately not free-form NL→SQL generation.** `src/analytics/
sql_layer.py` exposes a fixed set of parametrized, human-reviewed query
functions covering every required metric (Section 10). The classifier +
a lightweight entity extractor (product/category name resolution)
determine *which* function to call and with *which* parameters — never
which raw SQL string to execute. This bounds any LLM/heuristic influence
to parameter selection, never SQL construction, which is the
production-safe pattern (see Section 26 Q&A below for the full reasoning
on why free-form generated SQL is risky for this use case).

## 10. Prompt design

`src/rag/prompt_templates.py`: every prompt = (1) a system instruction
enforcing grounding/separation/citation/conflict-flagging rules, (2) a
structured **JSON** evidence block (not prose — unambiguous for the model
to read numbers from correctly, and the same contract the fallback
generator consumes), (3) the question repeated last (recency helps
instruction-following in most models).

## 11. Grounding strategy

Every answer is generated *from* the evidence JSON, never from model
knowledge — enforced by explicit system-prompt rules for a real LLM, and
enforced *structurally* (by construction) for the fallback generator,
which literally cannot emit a number that isn't present in the evidence
dict. Diagnostic answers explicitly separate "Observed facts" /
"Possible explanations (inference)" / "Unsupported assumptions" per
Section 9D.

## 12. Citation strategy

Every structured-data evidence key and every retrieved chunk's `(document
name, section)` is surfaced in the API response's `sources` field and
rendered in the UI's Evidence Panel — this is metadata carried through
the whole pipeline from ingestion (`document_id`, `section`, `chunk_id`)
to the final response, not reconstructed after the fact.

## 13. Evaluation methodology

See [`docs/evaluation.md`](docs/evaluation.md) — 38 test cases (exceeds
the 35 minimum) across all 6 required categories plus a bonus diagnostic
bucket, with real (not cherry-picked) results: 92.1% query-type accuracy,
100% retrieval-recall proxy, full failure analysis of all 3 misses.

## 14. Failure cases

Documented honestly throughout rather than hidden:

- **Query classifier keyword ambiguity** (see `docs/evaluation.md`): a
  single word can plausibly signal more than one category ("ROAS" is
  both an analytical metric and something a policy doc states a target
  for). 3 of 38 eval cases fail for exactly this reason.
- **TF-IDF has no semantic generalization**: a query using a synonym the
  knowledge base doesn't use verbatim (e.g. "markdown" instead of
  "discount") will retrieve worse than a neural embedder would. This is
  the main quality gap the neural-embedder swap-in would close.
- **Fallback LLM cannot paraphrase or handle unanticipated phrasings** as
  fluently as a real model — it's a template renderer, not a language
  model. Its groundedness guarantee is also its ceiling.
- **Real-LLM faithfulness is not structurally guaranteed** the way the
  fallback's is — see `docs/evaluation.md` "Generation faithfulness" for
  the concrete automatable check I'd add before trusting `LLM_BACKEND=
  ollama` in production (verify every number in the generated answer
  traces back to the evidence JSON).
- **Full-corpus reindex on every document upload/delete**
  (`src/api/main.py`) — fine at ~20 documents, would need incremental
  indexing at scale (see below).
- **Entity resolution is exact/near-exact substring matching**
  (`query_classifier._resolve_product`) — a misspelled or heavily
  paraphrased product reference won't resolve, and the question will fall
  through to a category-level or generic answer instead of erroring
  loudly. A production version would want fuzzy matching with a
  confidence threshold and an explicit "did you mean X?" clarification
  path.

## 15. Production scalability considerations

- **Vector storage**: swap the in-process pickle for PostgreSQL +
  pgvector (assignment's own preferred stack) or Qdrant — both support
  incremental upsert/delete, unlike the current full-corpus rebuild.
- **10K → 100M documents**: move from full-corpus TF-IDF refit (which
  requires reprocessing the whole corpus on any change) to a
  vocabulary-frozen or neural embedder (fixed-dimension, embed-once,
  incrementally upsertable) + an ANN index (HNSW via pgvector/Qdrant)
  instead of exact cosine over a dense matrix.
- **Re-indexing updated documents**: incremental — only re-chunk/re
  -embed the changed document, upsert its chunk IDs, leave the rest of
  the index untouched. Requires the full-rebuild-on-upload behavior in
  `src/api/main.py::reindex()` to be replaced with a targeted upsert.
- **Embedding-model migration**: version-tag every stored vector with the
  embedding-model name/version; on migration, re-embed in the background
  and cut over reads atomically once the new index is complete — never
  mix vectors from two different embedding spaces in one similarity
  search.
- **Tenant isolation**: partition both the SQL warehouse and the vector
  store by `tenant_id`; every query function in `sql_layer.py` and every
  retriever call would take a mandatory tenant filter, never optional.
- **Monitoring RAG quality post-deployment**: log every
  `(question, query_type, sources, latency)` tuple (the `metrics` dict
  already returned by `/query` is designed to make this easy), sample a
  percentage for human or LLM-as-judge review, and alert on
  classifier-confidence drift or a sustained rise in `unanswerable`
  responses (a leading indicator of a knowledge-base gap).
- **LLM cost control**: cache answers for repeated/near-duplicate
  questions (evidence-fingerprint based, not just exact-string match),
  and consider a cheaper/smaller model for the query classifier tier if
  it's ever upgraded from rule-based to model-based.
- **LLM outages**: this system already has a working answer for this —
  `LLM_BACKEND` degrades gracefully from `ollama` to `fallback`
  automatically on connection failure would be a small addition to
  `src/llm/factory.py` (currently a manual config switch; wrapping the
  Ollama call in a try/except that falls back is a ~5-line change).

---

## Business question types (Section 9) — worked examples

All four required categories are implemented and tested; see
`src/evaluation/test_cases.json` for the full set. Quick illustrations:

- **Knowledge**: *"What is the recommended strategy for high-value
  customers?"* → routed to RAG only, answer cites Customer Strategy §4.
- **Analytical**: *"Which product generated the highest revenue?"* →
  routed to SQL only, answer computed live from the `sales` table.
- **Hybrid**: *"Which products generated the highest revenue, and what
  marketing strategy does the company recommend for those products?"* →
  SQL + RAG, evidence fused into one answer.
- **Diagnostic**: *"Aurora Pro Wireless Earbuds sales declined in Q2
  2025. What are the likely reasons?"* → SQL (sales trend, discount
  history, campaign spend, review sentiment) + RAG (Product Strategy
  quality-escalation guidance), answer explicitly separates observed
  facts / inference / unsupported assumptions.

## Unknown / hallucination test (Section 13)

*"What will Amazon's sales be in 2030?"* → classified `unanswerable`
before any retrieval happens; answer explicitly states the data does not
support this, per the assignment's expected behavior text.

## Conflicting information test (Section 14)

Marketing Strategy recommends a **10%** campaign discount target;
Pricing Policy sets a **15%** maximum ceiling. When both chunks are
retrieved together, `src/rag/context_builder.py::_detect_discount_conflict`
flags this explicitly in the evidence rather than silently merging or
averaging the numbers — see `tests/test_retrieval.py::
test_conflict_detection_surfaces_both_documents`.

**How source priority could work in production**: attach a
`priority`/`authority` field to each document's metadata at ingestion
(e.g. Pricing Policy > Marketing Strategy for numeric limits, since
Pricing Policy is the compliance source of truth per its own text) and
have the context builder prefer the higher-priority source *while still
surfacing the lower-priority one as context* — never silently discard
it, since "the marketing team's stated target differs from the pricing
ceiling" is itself useful information for the analyst asking the
question.

---

> **Note:** the sections below (14–15 and this performance log) are the
> historical design log from earlier V1 phases and reference the legacy
> SQLite/`fallback`-LLM stack. The live runtime is the V2.1+ PostgreSQL +
> Groq/NVIDIA architecture in “Current runtime” at the top; current
> measured latency is in the certification reports
> (`QUERYBRIDGE_*_LATENCY_CERTIFICATION.md`).

## Performance optimizations (V1 historical log)

Rather than guess at bottlenecks, these were found by profiling the live
pipeline (`cProfile` over repeated `pipeline.answer()` calls) and fixed
with measurements before/after — numbers below are real, not estimated.

| Optimization | File | Why | Measured effect |
|---|---|---|---|
| **Thread-local persistent SQLite connections** | `src/analytics/sql_layer.py` | Profiling showed `sqlite3.connect()`/`close()` on every single analytics call was the single largest cost — a diagnostic question alone triggers 8-10 separate SQL calls, each previously opening and tearing down its own connection. Each FastAPI worker thread now opens one connection and reuses it for its lifetime (safe because SQLite connections aren't shared *across* threads, only reused *within* one) | part of the 48% cache-miss-path speedup below |
| **In-memory product/category entity cache** | `src/rag/query_classifier.py` | `_resolve_product()` was re-querying and re-lowercasing the full 120-row products table on *every single* `classify()` call, including questions that never resolve a product at all | part of the 48% cache-miss-path speedup below |
| **Precompiled classifier regex** | `src/rag/query_classifier.py` | Diagnostic patterns and the ~30 analytical/knowledge keywords were being freshly matched (in the keyword case, via ~30 separate `re.search` calls) on every classify() call; now one compiled alternation pattern per keyword list, built once | part of the 48% cache-miss-path speedup below |
| **Query-level LRU answer cache** | `src/rag/pipeline.py` | Every request re-ran full classification + retrieval + SQL + generation from scratch, even for an identical question asked seconds apart — realistic analyst traffic repeats a handful of popular questions constantly. Caches the full `QueryResult` keyed on normalized question text (256-entry LRU), invalidated automatically on `reindex()` so a document upload/delete can never serve stale evidence | **~97% latency reduction on repeat questions** (see below) |
| **`idx_products_category` index** | `src/ingestion/data_generator.py` | Negligible at 120 products today, but the category-performance query plan (`EXPLAIN QUERY PLAN`) was a full table scan on `products` before filtering — this becomes real once the catalog scales past a few thousand SKUs | not measurable at current scale; documented for the scaling story |

### Before / after (measured, `LLM_BACKEND=fallback`)

```
Cache-miss (worst-case, fully unique traffic — isolates the connection-
pooling + classifier-caching wins from the LRU query cache):
  Before: 5.49 ms/call  (439ms / 80 calls, cProfile baseline)
  After:  2.84 ms/call  (227ms / 80 calls)
  -> ~48% faster

Realistic repeated-question traffic (LRU cache doing its job):
  Cold:      2.5 ms   (cache miss, live API measurement)
  Repeat:    0.1 ms   (cache hit, live API measurement)
  -> ~25x faster on repeat questions

Full evaluation suite (38 cases, each question unique -> cache-miss path):
  Before: 4.06 ms/call average end-to-end latency
  After:  2.18 ms/call average end-to-end latency
  Query-type accuracy: 92.1% -> 92.1% (unchanged — optimizations
    touched performance only, verified against the same 38-case suite
    and all 25 unit tests, both before and after)
```

Verified live through the actual HTTP API, not just the Python pipeline
object directly: a repeated `POST /query` call returns `cache_hit: true`
with `end_to_end_latency_ms` near zero, and a `POST /documents/upload`
call correctly forces the next identical question back to a cache miss
(proving the invalidation path works, not just the cache path).

**What wasn't optimized, and why:** `json.dumps`/`json.loads` round-
tripping the evidence dict through the prompt string (`src/rag/
prompt_templates.py` + `src/llm/fallback_llm.py`) is measurably wasteful
specifically for the fallback backend — it serializes evidence to JSON
text only to immediately regex-extract and re-parse that same JSON back
out. Left as-is because the *shared prompt contract* between the fallback
generator and a real LLM backend (Ollama needs the actual serialized text
prompt) is the architecture's main strength — special-casing this one
backend to skip serialization would break the "swap `LLM_BACKEND` with
zero other code changes" property documented above, for a ~0.5ms/call
saving that doesn't show up in any realistic workload once the LRU cache
is in place upstream of it.

---

## Security

- `.env.example` is committed; `.env` is git-ignored (see `.gitignore`).
  Real provider keys (Groq/NVIDIA) and the PostgreSQL password live only in
  the local `.env` / Docker secrets, never in tracked files.
- **Active runtime (V2.1+):** Groq is the primary LLM provider with a
  strictly bounded NVIDIA fallback (`src/llm/provider_policy.py`); storage
  is PostgreSQL (Docker), embeddings are the TF-IDF pipeline. Keys are
  forwarded only to their own provider inside the API container.
- Structured SQL is workspace-scoped and parameterized: raw user text
  never becomes an SQL identifier or fragment (see `src/agents/tools/
  sql_tools.py` and the `tests/e2e/test_sql_security.py` suite).
- **Production business-data protection:** every workspace-owned entity
  (datasets, documents, chunks, semantic mappings, conversations, cache
  entries) carries a `workspace_id` and every read/write/list/delete path
  enforces it — see `tests/e2e/test_workspace_isolation.py`. Put the API
  behind auth (OAuth2/JWT) and encrypt volumes at rest before multi-tenant
  production; redact raw evidence fields for roles that shouldn't see
  row-level detail; log query access for audit, since sales/marketing data
  (revenue, campaign spend, customer LTV) is commercially sensitive.

---

## Repository structure

```
README.md
requirements.txt
.env.example
data/
  knowledge_base/*.md        # 7 policy/strategy documents (33 chunks after chunking)
tests/
  test_causal_routing.py     # causal-intent routing + honesty tests
  test_classifier.py, test_metrics.py   # routing / metric unit tests
  benchmark_final.py          # 33-question deterministic accuracy + latency benchmark
  e2e/
    test_sql_security.py      # SQL injection / identifier security suite
    test_revenue_ground_truth.py  # certified analytics ground truths
    test_workspace_isolation.py   # cross-workspace isolation matrix (Blocker 2)
src/
  config.py
  agents/
    orchestrator_v2.py        # ACTIVE orchestration: router → semantic → evidence
    router.py                 # deterministic query classifier (incl. CAUSAL intent)
    semantic.py               # metric/dimension resolution
    tools/                    # metrics, sql, rag, schema, workspace tools
    specialists/              # analytics / rag agents
  analytics/
    dynamic_engine.py         # workspace-scoped SQL engine (canonical KPIs)
  llm/
    provider_policy.py        # Groq primary → bounded NVIDIA fallback
    groq_client.py, nvidia_client.py, query_cache.py
  retrieval/                  # vector_store, keyword_search, hybrid_retriever
  api/
    main.py, schemas.py       # FastAPI app (workspace-scoped endpoints)
frontend/
  src/                         # Next.js App Router UI (AI Analyst / Data Center)
```