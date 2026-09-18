# Plan: Quality-gated retrieval

- **Spec:** [`spec.md`](spec.md)
- **Status:** Drafting
- **Repository anchors:** `docs/architecture/overview.md` (facade, retrieval,
  and offline-eval ownership); `src/memex/application/memory.py` (shared recall
  service and composition root); `src/memex/infrastructure/bm25_retriever.py`
  (current ranking, filtering, tie surface, and side effects); `eval/runner.py`
  and `eval/run.py` (metric and reproducibility seams);
  `tests/unit/test_bm25_retriever.py` and `tests/unit/test_eval_entry.py`
  (construction patterns). The optional native package is a deliberate
  deviation from the standard-library preference and remains confined to an
  experiment until the approved dependency gate is met.

> **Plan contract:** this is the implementation strategy. It may change
> substantively only while its Status is `Drafting`, before approval records its
> baseline.

## Approach

Extend the existing offline evaluator into a paired baseline-versus-candidate
gate before changing production retrieval. Candidate implementations live in
`eval/` first and consume the same generated pages and query manifest. The
initial set covers FTS5 field weighting, deterministic reciprocal-rank fusion,
query backoff, and bounded rank-space boosts, plus an optional `rgapi==0.1.22`
lexical candidate. Only the one candidate that passes every gate moves behind
the existing `BM25Retriever`/`Memex.recall` service; if none passes, the
production path remains unchanged and the report is the result.

The implementation uses full mode because it evaluates a new compiled
dependency and may change the retrieval strategy shared by every adapter.

A pre-review disconfirming probe ran `uv run python -m eval.run retrieval
--realistic --size 100 --seed 42` against an evaluator-owned temporary store.
It completed 208 queries and emitted difficulty metrics, p99 latency, and the
reproducibility JSON, confirming that the current harness can carry paired
measurement work; it does not establish any promotion gate.

### Work-loop assumptions

- **Files likely touched:** `eval/`, retrieval-focused tests,
  `src/memex/infrastructure/bm25_retriever.py`, and the durable-output documents
  named by the spec; `pyproject.toml` and `uv.lock` only for an optional
  experiment.
- **Proof of done:** focused unit and integration suites, paired 10K/100K
  reports satisfying AC-0001–AC-0007, the full repository gates, and one real
  isolated CLI recall.
- **Not changing:** Markdown schema, public recall datatypes and arguments,
  adapters, lifecycle hooks, consolidation, or the canonical storage model.
- **Declined:** a general plugin framework for rankers; one experimental seam
  and the existing retriever are sufficient for this slice.
- **Declined:** embeddings, learned reranking, and persistent section indexes;
  the brief assigns them no role in this first slice.

No task is expected to exceed 2,000 reviewable behavior-and-test lines. The
work is DEEP rather than mechanically WIDE, so measurement, candidates,
selection, promotion, and documentation remain dependency-ordered tasks that
leave the repository working after each task.

## Constraints

- The contract is `spec.md`, especially its same-candidate promotion rule and
  portability boundary.
- ADR-0001 keeps Markdown authoritative; no candidate writes canonical data.
- ADR-0002 keeps retrieval shared through the application facade; adapters do
  not select or reimplement rankers.
- All benchmark stores use evaluator-owned temporary directories or verified
  empty explicit directories. No test or measurement touches `~/.memex`.
- The `rgapi` experiment is pinned to 0.1.22, isolated from base installation,
  and covered by Apache-2.0 license evidence. Its transitive `fastcore`
  dependency is part of the dependency review.
- Logs and reports contain queries only when they come from the generated eval
  corpus; production memory content and tool inputs are never logged.

## Construction tests

- `tests/unit/test_retrieval_comparison.py` owns threshold, same-candidate,
  raw-latency percentile selection, rendered token-accounting, and
  incomplete-result logic.
- `tests/unit/test_eval_entry.py` owns isolated-directory and reproducibility
  report behavior.
- `tests/unit/test_bm25_retriever.py` and
  `tests/acceptance/test_index_retrieval_acceptance.py` own production ranking,
  compatibility, deduplication, rank numbering, production-path determinism,
  winner identity, and access-statistic behavior.
- `tests/integration/test_rgapi_candidate.py` owns the optional native binding
  and subprocess prohibition and skips only when the optional extra is absent.
- Paired seed-42 reports at 10K and 100K are goal-based PR evidence, not
  committed golden outputs; committed tests use small deterministic fixtures.

