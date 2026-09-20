# Task evidence recall: held-out baseline

- **Run date:** 2026-09-20
- **Source revision:** `0f7813d0c4b1e3a6b2ddb46260ae6043aa2bc0cb`
- **Reproduce:** `uv run python -m eval.agent_workflow`

## Corpus

The expanded fixture contains 24 held-out coding tasks and 123 memory cards.
Of those cards, 99 are active current-project cards and 24 are excluded
archived or other-project distractors. Required labels are present only in
`eval/data/coding-agent-workflow.json`; the linked-summary and human-query
contributors used the sanitized
`eval/data/coding-agent-workflow-summary-source.json` projection, which exposes
task names, task goals, and eligible source pages without required labels or
focused queries.

The active cards are curated excerpts from canonical repository documents at the
pinned source revision. The fixture stores the exact body written to the isolated
Memex store, and the integration test validates that body against the pinned
source text. These are not captured Memex memories from live agent sessions.
Their titles are mechanically derived from the excerpt text, and that title shape
can affect BM25 retrieval.

The independently authored linked-summary fixture contains 24 task-ordered
summaries with 76 valid source links in `eval/data/task-linked-summaries.json`.
The independently authored human-query fixture contains 72 task-ordered queries
in `eval/data/human-focused-queries.json`.

## Baseline run

Two isolated benchmark runs produced stable deterministic task, corpus, recall,
call, and token counts. Latency is wall-clock timing from the second run; the
linked-summary latency was 1,055.1 ms in the first run and 1,051.7 ms in the
second run.

| Strategy | Complete tasks | Fact recall | Calls | Rendered tokens | Latency ms | Inactive hits | Other-project hits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Current hook injection | 5/24 | 43.75% | 24 | 14,988 | 97.4 | 0 | 0 |
| One broad query | 7/24 | 54.69% | 24 | 16,362 | 112.9 | 0 | 0 |
| Human-written focused queries | 12/24 | 73.44% | 72 | 14,559 | 189.4 | 0 | 0 |
| Linked task summary | 11/24 | 70.31% | 24 | 4,485 | 1,051.7 | 0 | 0 |

Each task strategy keeps at most eight distinct evidence hits and validates the
per-task rendered context budget at 4,096 estimated tokens. The linked-summary
baseline retrieves one summary page with one broad query, does not force the
intended task summary if another summary ranks first, and credits only links from
that single retrieved summary. Its token cost counts the rendered summary body,
not only snippets.

## Interpretation

The current hook baseline exercises the existing `build_injection` path, using
the hook's default top-k, relevance floor, renderer, and token estimator. The run
uses an isolated temporary store rather than a live installed harness.

The broad-query baseline outperforms current hook injection on this corpus, but
both miss many required facts. Human-written focused queries improve recall over
both broad baselines, but they complete only 12 of 24 tasks. Treat that result as
a diagnostic human-query baseline, not as a true ceiling over model behavior.

The linked-summary strategy scores below the human-query baseline after the
one-summary retrieval correction, but above broad query on both complete tasks
and fact recall. Its scorer credits valid source links to required pages as a
proxy for evidence. That proxy does not prove that an agent understood the linked
pages or completed the coding task.

This T1 run records baselines before candidate tuning. It does not promote any
guidance change, score completed code, or run unaided model question selection.
The retained report omits raw task goals, memory bodies, and tool inputs.
