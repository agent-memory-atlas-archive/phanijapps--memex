# Plan: Index-derived query term filtering

- **Spec:** [`spec.md`](spec.md)
- **Status:** Done <!-- executed and measured; candidate rejected -->
- **Repository anchors:** `src/memex/infrastructure/search/index_manager.py`
  (`_SCHEMA`, `SCHEMA_VERSION`, `drop_for_rebuild`) and
  `src/memex/infrastructure/search/bm25_retriever.py` (`_semantic_tokens`,
  `production_ranker_metadata`) as the production seams;
  `tests/unit/test_bm25_retriever.py` trace-callback tests as the construction
  shape; `eval/selection.py::_run_baseline_pair` and
  `eval/comparison.py::tokens_per_correct_hard_query` as the gate; named
  deviation: the paired evaluator's baseline is the legacy `OR` ranker, so the
  shipped-ranker comparison is [`notes/grid.py`](notes/grid.py), which drives
  `eval.selection._run_candidate_pair` and `_quality_metrics` on one store from
  each source tree.

## Approach

Two owned files change. `IndexManager` gains `wiki_vocab`, an `fts5vocab`
`row` table over `wiki_fts`, created in `_SCHEMA` and dropped before `wiki_fts`
on rebuild; `SCHEMA_VERSION` moves to `7`. `BM25Retriever` replaces the phrase
strips and stop list with one predicate over per-token document frequency.
FTS5 exposes no tokenizer function, so each connection owns a temporary
one-row helper FTS table with the index tokenizer and an `instance`-mode
vocabulary over it: inserting the joined tokens and reading
`term ORDER BY offset` yields one Porter stem per token position, and a single
`SELECT term, doc FROM wiki_vocab WHERE term IN (…)` returns the counts. The
filter keeps tokens with `0 < df <= MAX_TERM_DOCUMENT_RATIO * N`, falls back to
every indexed token, then to the first token. The threshold comes from the
corpus vocabulary, then a grid over ratio and explicit stop list picks the best
candidate, and the promotion gates decide. The riskiest part is that a
document-frequency filter cannot see benchmark phrase words that occur at
content frequency; the measurement confirmed that risk.

## Constraints

- ADR-0001: SQLite stays disposable; `wiki_vocab` is a view over the FTS index
  and rebuilds with it.
- ADR-0002: the CLI, MCP, and facade share `BM25Retriever`; no adapter-level
  filter.
- `quality-gated-retrieval` Boundaries: paired stores, same seed and manifest,
  safe query boundary preserved, gates conjunctive, isolated `MEMEX_DATA_DIR`.

## Construction tests

**Integration tests:** `uv run pytest tests/integration/test_agent_workflow_eval.py -q --no-cov -k real_workflow_recall`
(22/24 `human_focused` floor), `uv run python -m eval.run retrieval --realistic --size 1000 --seed 42 --top-k 10 --data-dir <empty>`,
`uv run python -m eval.run selection --size 1000 --seed 42 --top-k 10 --candidate semantic-and-fallback-fts5 --data-dir <empty> --evidence-dir <empty>`
with `MEMEX_DATA_DIR` pointing at a different empty directory (the selection
refuses a data dir inside a protected store).
**Paired shipped-versus-candidate measurement** (both trees are clean copies
of `71ff7d3`; the second has `notes/candidate.patch` applied; `<store>` is an
empty directory outside every Memex store and `MEMEX_DATA_DIR` points at a
separate empty guard directory):

```bash
git archive 71ff7d3 | tar -x -C <head>
git archive 71ff7d3 | tar -x -C <cand> && (cd <cand> && git init -q && git add -A && git commit -qm base && git apply docs/specs/idf-query-terms/notes/candidate.patch)
for tree in <head> <cand>; do
  (cd $tree && PYTHONPATH=$tree/src:$tree python docs/specs/idf-query-terms/notes/grid.py --root <store>/grid-$tree)
  (cd $tree && PYTHONPATH=$tree/src:$tree python -c 'from eval.agent_workflow import run_benchmark
for name, s in sorted(run_benchmark().strategies.items()):
    print(name, (s.task_complete, s.fact_recall, s.calls, s.rendered_tokens, s.inactive_hits, s.other_project_hits))')
done
```

`grid.py` counts `BM25Retriever._execute_ranked_query` calls minus queries to
report `OR` fallbacks. **Manual verification:** none.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Decision rationale (`spec.md`) | T4 | `notes/grid.py`, evaluator, and workflow output from two clean trees | numbers recorded in `spec.md` |
| Reproducible evidence (`notes/candidate.patch`, `notes/grid.py`) | T3, T4 | `git diff` of the candidate tree (retriever, index, three test files) and the grid script | 5 file diffs, no home paths; `git apply --check` passes on `71ff7d3` |

## Design (LLD)

### Design decisions

- Stem via a temp helper FTS table plus `instance` vocabulary rather than a
  Python Porter port: one tokenizer, no drift. Rejected: `COUNT(*) … MATCH`
  per token, which stems correctly but leaves `wiki_vocab` unused.
- Drop absent tokens (`df = 0`) as well as frequent ones: an absent token can
  match nothing, and keeping it only forces the `OR` fallback. Traces to
  AC-0004.
- Fallback order when everything drops: every indexed token, then the first
  token, so `MATCH` is never empty. Traces to AC-0005.

### Data & schema