## Durable-output map

| Output | Task | Verification | Retention |
| --- | --- | --- | --- |
| User guide | T6 | `uv run mkdocs build --strict` and content pin | Repository-durable at `docs/gitpages/guide.md` |
| Architecture map | T6 | architecture content pin and strict docs build | Repository-durable at `docs/architecture/overview.md` |
| Decision rationale | T4, T6 | paired report plus implementation-note content pin | Repository-durable at `docs/gitpages/implementation-notes.md` |
| Evaluation evidence | T4 | schema validation, rerun command, and reviewer inspection | PR-only generated JSON; stable post-closeout owner is the committed evaluator plus implementation note |
| Release history | T6, only if default changes | changelog content pin | Repository-durable at `docs/product/changelog.md` |
| Delivery contract | G-plan gates | spec/plan lint, independent reviews, and human approvals | Repository-durable at this directory; the cohort-approved content hashes are the fingerprints read by implementers, reviewers, CI, and closeout |

## Design (LLD)

### Design decisions

The evaluator is the selection authority; no candidate may self-report a pass.
It compares one immutable baseline record with one immutable candidate record
and returns per-gate outcomes plus one conjunction. Candidate discovery and
scoring remain replaceable experiment code until selection.

### Interfaces and contracts

Production keeps `Memex.recall(...) -> RecallResult` and its existing keyword
arguments. Evaluation gains a development-only candidate selector and JSON
comparison output; it remains invokable as `uv run python -m eval.run`, not as
a `memex` CLI subcommand. The report schema is versioned and records enough
inputs to reproduce the comparison.

### Component and module decomposition

- `eval/runner.py` continues to own query execution and raw metrics.
- A small comparison component under `eval/` owns paired metric records and
  gate verdicts; it contains no production imports beyond public Memex types.
- Candidate adapters under `eval/` expose ordered page slugs and completeness
  metadata. The `rgapi` adapter consumes structured Python objects, never CLI
  text.
- The winning deterministic strategy is folded into
  `BM25Retriever` or one narrowly owned infrastructure collaborator only after
  T4 selects it. No generic ranker registry is introduced.

### State and control flow

For each corpus size, the evaluator creates one fresh corpus, constructs the
baseline and candidate over equivalent derived state, runs the same ordered
queries, and serializes both records with the gate verdict. Quality and token
metrics use the 10K run. Latency gates use 10K and 100K runs. Production recall
continues to record access once after final deduplication.

### Behavior and rules

Reciprocal-rank fusion combines rank positions rather than incomparable raw
scores. Query backoff broadens only after a stricter query has insufficient
candidates. Boosts are deterministic and bounded in rank space. Duplicate
candidate slugs collapse before `top_k`; ascending slug is the final tie-break.
The exact candidate parameter grid is report metadata, not a public contract.
The latency calculation uses every raw per-query observation and nearest-rank
p99 before any display rounding. Context cost uses the existing injection
packer, renderer, and estimator with a fixed 4096-token packing budget; report
metadata pins those identities and the budget.

### Failure, edge cases, and resilience

An invalid query keeps the existing `ValueError`. Empty results remain valid.
An optional dependency import failure disables only that experiment. An
incomplete candidate result is represented explicitly and fails promotion.
A failed measurement or malformed report stops selection rather than falling
back to a partial comparison.

### Quality attributes

The selected strategy is deterministic, offline, local-first, and bounded by
the spec's accuracy, context-cost, and latency gates. Benchmark timing excludes
setup, uses the same process and runner for paired values, and reports rather
than hides non-identifying environment metadata. Reports exclude hostnames,
device names, usernames, profile paths, and user-specific filesystem paths.

### Dependencies and integration

`rgapi==0.1.22` is the only proposed new package and is an optional evaluation
extra. Static contract evidence comes from its PyPI metadata and source
manifests. The official ripgrep crates embedded by the package supply walking
and matching; Memex supplies ranking, filters, deduplication, and promotion
policy. Base installation and production fallback depend only on SQLite FTS5.

## Tasks

### T1: Paired metrics and promotion gate

**Depends on:** none

**Spec map:** AC-0001, AC-0002, AC-0003, AC-0004, AC-0005, AC-0006, AC-0007,
AC-0008, AC-0009

**Mode:** TDD

**Tests:**

