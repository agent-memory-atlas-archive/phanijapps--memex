# Recover all task evidence from a broad goal

## Scenario and outcome

A coding agent asks Memex about a whole task, such as fixing missing project memories. The first results may describe the visible symptom while omitting a prerequisite such as how project identity is derived. The agent can then act with incomplete evidence even though the missing memory is present in the same project. A useful recall flow should surface the distinct facts needed to work on the goal within a bounded context budget.

## Evidence and reproduction

The [coding-agent recall report](https://github.com/phanijapps/memex/blob/eval/agent-recall/docs/research/2026-09-20-coding-agent-recall.md) records a six-task, 18-memory comparison in [draft PR #8](https://github.com/phanijapps/memex/pull/8). One broad query per task found all three required memories for **2/6 tasks** and **13/18 memories**. Three human-written focused queries per task found all three for **6/6 tasks** and **18/18 memories**. This measures retrieval of labeled evidence, not whether an unaided agent can plan the focused queries or complete the coding task.

1. Check out the `eval/agent-recall` branch from PR #8 and run `uv run python -m eval.agent_workflow`. The runner creates a temporary Memex store; it does not use `~/.memex`.
2. Compare `one_shot_missing` and `focused_missing` for each task in the printed report. In the project-memory task, the broad query misses the derived project identity card. The focused queries retrieve it.
3. Inspect the [fixture](https://github.com/phanijapps/memex/blob/eval/agent-recall/eval/data/coding-agent-workflow.json) for the task goals, required memory labels, and focused queries. Current [FTS5 retrieval](../../src/memex/infrastructure/bm25_retriever.py) uses strict term matching and broadens to `OR` only after zero results, so one query can rank some matching cards while still missing a different prerequisite.

## Current evidence and next slice

The expanded [24-task baseline](../research/2026-09-20-task-evidence-baseline.md)
found complete evidence for 5/24 tasks through the current hook and 7/24
through one broad query. Human-written focused queries reached 12/24, but a
single pi model run reached 7/24 and did not pass the promotion gate; see the
[candidate report](../research/2026-09-20-task-evidence-focused-candidate.md).
None of these numbers measures completed coding work.

A [file-search diagnostic](../research/2026-09-20-task-evidence-file-search-probe.md)
combined FTS5 with a simple scan of the same page text and reached 8/24
complete tasks. That gain is too small to justify a new default search tool.

The next slice is a task evidence workflow that searches for distinct facts,
combines and deduplicates source-linked pages within one context budget, and
states which questions remain unanswered. A bounded file-text fallback is a
candidate only if it adds material coverage on fresh tasks while preserving
project, archive, and time filters. Freeze fresh labels before tuning, then
measure complete evidence sets, fact recall, rendered tokens, calls, latency,
leakage, and completed code against the existing baselines. The first model
comparison's five-minute and $5 approval has been spent; any new model run
needs its own ceiling.

## Phased build decision

1. **Make the measurement auditable.** Retain per-task hit and missing-page
   lists for future candidate runs, count pi cache tokens in model usage, and
   reject non-finite cost limits. Freeze new task labels before trying another
   retrieval candidate. Keep the current hook unchanged during this phase.
2. **Test task-directed retrieval.** Use the existing scoped recall operation
   to search distinct information needs, deduplicate pages, follow verified
   source links when useful, and surface unanswered needs. Compare a bounded
   file-text fallback only when recall misses; add it to the product only if it
   materially improves complete-task coverage under the same eight-page and
   4,096-token limits. This phase produces an experimental candidate, not an
   automatic default.
3. **Promote only after the full gate.** Repeat model-backed tests under a new
   approved time and spend limit, test completed coding behavior and a poisoned
   memory, and apply the task-evidence spec's recall, cost, latency, scope, and
   safety gates. Update installed guidance only if every gate passes.

The evaluator's cache-token and cost-limit corrections are implemented on the
`feat/task-evidence-continuity` branch. Automatic retention of per-task traces,
fresh frozen task labels, task-directed retrieval, and promotion checks remain
open.
