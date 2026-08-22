# Evaluation

## Methodology

`src/evaluation/test_cases.json` defines 38 test cases (exceeds the
35-minimum in Section 15), grouped exactly per the assignment's required
buckets:

| Bucket | Count | Required minimum |
|---|---|---|
| Knowledge questions | 10 | 10 |
| Analytical questions | 10 | 10 |
| Hybrid questions | 5 | 5 |
| Unanswerable questions | 5 | 5 |
| Ambiguous questions | 3 | 3 |
| Conflicting-information questions | 2 | 2 |
| Diagnostic questions (bonus, beyond the 35 minimum) | 3 | — |
| **Total** | **38** | 35 |

Each case defines `expected_query_type`, `expected_source`, and
`expected_characteristics` (qualitative — used for manual answer review,
not automated scoring, since scoring free-text answer *quality*
automatically would need either a second LLM-as-judge call or hand
-labeled reference answers, both out of scope for "a simple evaluation
framework is sufficient").

`src/evaluation/eval_runner.py` runs every case through the live pipeline
and computes:

- **Query-type accuracy** — did the classifier route to the expected
  type? (For 3 intentionally fuzzy "ambiguous" cases, multiple types are
  accepted, e.g. `ambiguous_or_knowledge`.)
- **Retrieval recall proxy** — did the returned sources include the
  expected document(s)/table(s)? Not a true recall@K over a labeled
  relevance set (we don't have human relevance judgments for this
  synthetic corpus), but a reasonable automatic proxy given the corpus.
- **System latency** — retrieval, generation, and end-to-end, per call and
  aggregated (mean, p95).

Run it yourself: `PYTHONPATH=. python3 src/evaluation/eval_runner.py`
(writes `src/evaluation/eval_results.json` with full per-case detail).

## Results (fallback LLM backend, TF-IDF embeddings — this repo's default config)

```
Total cases:              38
Query-type accuracy:      92.1%  (35/38)
Retrieval recall proxy:   100%   (38/38)
Avg end-to-end latency:   4.1 ms
p95 end-to-end latency:   10.8 ms
```

By bucket:

| Bucket | Type accuracy | Retrieval recall |
|---|---|---|
| Knowledge | 80% | 100% |
| Analytical | 100% | 100% |
| Hybrid | 100% | 100% |
| Diagnostic | 100% | 100% |
| Unanswerable | 100% | 100% |
| Ambiguous | 67% | 100% |
| Conflicting information | 100% | 100% |

Latency is trivial here because the fallback backend does no neural
inference — this number will *not* hold with `LLM_BACKEND=ollama`, where
generation latency will dominate (expect 2-15s per answer on a 7B model,
depending on hardware — see README "Limitations").

## Failure analysis (3 of 38 cases)

Documenting these honestly rather than hand-picking a test set that
happens to pass — a rule-based classifier has known, explainable failure
modes:

1. **K5 — "What is the minimum acceptable ROAS for conversion campaigns?"**
   classified `analytical` instead of `knowledge`. The literal keyword
   "ROAS" is a strong analytical signal (it's also a computed metric over
   real campaign data), but this specific question is asking what the
   *policy document* says the threshold should be, not what the *actual*
   campaign ROAS is. A keyword-based classifier structurally cannot
   distinguish "what is ROAS" (analytical) from "what should ROAS be per
   policy" (knowledge) without deeper parsing — this is the single
   clearest argument in the whole assignment for why query routing is
   listed as a 15%-weighted evaluation area rather than a solved problem.

2. **K8 — "What is the top category priority for FY2025-2026?"**
   classified `hybrid` instead of `knowledge`. "Top" is an analytical
   keyword (correctly, for "top products by revenue"-style questions) and
   "priority" is a knowledge keyword; both fire here, producing a hybrid
   route. The hybrid answer is not *wrong* (it correctly retrieves the
   Product Strategy category-priority section), it's just broader than
   strictly necessary — arguably a defensible outcome, but scored as a
   miss against the test case's strict expectation.

3. **AM2 — "How is the product doing?"** classified `analytical`. This
   case is genuinely ambiguous by design (no product is named) and the
   test case itself accepts either `ambiguous` or `knowledge` as correct.
   The classifier's vague-question fallback heuristic (`"doing"` → default
   to a general analytical overview) produces a third, also-defensible
   answer that the test's acceptance list didn't anticipate. This is
   arguably a test-case specification gap as much as a system gap.

**Common thread:** every failure is a keyword-overlap case where a
single word plausibly belongs to more than one category. This is the
expected failure mode of a transparent, rule-based classifier and is the
main thing that would change first in a production iteration — either a
small trained classifier (with the current rule-based version kept as a
fallback / sanity check) or a two-stage classifier that asks "does this
question want a value that exists as a column in the database, or a
value that exists as prose in a document?" as a more targeted signal than
raw keyword overlap.

## Generation faithfulness (groundedness)

With `LLM_BACKEND=fallback`, faithfulness is enforced *by construction*:
the template generator can only emit values it reads directly out of the
evidence JSON (see `src/llm/fallback_llm.py`), so hallucination is
structurally impossible in this configuration — verified by
`test_unanswerable_question_does_not_fabricate` in
`tests/test_retrieval.py`.

With `LLM_BACKEND=ollama` (real model), faithfulness is *not* structurally
guaranteed and would need actual measurement — e.g. checking that every
number in the generated answer appears somewhere in the evidence JSON
(a cheap automatable check), or periodic LLM-as-judge spot review. This
is flagged in README "Failure cases" as the top priority for hardening
before a production launch on a real LLM backend.