- `test_candidate_gate_requires_one_candidate_to_pass_every_threshold`
  (AC-0001, AC-0002, AC-0003, AC-0004, AC-0005, AC-0006, AC-0007),
  `stub: true`.
- `test_comparison_report_separates_stable_and_volatile_fields` (AC-0008,
  AC-0009), completed during green.
- Raw `HitResult` latency and rendered-hit fixtures exercise the percentile and
  context-cost construction before verdict evaluation (AC-0004, AC-0005).

```python
# STUB: AC-0007
from eval.comparison import CandidateMetrics, evaluate_candidate


def test_candidate_gate_requires_one_candidate_to_pass_every_threshold() -> None:
    baseline = CandidateMetrics(
        hard_recall_at_10=0.320,
        hard_mrr=0.400,
        recall_at_10={"overall": 0.680, "easy": 0.950, "medium": 0.750},
        tokens_per_correct_hard_query=100.0,
        p99_ms={10_000: 40.0, 100_000: 80.0},
        complete=True,
    )
    candidate = CandidateMetrics(
        hard_recall_at_10=0.370,
        hard_mrr=0.450,
        recall_at_10={"overall": 0.675, "easy": 0.945, "medium": 0.745},
        tokens_per_correct_hard_query=80.0,
        p99_ms={10_000: 44.0, 100_000: 88.0},
        complete=True,
    )

    verdict = evaluate_candidate(baseline=baseline, candidate=candidate)

    assert verdict.passed is True
    assert set(verdict.gates) == {
        "hard_recall_at_10",
        "hard_mrr",
        "recall_regression",
        "tokens_per_correct_hard_query",
        "absolute_p99",
        "paired_p99",
    }
    assert all(gate.passed for gate in verdict.gates.values())
```

**Stub validation:** syntax passed and the import produced the intended
`ModuleNotFoundError` red on 2026-09-17; no repository test file was created.

**Approach:** add immutable paired metric and verdict types beside the existing
evaluator, derive the context-cost metric from rendered hits and the existing
token estimator, and serialize stable comparison fields separately from
volatile run metadata.

**Done when:** the task's tests independently red on every failing side of each
threshold and green at the exact passing boundaries.

### T2: Deterministic lexical candidates

**Depends on:** T1

**Spec map:** AC-0012, AC-0020, AC-0021

**Mode:** TDD

**Tests:**

- `test_fusion_deduplicates_and_uses_slug_as_final_tie_break` (AC-0012,
  AC-0021), `stub: true`.
- `test_fusion_assigns_consecutive_one_based_ranks` (AC-0020), completed
  during green.
- Candidate fixtures cover title/body/tag weighting, reciprocal-rank fusion,
  query backoff, and bounded boosts without duplicating threshold assertions
  owned by T1.

```python
# STUB: AC-0012
from eval.candidates import RankedCandidate, reciprocal_rank_fusion


def test_fusion_deduplicates_and_uses_slug_as_final_tie_break() -> None:
    sources = [
        [RankedCandidate("beta", 1), RankedCandidate("alpha", 2)],
        [RankedCandidate("alpha", 1), RankedCandidate("beta", 2)],
    ]

    ranked = reciprocal_rank_fusion(sources)

    assert [candidate.slug for candidate in ranked] == ["alpha", "beta"]
```

**Stub validation:** syntax passed and the import produced the intended
`ModuleNotFoundError` red on 2026-09-17; no repository test file was created.

**Approach:** implement candidates in evaluation scope using current FTS5
search results and rank positions. Keep parameter sets explicit in report
metadata and stable-sort every output.

**Done when:** the candidate suite proves deterministic, duplicate-free,
consecutively ranked output and the evaluator can compare every candidate with
baseline.

### T3: Optional in-process `rgapi` candidate

**Depends on:** T1

**Spec map:** AC-0014, AC-0015, AC-0016

**Mode:** goal-based integration

**Tests:** no stub (goal-based). `tests/integration/test_rgapi_candidate.py`
uses the optional environment, structured rows, an incomplete-result fixture,
and a process-spawn sentinel (AC-0015, AC-0016). A base-environment job removes the extra and runs
the existing write/rebuild/recall smoke path with `PATH` containing no `rg`.
That base job verifies AC-0014.

**Approach:** declare a pinned optional evaluation dependency, adapt structured
search rows to candidate slugs, sort explicitly, and propagate `complete` and
`stop_reason` into the comparison record. Do not import it from `src/memex`.

