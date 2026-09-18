# Quality-gated retrieval verification ledger

## 2026-09-18 — T4 pre-repair selection evidence

Command:

```bash
uv run python -m eval.run selection --promotion \
  --evidence-dir /tmp/memex-t4-promotion-oegQXl
```

The run used source revision
`64718b57905ab1d104557a6f6e86c287ffffb9c0` with `git_dirty=false`, seed 42,
`top_k=10`, 10,000 generated memories, and all 20,800 generated queries. The
retained PR-only report was
`/tmp/memex-t4-promotion-oegQXl/selection-promotion.json`.

This entry is historical pre-repair evidence. It predates the amended
AC-0037/AC-0038 workload-label and multi-workload gates, so its synthetic
scores are not comparable promotion evidence for the repaired benchmark series.
Only post-repair sections in this ledger are comparable promotion evidence.

The `weighted-lexical-rrf` candidate completed the 10K run:

- Hard-query Recall@10: `0.3198275862` baseline, `0.4155172414` candidate;
  delta `+0.0956896552` (pass).
- Hard-query MRR: `0.2054122879` baseline, `0.2270516557` candidate; delta
  `+0.0216393678` (fail; required `+0.05`).
- Recall@10: candidate improved overall, easy, and medium buckets (pass).
- Rendered tokens per correct hard query: `4655.3445` baseline, `2765.8510`
  candidate; ratio `0.5941` (pass; maximum `0.80`).
- 10K p99: `41.8557 ms` baseline, `36.1791 ms` candidate; paired ratio
  `0.8644` (pass).

The optional `rgapi-0.1.22` candidate completed 37 queries before its bounded
evaluation budget expired. It was recorded as incomplete and failed closed.

No candidate cleared the complete 10K eligibility gate. The evaluator
therefore did not run the 100K phase, selected no candidate, and left production
retrieval unchanged, as required by T4's no-winner path. At that time, T5 and
T6 were blocked on a candidate that satisfied the then-approved hard-query MRR
threshold.

Repository verification after the bounded-evaluation change:

- Ruff check: pass.
- Ruff format check: pass, 106 files.
- Mypy: pass, 92 source files.
- Pytest: 487 passed, 1 skipped in 139.64 seconds; coverage 90.17%.
- MkDocs strict build: pass in 0.53 seconds.

## 2026-09-18 — Post-review hardening

Commit `e0d8706` added protected-store rejection for the default and configured
Memex roots, a retained-report prohibited-content canary, per-scale incomplete
status reporting, bound ranker metadata to the executed FTS5 weights, and added
real weighted-ranking and query-backoff fixtures. Adversarial, quality, and
security reviewers returned clean verdicts.

Verification on that committed tree:

- Ruff check: pass.
- Ruff format check: pass, 106 files.
- Mypy: pass, 92 source files.
- Pytest: 494 passed, 1 skipped in 141.14 seconds; coverage 90.17%.
- MkDocs strict build: pass in 0.54 seconds.

## 2026-09-18 — T6 earlier clean promotion

Command:

```bash
uv run python -m eval.run selection --promotion \
  --candidate semantic-and-fallback-fts5 \
  --workload realistic \
  --workload gutenberg \
  --workload salesforce \
  --evidence-dir /tmp/memex-promotion-clean.H9F8Xy/evidence
```

The run used source revision
`7af1bb14a857e05f8e5322840c7e6dcb335a7e5f` with `git_dirty=false`, seed 42,
`top_k=10`, 10,005 generated 10K memories, 100,005 generated 100K memories,
and 388 sampled queries. The retained PR-only report was
`/tmp/memex-promotion-clean.H9F8Xy/evidence/selection-promotion.json`.

The selected winner was `semantic-and-fallback-fts5`. It passed promotion,
was promotion-eligible, and recorded no failures.

This entry is historical earlier clean evidence. It was superseded as the
current promotion evidence by the definitive clean production-path report
below, after review hardening and final rerun on source revision `226bad7`.

- Overall Recall@10/MRR/nDCG@10: `0.9819587629`, `0.9819587629`,
  `0.9323851353`.
- Hard-query Recall@10/MRR: baseline `0.9809523810` / `0.9738095238`,
  candidate `0.9809523810` / `0.9809523810`.
- Rendered tokens per correct hard query: baseline `1525.6407766990`,
  threshold `1220.5126213592`, candidate `935.1844660194`.
- 10K p99: baseline `42.6426850026 ms`, candidate `12.3535629828 ms`,
  paired ratio `0.2896994639`.
- 100K p99: baseline `363.3644640213 ms`, candidate `73.0164520210 ms`,
  paired ratio `0.2009454948`.
- Workload gates: repaired realistic, Gutenberg, and Salesforce each passed
  Recall@10, MRR, nDCG@10, hard Recall@10, hard MRR, and family Recall@10.

## 2026-09-18 — Definitive clean production-path promotion

Command:

```bash
uv run python -m eval.run selection --promotion \
  --candidate semantic-and-fallback-fts5 \
  --workload realistic \
  --workload gutenberg \
  --workload salesforce \
  --evidence-dir /tmp/memex-final-evidence-226bad7
```

