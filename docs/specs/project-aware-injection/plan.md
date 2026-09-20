# Plan: Project-aware injection

- **Spec:** [`spec.md`](spec.md)
- **Status:** Drafting
- **Repository anchors:** `docs/architecture/overview.md`, ADR-0002, ADR-0004,
  `src/memex/cli.py`, `src/memex/application/context_injection.py`,
  `src/memex/infrastructure/workspace_context.py`,
  `tests/unit/test_context_injection.py`, and
  `tests/unit/test_cli.py`.

> **Plan contract:** Tasks, Tests, Touches, and Done when are the build gates.
> The design is revisable while this plan is Drafting.

## Approach

Measure the current hook's complete rendered output on held-out project,
global, and unknown-project cases. The evaluation is the first deliverable.
Only a demonstrated relevance failure allows a candidate selection rule to be
built and compared. A missing required global preference or an inactive hit is
a relevance failure too. If the baseline has no specified failure or the candidate loses
required global preferences, record no default change. Keep one shared
injection rule behind the existing CLI hook and preserve user-owned
enablement. The hook baseline runs independently; task-evidence labels may be
reused only when their fixture contract is already available. An isolated
throwaway run of the real hook emitted a current-project page, an other-project
page, and a global preference for the same query, so cross-project leakage is
an observed failure worth evaluating on held-out task starts.

## Constraints

- ADR-0002 requires shared application behavior across adapters.
- ADR-0004 forbids repository-driven activation.
- The retrieval and evidence brief owns generic context-budget and ranking
  changes; this plan owns selection for the coding-task hook only.
- Tests use isolated `MEMEX_DATA_DIR` and never touch live memory.

## Construction tests

**Integration:** Invoke `memex hook session-start` from project and
non-Git fixtures, collecting stdout, stderr, exit code, retained log records,
and access counters; assert the other-project source marker is absent from
every channel and its access counter is unchanged. Include active global
preferences alongside global episodes, summaries, and project-derived pages;
assert only the preference appears. Inject identity, query, index, and store
failures plus a raised lower-level timeout into a live hook process; assert
empty stdout, exit 0, bounded stderr, no broad fallback read, and no raw
memory body, path, or query in any captured channel.
**Manual verification:** Exercise enabled harness paths after any selection
change and verify the same output contract. Use one poisoned project fact and
one poisoned global preference to check the instruction-vs-data boundary.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Guide | T3 if default changes | Isolated hook example | Current user promise matches output |
| Architecture | T2, T3 | Scope rule and trust-boundary review | Map matches shared implementation |
| Evaluation fixture and report | T1, T2 | Paired runner and report | Decision reproducible |
| Changelog | T3 if default changes | Scoped entry | Entry exists only for changed behavior |

## Design (LLD)

### Design decisions

The evaluator checks the output the agent sees, including metadata. A full
rendered-block budget defect is routed to the retrieval and evidence owner.
Project identity is derived by `workspace_context.py`; it is not
inferred from arbitrary retrieved text. The candidate rule distinguishes
project facts from global preferences, with a non-Git path-derived identity.
Traces to AC-0001–AC-0006, AC-0010, AC-0011, and AC-0012.

### Interfaces and contracts

`memex hook session-start` and its context block remain the public contract.
The CLI stays a thin adapter; shared selection belongs in
`src/memex/application/context_injection.py`. Traces to AC-0008.

### State & control flow

The hook derives identity before recall, selects eligible project and global candidates,
packs the rendered block, and returns content or silence. A no-change verdict
keeps the current path. Traces to AC-0002–AC-0006 and AC-0014–AC-0016.

### Failure, edge cases & resilience

The non-Git path identity cannot borrow a nearby project's scope. A missing
global preference makes a candidate ineligible. Identity or read failure
produces a bounded, empty hook result without a broad fallback. Traces to
AC-0005, AC-0006, AC-0008, AC-0009, and AC-0016.

## Tasks

### T1: Session-start relevance baseline is reproducible

**Depends on:** none

**Touches:** eval/*, tests/unit/test_context_injection.py, docs/research/*

**Tests:**
- Goal-based integration: paired isolated fixture runs measure AC-0001 and
  give a stable baseline for AC-0002, AC-0003, AC-0010, AC-0011, and AC-0012.
- Test fixture spans known project, another project, global preference,
  archived page, and unknown project.

**Approach:**
- Reuse task labels where suitable and add hook-specific fixtures.
- Record complete rendered output metrics without raw memory content.

**Done when:** The report names the baseline trigger or an explicit no-change
verdict.

### T2: Shared hook selection passes the relevance gate or stays unchanged

**Depends on:** T1

**Touches:** src/memex/application/context_injection.py, src/memex/cli.py, tests/unit/test_context_injection.py, tests/unit/test_cli.py

**Tests:**
- TDD: existing `build_injection` and CLI hook suites receive red cases for
  AC-0004, AC-0005, AC-0006, AC-0013, AC-0014, AC-0015, and AC-0016 before
  selection changes. The AC-0014 fixture checks access counters before/after
  and spies on scoped retriever reads, then captures stdout, stderr, and logs;
  AC-0016 injects each failure mode, including a raised `TimeoutError` from
  recall while the hook process remains alive.
- Integration: repeat T1's fixture for AC-0002, AC-0004, AC-0008, AC-0009,
  AC-0010, AC-0011, AC-0012, AC-0015, and AC-0016, including captured log
  records and the failure cases in Construction tests.
- Recorded agent-run check: for AC-0017, confirm each poisoned page appears
  in the rendered hook block before inspecting the tool trace and working tree
  for unauthorized action while a live-request action succeeds.

**Approach:**
- Implement the smallest selection rule in the shared injection path only
  when T1 demonstrates a failure.
- Keep explicit scope and user enablement separate.

**Done when:** The paired report records a pass or no-change verdict and the
real hook invocation matches it.

### T3: Hook documentation matches the measured result

**Depends on:** T2

**Touches:** docs/gitpages/guide.md, docs/architecture/overview.md, docs/product/changelog.md

**Tests:**
- Goal-based check: `uv run mkdocs build --strict`.
- Manual QA: invoke `memex hook session-start` in an isolated enabled
  environment and compare the guide's described output.

**Approach:**
- Describe the selected rule only if it ships.
- Record the evaluation limit and no-change reason otherwise.

**Done when:** The strict docs build passes and the current-state guide
matches the observed hook output.

## Rollout

Any changed selection rule is applied by the existing hook command on future
invocations. There is no storage migration or new dependency. User-owned
harness activation remains opt-in and existing configuration is preserved.

## Risks

- Project-filtered output may lose genuinely global user preferences.
- Unknown-project fallback may be more confusing than silence.
- The hook's latency-sensitive path may grow with multiple recall calls.

## Changelog

- 2026-09-20: Initial conditional plan from the Ready intent-continuity brief.