**Done when:** the optional integration and dependency/license audit pass while
the base environment remains fully functional without the module or CLI.

### T4: Run paired selection at scale

**Depends on:** T2, T3

**Spec map:** AC-0001, AC-0002, AC-0003, AC-0004, AC-0005, AC-0006, AC-0007,
AC-0008, AC-0009, AC-0010, AC-0016

**Mode:** goal-based integration

**Tests:** no stub (goal-based). Run the committed evaluator with seed 42 at
10K for every candidate and at 100K for the baseline plus candidates still
eligible after the 10K gate. Validate report schema and rerun the selected 10K
candidate once for deterministic quality and ordering. The explicit empty and
non-empty data-directory cases verify AC-0010.

**Approach:** execute baseline and candidate in one runner environment at one
source revision, retain sanitized JSON as PR evidence, select only a candidate
with an overall passing verdict, and record failed candidates without averaging
their metrics into the winner.

**Done when:** one report names a same-candidate pass for every gate. If no
candidate is eligible, the task records the failures and blocks spec completion
before production promotion.

### T5: Promote the selected strategy through shared recall

**Depends on:** T4

**Spec map:** AC-0011, AC-0012, AC-0013, AC-0017, AC-0018, AC-0019, AC-0020,
AC-0021, AC-0022, AC-0023, AC-0024

**Mode:** TDD plus manual QA

**Tests:** no stub (implementation-discovered). The winning strategy determines
whether the production seam remains inside `BM25Retriever` or needs one narrow
infrastructure collaborator. The discovery predicate is the T4 winner's input
requirements; the constraint is the unchanged `Memex.recall` contract. The
proof obligation is a real-index compatibility matrix for AC-0011, AC-0012,
AC-0013, AC-0020, AC-0021, and AC-0023; a committed winner-discriminating
API/CLI fixture for AC-0022; an identity comparison with the paired promotion
report for AC-0024; and isolated CLI observations for AC-0017, AC-0018, and
AC-0019.

**Approach:** move only the selected deterministic mechanism into the existing
infrastructure retrieval owner, deduplicate before limiting and access updates,
and leave every adapter on `Memex.recall`. If the winner depends on `rgapi`,
stop for the Ask-first runtime dependency and portability decision. Persist one
minimal fixture whose baseline and winning orders differ, then verify the
winning order and candidate identity through the shared API and CLI.

**Done when:** the compatibility, retrieval acceptance, and manual CLI checks
pass through the shared service.

### T6: Refresh durable documentation and run release gates

**Depends on:** T5

**Spec map:** Durable Outputs

**Mode:** goal-based check

**Tests:** no stub (goal-based). Run `uv run mkdocs build --strict`, the
documentation content pins, `uv run ruff check .`, `uv run ruff format --check
.`, `uv run mypy src tests`, and `uv run pytest`.

**Approach:** update the guide, architecture overview, implementation notes,
and changelog when applicable. Describe only the shipped winner and link to the
evaluator for selection mechanics; do not document failed experiments as
product features.

**Done when:** every named gate passes and closeout can account for each durable
output row.

## Rollout

The evaluator and optional candidate land without changing production recall.
After T4 produces a passing winner, T5 changes the internal default in one
reversible commit while preserving the FTS5 baseline implementation for
rollback. No data migration or irreversible write occurs. A winner requiring
`rgapi` pauses before promotion for the explicit runtime-dependency and
portability decision; otherwise the optional experiment remains development
only. Deployment needs no service, secret, network access, or sequencing
beyond shipping code and documentation together.

## Risks

- The synthetic corpus may reward generator vocabulary rather than real user
  queries. The paired gate limits false attribution but does not replace later
  real-corpus validation.
- Benchmark noise may dominate a 10% paired-latency bound. Same-process paired
  runs and recorded environment reduce noise; a noisy run fails closed and is
  rerun as a whole, never cherry-picked per query.
- `rgapi` is young, adds `fastcore`, and lacks wheels for platforms Memex
  claims to support. It remains optional and cannot become runtime-critical
  without a separate decision.
- Candidate fusion can improve hard queries while duplicating pages or
  disturbing filters. Deduplication, compatibility, and access-statistic tests
  run before promotion.

## Changelog

- 2026-09-17: initial plan from the confirmed quality-gated lexical retrieval
  slice; `rgapi==0.1.22` is an optional in-process experiment, with FTS5 kept as
  the portable default and fallback until all gates pass.
