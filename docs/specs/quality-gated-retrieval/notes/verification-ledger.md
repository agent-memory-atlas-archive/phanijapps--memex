# Quality-gated retrieval verification ledger

## 2026-09-18 — T4 canonical selection

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
retrieval unchanged, as required by T4's no-winner path. T5 and T6 remain
blocked on a candidate that satisfies the approved hard-query MRR threshold.

Repository verification after the bounded-evaluation change:

- Ruff check: pass.
- Ruff format check: pass, 106 files.
- Mypy: pass, 92 source files.
- Pytest: 487 passed, 1 skipped in 139.64 seconds; coverage 90.17%.
- MkDocs strict build: pass in 0.53 seconds.
