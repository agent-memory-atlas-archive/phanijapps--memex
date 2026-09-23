# Spec: Index-derived query term filtering

- **Status:** Archived (rejected 2026-09-23 — every gate versus the shipped ranker failed; see Measured result)
- **Owner:** Memex maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`ADR-0001`](../../adr/0001-use-markdown-pages-as-memory-source-of-truth.md), [`ADR-0002`](../../adr/0002-use-layered-package-and-shared-adapter-contracts.md), [`quality-gated-retrieval`](../quality-gated-retrieval/spec.md) promotion gates
- **Brief:** none
- **Discovery:** none
- **Contract:** none — `Memex.recall`, `RecallResult`, and `RecallHit` are unchanged
- **Shape:** service

> **Spec contract:** Boundaries, Testing Strategy, and Acceptance Criteria are
> completion gates. The plan describes construction. The candidate was built,
> measured, and rejected; [`notes/candidate.patch`](notes/candidate.patch)
> holds the exact source and tests that produced every number below, and
> [`notes/grid.py`](notes/grid.py) is the paired shipped-versus-candidate
> measurement.

## Objective

Recall drops query words that cannot narrow a search because the index itself
says so: a word is scaffolding when it appears in more than a fixed share of
indexed pages, or in none of them. The five hand-written phrase strips
(`instead of`, `how does … handle`, `how many`, `why is … showing`,
`switch from`) and the fifteen-word stop list disappear from the production
ranker, so recall quality no longer depends on the phrasing of the benchmark
generator. The change ships only when it holds every promotion gate of
`quality-gated-retrieval` against both the legacy baseline and the shipped
ranker.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Decision rationale | A promoted retrieval change must be explainable; a rejected one must stay findable | this spec and `plan.md` | Memex maintainers | Corpus inspection, threshold grid, paired gate numbers | The rejection reason is reproducible from `notes/candidate.patch`, `notes/grid.py`, and the commands in `plan.md` T4 |
| Reproducible evidence | Promotion depends on paired measurement | `notes/candidate.patch` and `notes/grid.py` | Implementing contributor | Retriever, index, and test diff; one paired measurement script | `git apply` of the patch on a clean `71ff7d3` checkout passes the unit suite, and `grid.py` run in both trees reproduces the AC-0008 and AC-0009 figures |
| Release history | Only if the default ranker changes | `docs/product/changelog.md` | Memex maintainers | One user-visible entry | Not applicable: no shipped behavior changed |

## Boundaries

### Always do

- Measure the candidate and the shipped ranker on the same isolated
  `MEMEX_DATA_DIR`, the same seed-42 realistic corpus, the same query
  manifest, and the same `top_k`; never against the developer's `~/.memex`.
- Keep the safe query-token boundary (`[a-z0-9]+`, 1,024 bytes, 64 tokens)
  and run every document-frequency lookup with bound parameters.
- Keep at least one query token; a query never reaches FTS5 with an empty
  `MATCH`.
- Reject the candidate when any promotion gate fails, and restore the shipped
  ranker completely rather than leaving a partial change.

### Ask first

- Change the strict-AND-then-OR query strategy, the column weights, or the
  snippet size while measuring a term-filter change.
- Relax a `quality-gated-retrieval` gate or the 22/24 `human_focused` floor.

### Never do

- Never hand-code a phrase or word that exists only because the benchmark
  generator emits it.
- Never read document frequency from anything but the FTS5 index the
  `IndexManager` owns; no second corpus statistic, cache file, or model.
- Never log or return query text, page bodies, or store paths from the
  frequency lookup.

## Testing Strategy

- **Schema (AC-0001, AC-0002): TDD.** Unit tests open a fresh store, drop
  and rebuild, open a store whose `wiki_vocab` was removed, and open a legacy
  store whose `wiki_index` lacks `scope` beside a `wiki_fts`, asserting
  `wiki_vocab` exists each time.
- **Term filter (AC-0003, AC-0004, AC-0005, AC-0006): TDD.** Unit tests trace
  the FTS5 `MATCH` string to prove which tokens survive stemming, the ratio
  ceiling, the absent-token rule, and the never-drop-last rule.
- **Promotion (AC-0007, AC-0008, AC-0009, AC-0010): goal-based integration.**
  The offline evaluator (`eval.run retrieval` and `eval.run selection`, 1,000
  pages, seed 42, `top_k=10`), an in-process paired grid against the `HEAD`
  retriever on the identical store, and
  `tests/integration/test_agent_workflow_eval.py`.

## Acceptance Criteria

- [x] **AC-0001.** A fresh index contains an `fts5vocab` table `wiki_vocab`
      over `wiki_fts` in `row` mode, and `index_meta.schema_version` is `7`.
- [x] **AC-0002.** `wiki_vocab` exists after `drop_for_rebuild()`, after
      opening a store that lacks the table, and after `initialize()` replaces
      an incompatible legacy `wiki_index`; `needs_rebuild()` is false in the
      first two cases and true in the third. The `SCHEMA_VERSION` bump is a
      stamp only: `needs_rebuild()` reads column shape, and the table arrives
      through `CREATE VIRTUAL TABLE IF NOT EXISTS` on every open.
