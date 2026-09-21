# Description and navigation recall evaluation

**Date:** 2026-09-21
**Question:** Did the agentic-frontmatter-search feature (v0.5.0) improve
recall and search capability, and to what grade?

## Method

Three evaluations on commit `4ded1a3` (branch `feat/agentic-frontmatter-search`,
clean tree, ranker `semantic-and-fallback-fts5`):

1. **Known-item retrieval** — the packaged harness
   (`uv run python -m eval.run retrieval --realistic --size 1000 --top-k 10`),
   seed 42, fresh store. The synthetic corpus writes pages without
   descriptions, so this run measures the no-regression contract (AC-0007).
2. **Paired description run** — same corpus and queries; every page then
   gains a first-sentence description, `rebuild-index`, and the identical
   query set re-runs. Metrics before/after come from one deterministic
   script (seed 42 both sides).
3. **Goal-shaped task benchmark** — the committed agent-workflow fixture
   (123 cards, 24 tasks, queries authored 2026-09-20, before descriptions
   existed) run twice: baseline, then with hand-written saver-style signpost
   descriptions on all 111 active cards (fresh wording derived from each
   card's own content; distractors carry honest not-current-evidence
   signposts). A control run with body-copy descriptions isolates the
   vocabulary effect.

## Results

**Known-item (1,000 realistic pages, 2,080 queries).** Recall@1 98.99%,
recall@5 99.13%, recall@10 99.33%, MRR 0.9909, precision@5 68.85%,
avg latency 3.6 ms. Hard-query recall@10 98.4%. Under the rubric below
this is an **A** — and it was an A before this feature shipped: this run
reproduces the pinned baseline, confirming descriptions changed no existing
ranking (the explicit five-column weight vector holds slug/title/body/tags
contributions fixed).

**Paired descriptions.** Recall@1 98.99% → 99.28%, MRR 0.9909 → 0.9930,
recall@10 99.33% → 99.47%. One previously missed query recovered
("what is idempotency"); zero queries regressed. With body-derived
descriptions every top-hit snippet still sources from the body (body weight
2.0 dominates when text is shared), so the gain comes from the few queries
whose terms the description surfaced more sharply.

**Goal-shaped tasks (24 tasks, evidence = 3 pages each).**

| Strategy | Baseline tasks | Baseline fact recall | + saver descriptions |
| --- | --- | --- | --- |
| current injection (1 query) | 5/24 | 0.4375 | 4/24 · 0.4219 |
| broad goal query | 7/24 | 0.5469 | 6/24 · 0.5469 |
| human focused questions (3) | 12/24 | 0.7344 | 12/24 · **0.7500** |
| linked summary | 11/24 | 0.7031 | 11/24 · 0.7031 |

Control (body-copy descriptions): all four strategies unchanged — copying
body text into descriptions adds no vocabulary and moves nothing. Saver
signposts lift focused-question fact recall +1.6 points and leak no archived
or other-project cards, but task-completion counts stay within one task of
baseline (noise at n=24).

## Grade

Rubric, stated: known-item — A ≥ 0.95 recall@10 and MRR ≥ 0.90, B ≥ 0.85/0.75,
C ≥ 0.70/0.60, D ≥ 0.50/0.45, F below. Goal-shaped — A ≥ 90% tasks complete,
B ≥ 75%, C ≥ 55%, D ≥ 35%, F below (focused strategy is the operating mode).

- **Known-item retrieval: A** (before and after; mechanics were already
  promoted by the earlier ranker selection work).
- **Goal-shaped task search: C− focused / D broad** — and unchanged by this
  feature.

## Verdict

The descriptions-and-navigation feature did **not** move the letter grade of
goal-shaped task search, and the evidence says it was not designed to: the
description column carries a neutral weight, so pages without descriptions
and queries that match body vocabulary rank exactly as before (proven by the
pinned baseline reproduction). What it measurably adds is a discovery
surface: descriptions are searchable, returned on hits, listed in generated
directory indexes, and produce small strict gains (+0.3 points recall@1,
+1.6 points focused fact recall, one recovered query, zero regressions, no
distractor leakage) whenever the searcher's wording appears in a signpost.

The remaining gap between C/D task search and better grades is vocabulary
mismatch — synonyms and acronyms in queries that no field carries — which
this spec explicitly deferred to the aliases follow-on
(`docs/specs/agentic-frontmatter-search/spec.md`, Follow-ons). Raising the
goal-shaped grade needs that follow-on, or query vocabulary that savers
actually write into descriptions.

Evidence: `/tmp/eval-base.json` (packaged harness JSON with git state and
ranker metadata); paired and benchmark scripts run under `timeout` with
seed 42 and fresh isolated stores; reproducible via the commands in Method.

## Limits

The synthetic corpus's hard misses are duplication artifacts; the workflow
fixture is documentation-derived with curated cards, and the saver
descriptions in run 3 were written by one author after seeing strategy
summaries (not query texts); n=24 tasks cannot resolve single-task deltas.
Task-completion grades carry ±1 task of noise.
