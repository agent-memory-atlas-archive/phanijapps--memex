# Plan: Task evidence recall

- **Spec:** [`spec.md`](spec.md)
- **Status:** Drafting
- **Repository anchors:** `docs/architecture/overview.md`, ADR-0001, ADR-0002,
  ADR-0004; `src/memex/application/memory.py`,
  `src/memex/application/context_injection.py`,
  `src/memex/infrastructure/harness_installer.py`,
  `eval/agent_workflow.py`, and `tests/integration/test_agent_workflow_eval.py`.

> **Plan contract:** Tasks, Tests, Touches, and Done when are the build gates.
> The design is revisable while this plan is Drafting.

## Approach

Establish held-out task evidence and an isolated baseline first. Use the
existing recall interface to test unaided focused questions before changing
installed guidance. If the predeclared promotion gate fails, publish the
evaluation and keep the existing guidance. If it passes, add a short
task-recall procedure to the installed harness guidance, with bounded result
assembly and explicit missing evidence. Keep any shared assembly logic in the
application layer so adapters cannot disagree. The existing six-task fixture
remains a diagnostic ceiling. A disposable keyword-splitting probe completed
only 1/6 tasks, so term splitting is not a valid planner.

The first implementation loop is T1, the benchmark. T2 cannot start its
model-backed verification until the delivery owner records an approved wall
time and model-spend ceiling in the execution ledger; an absent ceiling blocks
those runs. No task is
expected to exceed 2,000 reviewable behavior-and-test lines.

## Constraints

- ADR-0001 keeps Markdown authoritative; evaluator stores are disposable.
- ADR-0002 puts shared behavior in the facade/application layer and adapters
  at the edge.
- ADR-0004 leaves harness enablement user-owned.
- The memory retrieval and evidence brief owns generic ranker, packing, and
  consolidation behavior.
- Raw goals, memory bodies, and tool inputs remain out of retained reports.

## Construction tests

**Integration:** `uv run python -m eval.agent_workflow` and the expanded
task evaluator use isolated stores. A held-out run compares baseline,
unaided focused questions, and the human-query diagnostic ceiling.
**Manual verification:** Invoke the installed guidance in at least one
supported harness and record the agent's question choices, sources, omissions,
and completed coding check. Use a fresh `MEMEX_DATA_DIR`.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Guide | T3 | Example exercised against isolated store | Current guide matches shipped path |
| Architecture | T2, T3 | Shared ownership and trust-boundary review | Map matches implementation |
| Evaluation fixture and report | T1, T2 | Reproduction command and paired report | Held-out labels and limits preserved |
| Changelog | T3 if guidance ships | Scoped entry | Shipped behavior named accurately |

## Design (LLD)

### Design decisions

A question plan belongs to the agent using its live task context. The existing
recall tool supplies evidence; it does not infer formal requirements. The
evaluator holds labels outside the question planner. The task-level promotion
decision compares complete evidence sets, not individual hit ranks. Traces to
AC-0001–AC-0004 and AC-0008–AC-0009.

### Interfaces and contracts

No new public tool is planned. Existing `Memex.recall`, CLI, and MCP results
remain the compatibility contract. Installed guidance is the user-facing
surface. Traces to AC-0010.

### Component / module decomposition

`eval/agent_workflow.py` owns task fixtures and paired scoring. Shared
deduplication and rendered-budget handling, if needed beyond agent guidance,
belong in `src/memex/application/` and reuse `RecallHit` source fields.
Installer-owned guidance remains in `marketplace/` and
`src/memex/infrastructure/harness_installer.py`. Traces to AC-0005–AC-0007.

### Failure, edge cases & resilience

Empty or partial recall is a visible evidence gap. Archived and wrong-project
hits are excluded before task assembly. A budget omission is reported in the
rendered answer. Traces to AC-0005–AC-0007.

## Tasks

### T1: Held-out task baseline is reproducible

**Depends on:** none

**Touches:** eval/*, eval/data/*, tests/integration/test_agent_workflow_eval.py, docs/research/*

**Tests:**
- Goal-based check: run the expanded evaluator twice and compare deterministic
  fixtures, one broad-query baseline, current-injection baseline, linked-summary
  baseline, and their measured costs for AC-0001. Keep the linked summary
  independent of the query planner.
- Integration: the existing fixture hash and project-filter assertions remain
  green while new held-out labels stay hidden from query planning.

**Approach:**
- Expand the sourced task corpus with independent goals and distractors. For
  each linked-summary baseline, a separate contributor sees the task goal and
  eligible source pages but not required-evidence labels, writes one
  source-linked summary page, and freezes it before scoring. Retrieve that
  page with one broad query under the same context budget.
- Record the baseline and diagnostic ceiling before candidate tuning.

**Done when:** The isolated benchmark command emits repeatable task and corpus
counts plus measured baseline task-complete recall, fact recall, calls,
rendered tokens, and latency before candidate tuning.

### T2: Focused task evidence passes its promotion gate or stays experimental

**Depends on:** T1

**Precondition:** The delivery owner has approved and recorded the wall-time
and model-spend ceiling for the model-backed run. Without it, stop after T1.

**Touches:** eval/*, src/memex/application/*, marketplace/*, tests/unit/*, tests/integration/*

**Tests:**
- Goal-based agent-run check: score the combined answer and recorded tool calls
  for AC-0005, AC-0006, and AC-0007. If a shared assembly callable is needed,
  locate the smallest application seam after T1 and write its red TDD stub
  before production code; no stub is claimed for guidance-only behavior.
- Goal-based paired run: compare AC-0002, AC-0003, AC-0004, AC-0008, AC-0009, AC-0011,
  AC-0012, AC-0013, and AC-0014 on held-out tasks; repeat variable model runs
  three times and report
  uncertainty without tuning against the held-out labels.
- Recorded agent-run check: a source-labelled memory card carrying an embedded
  tool/file instruction tests AC-0016. The run first proves the card is in the
  rendered task evidence, then checks the tool trace and working tree for the
  unauthorized action while observing one live-request-authorized action.
- Compatibility integration: exercise AC-0010 and AC-0015 through installed
  guidance for harnesses with recall transport, verify hosted Copilot's
  no-transport wording, and record a real isolated invocation.

**Approach:**
- Let an agent form focused questions from goals without labels.
- Reuse scoped recall, assemble a source-linked bounded answer, and install
  guidance only if the gate passes.

**Done when:** The paired report records a gate verdict and the candidate
either appears in installed guidance or remains unpromoted.

### T3: User and maintainer docs describe the measured result

**Depends on:** T2

**Touches:** docs/gitpages/guide.md, docs/architecture/overview.md, docs/product/changelog.md

**Tests:**
- Goal-based check: `uv run mkdocs build --strict` and a guide example
  exercised against the shipped path.
- Manual QA: record the real invocation and observed output.

**Approach:**
- Update current-state docs only for the behavior that shipped.
- Record the evaluation limits and decision in the research report.

**Done when:** Docs build cleanly and describe the observed product state.

## Rollout

Guidance changes ship with the package and take effect on future explicit
harness installs or updates. Existing user files remain under the installer's
conservative merge policy. No storage migration, service, or new dependency
is required.

## Risks

- Agent-generated questions may underperform human queries even with more
  calls.
- Installer guidance may not reach an already configured harness; the guide
  must state how to refresh it.
- A larger model-backed evaluation may exceed the agreed budget; stop at the
  ceiling and record an incomplete run rather than promote.

## Changelog

- 2026-09-20: Initial plan from the Ready intent-continuity brief.