- [x] **AC-0003.** Document frequency for a query token equals the number of
      indexed pages containing any word with the same Porter stem
      (`runs`/`running` count together; an absent word counts zero).
- [x] **AC-0004.** A token present in more than `MAX_TERM_DOCUMENT_RATIO` of
      indexed pages, or in none, is absent from the strict `MATCH` string.
- [x] **AC-0005.** When every token would be dropped, every indexed token is
      kept; when no token is indexed, the first token is kept.
- [x] **AC-0006.** `production_ranker_metadata()` has no `removed_scaffolding`
      key and reports `term_filter`, `max_term_document_ratio`, the dropped-term
      rules, and the kept-when-all-dropped rule; the candidate carries no
      explicit stop list, because the data (below) gave none that helped.
- [x] **AC-0007.** Versus the legacy `OR` baseline on the 1,000-page seed-42
      paired selection, hard Recall@10 and hard MRR do not regress, overall,
      easy, and medium Recall@10 regress by at most 0.005, tokens per correct
      hard query are at most 80% of baseline, and p99 is at most 110% of
      baseline.
- [ ] **AC-0008.** Versus the shipped ranker on the identical store and query
      manifest, tokens per correct hard query are no higher.
      **Measured: 929.67 vs 480.71 (+93.4%). Failed.**
- [ ] **AC-0009.** Versus the shipped ranker on the identical store, p99 recall
      latency is at most 110%. **Measured: 2.23 ms vs 0.84 ms (265%). Failed.**
- [ ] **AC-0010.** `human_focused` in the agent workflow benchmark completes at
      least 22 of 24 tasks. **Measured: 21 of 24 (fact recall 0.953125) vs
      22 of 24 (0.96875) for the shipped ranker from a clean checkout of the
      same commit. Failed.**

## Measured result

All runs on 2026-09-23: realistic corpus, 1,000 pages, seed 42, `top_k=10`,
stores in an isolated temporary `MEMEX_DATA_DIR`. Source: two clean
`git archive` copies of `71ff7d3`, one plain (the shipped ranker) and one
with `notes/candidate.patch` applied, each first on `PYTHONPATH`; the exact
commands are in `plan.md`. Recall, fallback counts, and the workflow tuples are
identical to an earlier working-tree run; the token and latency figures
recorded here replace that run's, which used uncommitted renderer edits.

### Corpus vocabulary (N = 1,000 pages, 826 stems)

Share of pages containing the stem: `the` 0.980, `this` 0.800, `in` 0.750,
`for` 0.662, `was` 0.568, `is` 0.545, `a` 0.521, `use` 0.485, `at` 0.466,
then the first content stem `idempotent` 0.462. Below that ceiling sit the
function words `from` 0.396, `and` 0.365, `when` 0.320, `with` 0.262,
`we` 0.250, `to` 0.239, `of` 0.174, `an` 0.081, `does` 0.043. Zero pages
contain `how`, `why`, `what`, `did`, `do`, `many`, or `showing`. The phrase
words sit at content frequency: `instead` 0.050, `handle` 0.058,
`switch` 0.067, between `query` 0.046 and `polling` 0.054.

Coverage of the retired stop list by `MAX_TERM_DOCUMENT_RATIO = 0.5` plus the
absent-token rule: covered `a`, `the`, `in`, `is` (above the ceiling) and
`how`, `why`, `what`, `did`, `do` (absent); not covered `an`, `does`, `from`,
`of`, `to`, `we`. Of the retired phrases, `how many` and `why is … showing`
are covered because their words are absent; `how does … handle`,
`instead of`, and `switch from` are not, because `does`, `handle`, `instead`,
`of`, and `switch` are as frequent as content words.

### Paired shipped versus candidate (`notes/grid.py`, all 2,080 positive queries, one store per tree)

| Tree | R@10 all / easy / medium / hard | Hard MRR | Tokens per correct hard | p99 | OR fallbacks |
| --- | --- | --- | --- | --- | --- |
| Shipped (`71ff7d3`) | 0.9933 / 0.9921 / 1.0000 / 0.9845 | 0.9819 | 480.71 | 0.84 ms | 0 |
| Candidate (ratio 0.5, no stop list) | 0.9933 / 0.9921 / 1.0000 / 0.9845 | 0.9819 | 929.67 | 2.23 ms | 500 |

Tokens per correct hard query rose 93.4% and p99 to 265% of the shipped
value with recall unchanged: the 500 queries that now fall back to `OR` pack
more pages into the budget and run two FTS5 queries.

### Ratio and stop-list sweep (working tree, recall and fallbacks only)

The sweep that chose ratio 0.5 ran in the working tree, so its token and
latency values are not comparable to the table above and are not recorded;
its recall and fallback counts do not depend on the renderer.