The definitive retained PR-only report is
`/tmp/memex-final-evidence-226bad7/selection-promotion.json`, with SHA-256
`8a810445ff9587c0a8c5e346461dc9ee0f7982f83ae4619cf2e5cd52ae46e705`.
The run used source revision `226bad7ab7a6b05c12d32a8a04afb6a33f5a2473` with
`git_dirty=false`, seed 42, `top_k=10`, 10,005 generated 10K memories,
100,005 generated 100K memories, and 389 sampled queries.

The selected winner was `semantic-and-fallback-fts5`. It passed promotion,
was promotion-eligible, and recorded no failures. The evaluator executed the
production `BM25Retriever` no-access path and recorded the candidate ranker
query caps: `max_query_bytes=1024` and `max_query_tokens=64`.

- Overall Recall@10/MRR/nDCG@10: `0.9819587629`, `0.9819587629`,
  `0.9323851353`.
- Hard-query Recall@10/MRR: baseline `0.9809523810` / `0.9738095238`,
  candidate `0.9809523810` / `0.9809523810`.
- Rendered tokens per correct hard query: baseline `1564.7669902913`,
  threshold `1251.8135922330`, candidate `966.4854368932`; reduction
  `38.23%`.
- 10K p99: baseline `48.0492539937 ms`, candidate `10.1166139939 ms`;
  reduction `78.95%`.
- 100K p99: baseline `400.7201319910 ms`, candidate `74.3253649562 ms`;
  reduction `81.45%`.
- Workload gates: repaired realistic, Gutenberg, and Salesforce each passed
  Recall@10, MRR, nDCG@10, hard Recall@10, hard MRR, and family Recall@10.
- Negative-control diagnostics: one Salesforce hard negative-control query,
  zero non-empty results, and zero non-empty result rate. The retained report
  omits raw query text.
- Difficulty metrics were retained in the report for overall and each named
  workload, without raw query text or user-specific paths.

## 2026-09-18 — T7 production promotion smoke

Command:

```bash
MEMEX_DATA_DIR=/tmp/memex-winner-smoke uv run memex recall "atlas risk integration"
```

The isolated store contained the winner-discriminating fixture used by
`tests/integration/test_recall_winner.py`. The command exited zero, reported
`search_engine="semantic-and-fallback-fts5"`, and returned
`atlas-risk-integration` as the first slug.

## 2026-09-18 — T8 durable documentation closeout

Durable documentation now describes the shipped `semantic-and-fallback-fts5`
ranker, the retained promotion evidence, the runtime dependency disposition,
and the retrieval-evaluation security controls required by AC-0039. The
content-pin test covers offline Salesforce facts, maintainer-supplied local
Project Gutenberg import, fixture-output confinement, compressed and expanded
parser limits, no-network execution, fail-closed integrity errors, and retained
report redaction.

Verification:

- Focused docs content test with normal coverage disabled:
  `uv run pytest --no-cov tests/unit/test_docs_retrieval_controls.py` — pass,
  1 test in 0.03 seconds. The same focused test also passed under the normal
  coverage configuration, but that one-test invocation failed the repository
  coverage threshold because no package module was imported.
- MkDocs strict build: pass in 0.54 seconds after this ledger entry.
- Ruff check: pass.
- Ruff format check: pass, 110 files.
- Mypy: pass, 95 source files.
- Pytest: 533 passed, 1 skipped in 137.70 seconds; coverage 90.28%.

Acceptance-correction verification after adding the T6 clean-promotion entry,
correcting the GitPages SQL join, removing false duplicate-before-limit prose,
and narrowing the changelog claim:

- Focused docs content test:
  `uv run pytest --no-cov tests/unit/test_docs_retrieval_controls.py` — pass,
  1 test in 0.02 seconds.
- MkDocs strict build: pass in 0.54 seconds.
- Ruff check: pass.
- Ruff format check: pass, 110 files.

## 2026-09-18 — Final confined-harness verification

The final clean promotion evidence at source revision `226bad7` includes the
fixture-slug and page-write confinement fix. The lifecycle-only closeout was
then verified against the complete repository state:

- Base-environment Pytest: 554 passed, 3 optional tests skipped in 138.47
  seconds; coverage 90.35%.
- Pinned optional integration:
  `uv run --locked --extra eval-rgapi pytest --no-cov -q tests/integration/test_rgapi_candidate.py`
  — 14 passed in 0.91 seconds with `rgapi==0.1.22` installed. The real
  structured-row test observed zero `subprocess.Popen` calls, and the real
  symlink canary returned no outside-root result.
- Ruff check: pass.
- Ruff format check: pass, 110 files.
- Mypy: pass, 95 source files.
- MkDocs strict build: pass in 0.52 seconds.
- Spec-status lint: pass.
- Traceability lint: pass with two pre-existing informational structural
  orphans (`memex-viz` and `v1-guardrails`).

Every AC-0001 through AC-0039 condition is covered by the retained promotion
report, the committed evaluator and production-path tests, the isolated CLI
smoke, or the durable documentation checks named above. The spec is shipped
and the plan is done; no delivery-only fact is the sole owner of a lasting
product, architecture, security, or research promise.
