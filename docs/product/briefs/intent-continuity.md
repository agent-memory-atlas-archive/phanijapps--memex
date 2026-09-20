# Brief: Intent continuity across coding sessions

- **Slug:** `intent-continuity`
- **Status:** Draft
- **Received:** 2026-09-20
- **Owner:** Memex maintainers; delivery owner to be assigned.
- **Initiative:** `ini-001`

## Outcome

When an agent starts or resumes a coding task, Memex helps it gather the
complete set of relevant, current project memories within a bounded context
budget. The agent can see where each fact came from and recognize missing
support before it acts. Improvement is judged first by task-level evidence
recovery and then by completed coding work, not by the number of memories
stored or a single search result's rank.

The [six-task coding-agent recall evaluation](../../research/2026-09-20-coding-agent-recall.md)
found all three required pages for 2/6 tasks from one broad query and 6/6
from three human-written focused queries. Those figures describe a 22-card,
curated corpus. They do not show that an agent can choose the focused queries
unaided or produce better code. This brief starts with that unresolved question.

## Scope

### In scope

- Reproduce and extend the task-level recall evaluation with independently
  written goals, larger and noisier project stores, held-out evidence labels,
  and queries selected by an unaided agent or deterministic method.
- Test whether a task can be decomposed into a few concrete information needs,
  recalled through the existing scoped service, deduplicated, and assembled
  into one bounded, source-linked answer. Account for extra calls, latency,
  and context cost.
- Assess session-start and prompt injection against the current project and
  task. Test whether the repository/branch/commit query and global recall
  default introduce irrelevant or other-project memories, or miss required
  local and global facts.
- Check the complete rendered injection against its stated token budget,
  including headers and metadata; make an over-budget or incomplete result
  visible. Coordinate any generic budget-contract change with the retrieval
  and evidence brief.
- Test whether consolidation preserves the facts needed by later coding tasks
  as a store grows. Send generic candidate-selection, idempotency, and
  fact-retention changes to the retrieval and evidence brief.
- Evaluate whether better evidence recovery improves an agent's code and
  reduces clarification or wrong assumptions in interrupted tasks.
- Preserve shared application behavior across CLI, MCP, and harness adapters
  for any task-level delivery selected from this brief.

### Non-goals

- Automatically extracting a formal requirement set from every transcript.
- A new task or intent node type, checkpoint store, workflow engine, or
  automatic plan resumption before a measured task-state failure calls for it.
- A separate ranker, context-packer, or consolidation implementation that
  duplicates the retrieval and evidence brief.
- Mandatory embeddings, graph storage, hosted services, or a background daemon.
- Treating retrieved memory as an instruction or as permission to use tools.
- Assuming the article's synthetic experiment predicts Memex's results.

## Success measures

- **Primary:** task-complete evidence recall: the fraction of held-out tasks
  for which every prelabelled necessary fact is in the combined, eligible
  context. Report fact-level recall alongside it. The six-task result above is
  an initial diagnostic, not a sufficient acceptance threshold.
- **Safety and relevance:** count stale, inactive, or other-project facts in
  injected context and distinguish a genuine global preference from an
  unrelated project's history. Report missing source links and any silent
  omissions from the context budget.
- **Cost:** report the actual rendered tokens, search calls, latency, and
  model use per task. Compare at the same total context budget where possible.
- **Downstream:** on held-out coding tasks, check completed behavior against
  predeclared requirements. Measure whether the agent used necessary evidence;
  do not infer coding success from retrieval alone.
- Compare current Memex, one broad query, human-written focused queries as a
  diagnostic ceiling, and proposed agent-generated or deterministic query
  plans. Include an ordinary linked task summary as a low-cost baseline.
- Predeclare numeric promotion and regression limits after baseline measurement
  and before tuning. Repeat variable model runs and report uncertainty.

## Constraints and delivery appetite

- Keep Markdown authoritative and indexes rebuildable. Reuse existing recall,
  project scope, status, source links, and token-budget interfaces before
  changing public models or adding dependencies.
- Retrieved pages and transcripts remain untrusted. No retrieved text can
  override the live request or the host's instruction order. Do not log memory
  contents, credentials, or tool inputs.
- Project-aware injection must preserve deliberate access to global memories
  without silently mixing unrelated projects. Define the selection rule and
  verify it across supported harnesses before changing the default.
- Fail visibly when required evidence cannot fit; do not silently claim a task
  has complete context. Preserve documented API compatibility.
