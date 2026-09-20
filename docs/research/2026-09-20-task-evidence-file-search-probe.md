# Task evidence: file search diagnostic

- **Date:** 2026-09-20
- **Scope:** the existing 24-task, 123-card isolated fixture in
  `eval/data/coding-agent-workflow.json`
- **Status:** diagnostic only; no production retrieval or hook change

## Result

The current project-scoped FTS5 broad query found every required page for
7/24 tasks and 35/64 required facts with eight hits per task. A simple scan of
the same active project page text found 6/24 tasks and 30/64 facts. Reciprocal
rank fusion of the FTS5 and text-scan lists found 8/24 tasks and 38/64 facts.
The fusion gained one complete task and three facts over FTS5 alone.

This does not establish that an `rg` or `rgapi` tool would improve Memex. The
probe used a Python scan of the fixture's indexed title and body fields, not
the `rg` executable, `rgapi`, or a production filesystem walk. It only tests
whether a second lexical ranking over the same page text adds useful
candidates. The already-scored fixture is a diagnostic set, not a fresh
validation set, and the scan did not measure rendered token cost or latency.

## Method

The probe built a fresh temporary Memex store and kept only active cards from
the fixture's current project. It split each task goal, title, and body into
lowercase alphanumeric terms and removed common task words. A card's scan
score summed inverse-document-frequency weights for overlapping body terms,
with twice that weight for overlapping title terms. The scan and FTS5 each
supplied up to 20 candidates. Reciprocal rank fusion used `1/(60 + rank)`
for each list, ordered ties by slug, and retained eight distinct pages per
task. Required-page labels were used only after ranking to score the output.

The published broad-query baseline also reports 7/24 tasks and 35/64 facts;
the fresh isolated probe reproduced those counts. It did not use the live
developer memory store or make a model call.

## Delivery decision

The present evidence does not justify a new user-facing file-search tool or a
default `rgapi` dependency. On this corpus, both searches work from similar
words; the important missing pages are often about a prerequisite the broad
task goal never names. The next candidate should help the agent search for
distinct task facts, preserve source links, and show unanswered questions.
It may use a bounded file-text search as a fallback if a fresh test shows a
material gain over the existing scoped recall operation.

Before promotion, evaluate on newly authored tasks whose labels are frozen
before candidate tuning. Compare complete evidence sets, fact recall,
rendered tokens, calls, latency, inactive and other-project hits, and completed
coding work. Keep the current task-evidence promotion gate and model-run
spending authorization separate; this diagnostic grants no additional model
budget.