`wiki_vocab(term, doc, cnt)` = `fts5vocab(wiki_fts, 'row')`. Dropped before
`wiki_fts` in both rebuild paths; created by `CREATE VIRTUAL TABLE IF NOT
EXISTS`, so a schema-6 store gains it on open with no data rebuild. Traces to
AC-0001, AC-0002.

### Failure, edge cases & resilience

Frequencies count every indexed row regardless of scope or validity, matching
`bm25()` statistics. A 1-page store puts every present token at ratio 1.0, so
the indexed-token fallback keeps the query whole. Traces to AC-0005.

## Tasks

### T1: `wiki_vocab` exists on fresh, rebuilt, and upgraded stores

**Depends on:** none
**Tests:** AC-0001, AC-0002 in `tests/unit/test_idf_query_terms.py`, including
a legacy `wiki_index` without `scope` beside a `wiki_fts`.
**Approach:** add the table to `_SCHEMA`, drop it in both rebuild scripts,
bump `SCHEMA_VERSION` (a stamp only; the table is created by
`CREATE VIRTUAL TABLE IF NOT EXISTS` on every open) and move the
`SCHEMA_VERSION` pin in `tests/unit/test_okf_frontmatter.py` to `"7"`.
**Done when:** the four schema tests and the pin pass. Result: passed.

### T2: Document frequency per stemmed query token

**Depends on:** T1
**Tests:** AC-0003 (`runs`/`running` → 2, absent → 0).
**Approach:** temp helper FTS table and `instance` vocabulary in
`BM25Retriever.__init__`; `_document_frequencies` returns one count per token.
**Done when:** the stemming test passes. Result: passed.

### T3: Term filter replaces phrase strips and stop list

**Depends on:** T2
**Tests:** AC-0004, AC-0005, AC-0006, plus `tests/unit/test_bm25_retriever.py`,
whose two scaffolding tests become
`test_retrieve_deduplicates_tokens_before_the_strict_match` and
`test_retrieve_keeps_every_indexed_token_on_a_single_page_store`, the rules
they exercise under the new filter.
**Approach:** `_semantic_tokens` keeps `0 < df <= ratio * N`, with the two
fallbacks; delete `_SEMANTIC_SCAFFOLDING_PHRASES`, `_phrase_indexes`,
`_how_does_handle_indexes`, `_why_is_showing_indexes`,
`_drop_semantic_scaffolding`, `_QUERY_STOP_WORDS`; no replacement stop list;
rewrite `production_ranker_metadata`.
**Done when:** in the candidate tree,
`ruff format --check` and `ruff check` over
`src/memex/infrastructure/search/bm25_retriever.py src/memex/infrastructure/search/index_manager.py tests/unit/test_idf_query_terms.py tests/unit/test_bm25_retriever.py tests/unit/test_okf_frontmatter.py`,
`mypy` over the same files, and
`pytest tests/unit/test_idf_query_terms.py tests/unit/test_bm25_retriever.py tests/unit/test_index_manager.py tests/unit/test_okf_frontmatter.py -q --no-cov`
are green. Result (2026-09-23, clean `71ff7d3` plus the patch): 5 files
already formatted, all checks passed, mypy no issues in 4 source files,
79 passed in 5.70s.

### T4: Threshold from data, then promotion gates

**Depends on:** T3
**Tests:** AC-0007 through AC-0010.
**Approach:** dump `wiki_vocab` for the 1,000-page seed-42 store; sweep ratio
`{0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.1}` × stop list `{none, an+does,
an+does+of+from+to+we}` for recall and fallbacks; then measure the chosen
candidate against the shipped ranker from two clean `71ff7d3` copies with the
commands under Construction tests (`notes/grid.py` and the workflow benchmark
in each tree, `eval.run retrieval` in each tree, `eval.run selection` in the
candidate tree); promote only if every gate holds, otherwise keep the working
tree's owned sources at `71ff7d3` and keep the patch.
**Done when:** every gate recorded in `spec.md`. Result: AC-0007 passed
(tokens 1069.14 vs 1675.80, paired p99 ratio 0.514); AC-0008 failed (929.67 vs
480.71 tokens per correct hard query, +93.4%); AC-0009 failed (p99 2.23 ms vs
0.84 ms, 265%); AC-0010 failed (`human_focused` 21/24 vs 22/24); working-tree
sources unchanged from `71ff7d3`.

## Rollout

Pure-logic change with no flag, infrastructure, or sequencing. Not shipped.

## Risks

- The patch moves the `SCHEMA_VERSION` pin in
  `tests/unit/test_okf_frontmatter.py`, a file outside this slice's owned set;
  it changes only inside the patch, never in the working tree.
- The paired evaluator has no shipped-ranker baseline, so the shipped
  comparison relies on `notes/grid.py`; it uses the same `eval.selection`
  metric functions and store, but writes no sanitized report.
- `notes/candidate.patch` applies cleanly to `71ff7d3` today and will drift as
  `bm25_retriever.py` and `index_manager.py` evolve.

## Changelog

- 2026-09-23: initial plan; built T1–T3, measured T4, rejected the candidate
  because tokens per correct hard query rose, p99 rose, and `human_focused`
  fell to 21/24 versus the shipped ranker.
- 2026-09-23 (review fixes): re-measured from clean `71ff7d3` copies with
  `notes/grid.py` (+93.4% tokens, p99 265%); moved the patch to `notes/`,
  removed its empty stop-list constant, fixed its test formatting, added the
  legacy-schema test, rewrote the two stale retriever tests, and moved the
  `SCHEMA_VERSION` pin inside the patch.