- The first work unit is a bounded evaluation of Memex's own failure modes.
  Keep a candidate behavior only if it improves the primary task-level measure
  without unacceptable cost or completion regressions.
- Agree time and model-spend limits before running a larger agent evaluation.

## Coordination with existing work

The [memory retrieval and evidence brief](memory-retrieval-and-evidence.md)
owns generic lexical ranking, section provenance, temporal relationships,
context-budget mechanics, and consolidation safety. This brief owns the
coding-task journey: identifying needed facts, choosing recall questions,
assembling eligible evidence, and checking whether an agent uses it.

The existing [quality-gated retrieval spec](../../specs/quality-gated-retrieval/spec.md)
selects a lexical ranker using its own accuracy, cost, and latency gates. Its
candidate selection is not reopened here. Any generic packing, injection, or
consolidation defect found by the task evaluation goes to the owning brief or
an explicitly coordinated spec. Confirm those handoffs before materializing
specs. No hard dependency is registered while the evaluation design is Draft.

## Assumptions and risks

- **Assumption:** An agent or deterministic planner can turn a broad coding
  goal into useful information needs without the human author's answer key.
- **Risk:** Three human-written queries may be a misleading ceiling; agent
  queries may miss the prerequisite they were meant to discover.
- **Risk:** Extra recall calls can improve recall while increasing latency,
  tokens, and distracting evidence.
- **Risk:** A small curated store may conceal relevance failures in long-lived,
  noisy projects. Simulated archived and other-project cards do not establish
  production behavior.
- **Risk:** Project filtering can hide a valid global preference; global recall
  can inject another project's fact. Both errors need separate measurement.
- **Risk:** Consolidation may return a short summary that omits a fact needed
  later. An index hit alone cannot prove source retention.
- **Risk:** Retrieved evidence may be present but ignored by the agent. End-to-end
  coding checks are needed before claiming continuity benefits.

## Delivery shape

First design a reproducible, task-level evaluation that allows the agent to
form its own questions. If that confirms a material gap, the first candidate
behavior is bounded multi-query recall through the existing service, with
scoped deduplication and traceable evidence. Check its cost and completed-work
impact against the baselines before selecting a product default.

Project-aware hook selection is a separate candidate if measured hook output
shows a cross-project or local-relevance problem. Budget and consolidation
findings feed the existing retrieval and evidence work. Structured
requirements and task checkpoints remain future hypotheses if task-level
retrieval still fails to preserve user intent across interruptions. These are
planning candidates, not confirmed delivery slices.

## Governance references

- [ADR-0001](../../adr/0001-use-markdown-pages-as-memory-source-of-truth.md)
  keeps Markdown authoritative and SQLite disposable.
- [ADR-0002](../../adr/0002-use-layered-package-and-shared-adapter-contracts.md)
  requires shared domain and application behavior across adapters.
- [ADR-0004](../../adr/0004-require-user-scope-enablement.md)
  preserves user control over capture, injection, and consolidation enablement.

## Source provenance

- Direct user direction on 2026-09-20 to ground Memex improvements in its own
  behavior rather than treat the new intent-continuity research as product
  requirements. This revision retains repository-origin authority and Draft
  lifecycle status.
- [Coding-agent recall evaluation](../../research/2026-09-20-coding-agent-recall.md)
  records the six-task, 22-card result and its limits. The
  [broad-goal recall backlog item](../../backlog/001-broad-goal-recall.md)
  names the potential first behavior and the unaided-agent validation gap.
- [Intent-continuity survey](../../intent-continuity-survey.md) records the
  supplied article and papers as adjacent evidence with explicit confidence
  limits. Their design is not adopted by this brief.
- Repository code inspected for this revision:
  [`context_injection.py`](../../../src/memex/application/context_injection.py),
  [`workspace_context.py`](../../../src/memex/infrastructure/workspace_context.py),
  [`consolidator.py`](../../../src/memex/infrastructure/consolidator.py), and
  [`cli.py`](../../../src/memex/cli.py).

## Ready gaps

- Assign a delivery owner and agree the evaluation's time and spending limit.
- Decide the held-out task set, evidence labels, agent/query baseline, and
  numeric promotion limits before tuning.
- Define the intended mix of current-project and global memory for hooks,
  including a safe rule when the project is unknown.
- Confirm the task-level handoff to the retrieval and evidence brief for
  generic budget and consolidation changes.
- Complete a Ready review before confirming delivery slices and writing specs
  and implementation plans.

## Spec map

| Spec | Status |
| --- | --- |