| Candidate variant | R@10 all / easy / medium / hard | Hard MRR | OR fallbacks |
| --- | --- | --- | --- |
| Ratio 0.5, no stop list | 0.9933 / 0.9921 / 1.0000 / 0.9845 | 0.9819 | 500 |
| Ratio 0.3 or 0.4, no stop list | 0.9918 / 0.9921 / 1.0000 / 0.9793 | 0.9793 | 500 |
| Ratio 0.2, no stop list | 0.9644 / 0.9746 / 0.9471 / 0.9793 | 0.9739 | 500 |
| Ratio 0.6–1.1, no stop list | 0.9933 / 0.9921 / 1.0000 / 0.9845 | 0.9819 | 700–800 |
| Ratio 0.5, stop list `an`, `does` | 0.9764 / 0.9921 / 0.9598 / 0.9845 | 0.9819 | 389 |

Ratios 0.6–1.1 keep recall but add 200–300 fallbacks (about 30% more tokens
in that sweep); adding `of`, `from`, `to`, `we` to the stop list changed
nothing. The medium-recall loss with `does` stripped is the strict-AND trap:
`handle` (0.058) stays, some other page contains every kept token, so strict
AND returns wrong pages and never falls back.

Root cause of the token cost: 335 of 768 distinct positive queries keep a
token that the expected page lacks, and every one is a benchmark phrase word:
`instead of` 177, `handle` 91, `instead` 67. Document frequency cannot separate
them from content because the generator uses them at content frequency.

### Official evaluator, candidate versus legacy `OR` baseline (clean candidate tree, 375 sampled queries)

Hard Recall@10 0.94 vs 0.94; hard MRR 0.94 vs 0.94; Recall@10 overall 0.9787
vs 0.976, easy 0.984 vs 0.976, medium 1.0 vs 1.0; tokens per correct hard
query 1069.14 vs 1675.80 (threshold 1340.64, pass); p99 2.432 ms vs 4.734 ms
(ratio 0.514, pass). Every realistic workload floor passed. The absolute-p99
gate reports "missing p99 latency size" because the 10K and 100K sizes run only
in `--promotion` mode, and `promotion_eligible` is false
(`source_unreproducible`) because the candidate copy carries the patch
uncommitted. `eval.run retrieval`, shipped vs candidate: Recall@10 99.3% vs
99.3%, MRR 0.991 vs 0.979, Recall@1 99.0% vs 96.8%, medium MRR 1.000 vs 0.972,
p99 2.8 ms vs 4.2 ms.

### Agent workflow benchmark (`eval.agent_workflow.run_benchmark`, one run per clean tree)

| Strategy | Shipped | Candidate |
| --- | --- | --- |
| `current_injection` | 5, 0.515625, 24, 16322 | 5, 0.546875, 24, 16243 |
| `broad_query` | 17, 0.875, 24, 81684 | 17, 0.875, 24, 81147 |
| `human_focused` | **22**, 0.96875, 72, 59457 | **21**, 0.953125, 72, 62565 |
| `linked_summary` | 11, 0.703125, 24, 4749 | 11, 0.671875, 24, 4773 |

Tuple: tasks complete, fact recall, calls, rendered tokens (inactive and
other-project hits were 0 everywhere).

### Verdict

Rejected. AC-0008, AC-0009, and AC-0010 failed. The shipped ranker's token
advantage comes from stripping words that only the benchmark generator emits,
and the shipped `human_focused` 22/24 also depends on them. The working tree's
owned source files stay at `71ff7d3`; the candidate lives in
`notes/candidate.patch`.

## Follow-ons

- Memex maintainers: `docs/product/briefs/memory-retrieval-and-evidence.md` —
  a term filter that survives the benchmark needs either a generator whose
  scaffolding words are not also content words, or a ranking step that tolerates
  one unmatched query term (for example strict AND over all-but-one term before
  the OR fallback) so the token metric no longer rewards phrase strips.

## Assumptions

- Technical: `wiki_fts` uses `tokenize='porter unicode61'`, so vocabulary
  terms are Porter stems and query tokens must be stemmed the same way
  (source: `src/memex/infrastructure/search/index_manager.py`).
- Technical: SQLite 3.50.4 in the `uv` environment ships `fts5vocab`,
  `row` and `instance` modes, and `CREATE VIRTUAL TABLE temp.… USING fts5vocab(temp, …)`
  (source: probe run 2026-09-23).
- Technical: the paired selection compares the candidate with the legacy
  `OR` baseline, not the shipped ranker, so the shipped comparison is an
  in-process grid on the same store using `eval.comparison`
  (source: `eval/selection.py::_run_baseline_pair`).
- Process: `tests/unit/test_okf_frontmatter.py` pins `SCHEMA_VERSION`; the
  patch moves that pin to `"7"` so applying it yields a green unit suite
  (source: `tests/unit/test_okf_frontmatter.py`, `test_schema_version_is_seven`
  in the patch).
- Technical: tokens per correct hard query counts the text
  `context_injection.pack_to_budget` and `format_context_block` render, so the
  figure moves whenever that renderer changes; every number in this spec comes
  from a clean `71ff7d3` checkout, not from a working tree with uncommitted
  renderer edits (source: `eval/comparison.py::tokens_per_correct_hard_query`).
