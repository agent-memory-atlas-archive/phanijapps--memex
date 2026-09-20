# Recover all task evidence from a broad goal

## Scenario and outcome

A coding agent asks Memex about a whole task, such as fixing missing project memories. The first results may describe the visible symptom while omitting a prerequisite such as how project identity is derived. The agent can then act with incomplete evidence even though the missing memory is present in the same project. A useful recall flow should surface the distinct facts needed to work on the goal within a bounded context budget.

## Evidence and reproduction

The [coding-agent recall report](https://github.com/phanijapps/memex/blob/eval/agent-recall/docs/research/2026-09-20-coding-agent-recall.md) records a six-task, 18-memory comparison in [draft PR #8](https://github.com/phanijapps/memex/pull/8). One broad query per task found all three required memories for **2/6 tasks** and **13/18 memories**. Three human-written focused queries per task found all three for **6/6 tasks** and **18/18 memories**. This measures retrieval of labeled evidence, not whether an unaided agent can plan the focused queries or complete the coding task.

1. Check out the `eval/agent-recall` branch from PR #8 and run `uv run python -m eval.agent_workflow`. The runner creates a temporary Memex store; it does not use `~/.memex`.
2. Compare `one_shot_missing` and `focused_missing` for each task in the printed report. In the project-memory task, the broad query misses the derived project identity card. The focused queries retrieve it.
3. Inspect the [fixture](https://github.com/phanijapps/memex/blob/eval/agent-recall/eval/data/coding-agent-workflow.json) for the task goals, required memory labels, and focused queries. Current [FTS5 retrieval](../../src/memex/infrastructure/bm25_retriever.py) uses strict term matching and broadens to `OR` only after zero results, so one query can rank some matching cards while still missing a different prerequisite.

## Potential fix

Start at the agent or harness layer: turn a broad task into two or three concrete information needs, call the existing project-scoped `memex_recall` for each, deduplicate the results, and fit the combined evidence into one explicit token budget. Preserve the current scope filters. This needs no new MCP tool or storage model. If unaided query planning still misses prerequisite concepts, test a retrieval-layer change against that demonstrated failure before expanding the design.

Validate with agents generating their own queries from held-out goals, rather than the fixture's human-written focused queries. Report task-complete evidence recall, cross-project and archived hits, total context tokens, and extra calls against the one-query baseline. The next step is that unaided evaluation; the current report cannot establish that the proposed flow solves the agent-level problem.
