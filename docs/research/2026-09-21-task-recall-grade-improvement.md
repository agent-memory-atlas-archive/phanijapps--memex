# Task recall grade improvement: signposts and a wider evidence pack

**Date:** 2026-09-21
**Question:** Can goal-shaped task recall move from C− (12/24) toward A while
staying lexical, local, and deterministic?

## Changes (owner-directed)

1. **Purpose-style descriptions.** Every write surface (MCP tool contract,
   CLI help, consolidation prompt, user guide) now teaches the same
   authoring rule: a description states WHEN the page is useful — the
   situation or question it answers, in a searcher's words — instead of
   summarizing the body. The workflow fixture's 111 active cards carry
   hand-written signposts of this style. Summary-style (body-copy)
   descriptions measurably add nothing; signposts do.
2. **Description BM25 weight 1.0 → 2.0.** A query that hits a purpose-written
   signpost is as strong a relevance signal as a body hit. Stores without
   descriptions are unaffected (the column is empty), pinned by the
   known-item suite.
3. **Task-recall evidence pack widened from 8 pages to 36** (per-question
   retrieval depth 9 → 12; `TaskRecallInput.max_hits` bound [1, 8] → [1, 36]).
   The 4,096-token context budget is unchanged and remains the real cost
   bound: the packed task context renders paths, titles, and snippets
   (~110 tokens per source), so a full 36-source pack stays near 2,600–3,600
   tokens. The former eight-page cap double-bounded cost below the token
   budget and starved multi-part tasks of distinct evidence.

## Measured result (committed benchmark, deterministic)

| Strategy | Before | After |
| --- | ---: | ---: |
| Human focused questions | 12/24 (50%) · 73.4% facts | **22/24 (91.7%) · 96.9% facts** |
| One broad query (same 36-page budget) | 7/24 · 54.7% | 17/24 · 87.5% |
| Current hook injection | 5/24 · 43.8% | 5/24 · 51.6% |

Ladder of attribution, each step measured alone on the same fixture:
baseline 12/24 → +purpose descriptions 13/24 → +description weight 2.0
14/24 (focused) and 8/24 (broad) → +36-page pack at depth 12: 22/24
focused, 17/24 broad. Every step's intermediate numbers are in the
2026-09-21 evaluation note and the amendment history of the task-evidence
baseline. Latency unchanged (same three SQL queries per task); zero
archived or other-project leakage at every step.

## Grade

With the prior note's rubric (A ≥ 90% task completion), goal-shaped task
recall moves **C− (50%) → A (91.7%)**. Known-item retrieval stays at its
prior A (99.3% recall@10, MRR 0.991, re-measured). **A+ (≥95%, 23/24) is
not honestly reachable**: the two remaining tasks fail because their
required evidence pages are addressed lexically only by OTHER tasks'
questions — a query-formulation gap, not a retrieval gap. Closing it would
need the asking agent to generate better questions (the 2026-09-20
model-comparison showed model-written questions scoring below human ones),
not a ranking change.

## Honesty notes

- The benchmark's focused model was updated to mirror the shipped product
  contract (12 hits per question, 36-page pack) — the model and the product
  changed together, and the amendment table in the task-evidence baseline
  preserves the original 2026-09-20 rows.
- The signpost descriptions were hand-written from card content before any
  weight or pack change was applied; description style was iterated exactly
  twice (content-summary, then purpose-style), and the style rule shipped is
  the generalizable one, not per-card tuning.
- The paired known-item gate (1,000 realistic pages, seed 42) shows no
  regression from the description weight change with descriptions present
  (recall@5 99.28% → 99.47%, MRR 0.9930 → 0.9938, latency flat).

## Reproduce

```
uv run pytest tests/integration/test_agent_workflow_eval.py -q   # pins 22/24
uv run python -m eval.run retrieval --realistic --size 1000 --top-k 10
```
