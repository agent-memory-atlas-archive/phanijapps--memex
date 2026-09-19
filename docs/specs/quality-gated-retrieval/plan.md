# Plan: Quality-gated retrieval

- **Spec:** [`spec.md`](spec.md)
- **Status:** Done
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
  dependency and embedded Rust crates are part of the dependency review.
- Candidate paths canonicalize under the resolved eval store's `docs` root;
  path rejection, query sanitization, and retained diagnostic sanitization
  follow the controls owned by the spec and `docs/architecture/overview.md`.
- Logs and reports contain queries only when they come from the generated eval
  corpus; production memory content and tool inputs are never logged.

## Construction tests

- `tests/unit/test_retrieval_comparison.py` owns threshold, same-candidate,
  raw-latency percentile selection, rendered token-accounting, and
  incomplete-result logic.
- `tests/unit/test_eval_entry.py` owns isolated-directory and reproducibility
  report behavior, clean-revision promotion enforcement, and paired-store
  independence.
- `tests/unit/test_bm25_retriever.py` and
  `tests/acceptance/test_index_retrieval_acceptance.py` own production ranking,
  compatibility, deduplication, rank numbering, production-path determinism,
  winner identity, and access-statistic behavior.
- `tests/integration/test_rgapi_candidate.py` owns the optional native binding
  subprocess prohibition, path confinement, literal query boundary, bounded
  work, and dependency admission, and skips only when the optional extra is
  absent.
- Paired seed-42 reports at 10K and 100K are goal-based PR evidence, not
  committed golden outputs; committed tests use small deterministic fixtures.

## Durable-output map

| Output | Task | Verification | Retention |
| --- | --- | --- | --- |
| User guide | T8 | `uv run mkdocs build --strict` and content pin | Repository-durable at `docs/gitpages/guide.md` |
| Architecture and security controls | T8 | retrieval trust-boundary content pin and strict docs build | Repository-durable at `docs/architecture/overview.md` |
| Decision rationale | T6, T8 | paired report plus implementation-note content pin | Repository-durable at `docs/gitpages/implementation-notes.md` |
| Evaluation evidence | T4, T6 | fixture/schema validation, rerun command, and reviewer inspection | Compact source fixtures are repository-durable; generated JSON is PR-only evidence |
| Release history | T8, only if default changes | changelog content pin | Repository-durable at `docs/product/changelog.md` |
| Research rationale | T8 | source-link and benchmark-limit content pins | Repository-durable at `docs/memory-optimization-survey.md` |
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
  T6 selects it. No generic ranker registry is introduced.

### State and control flow

For each corpus size, the evaluator creates one immutable Markdown corpus
snapshot, copies it into distinct fresh baseline and candidate data
directories, and rebuilds a separate SQLite database in each. It runs the same
ordered queries and serializes both records with the gate verdict; neither run
can observe the other's access-statistic mutations. Quality and token metrics
use the 10K run. Latency gates use 10K and 100K runs. Production recall
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
back to a partial comparison. File-search results canonicalize and confine
under the eval store's resolved `docs` root before they are read or reported;
path resolution failures become a sanitized incomplete result. Retained error
records use a closed category set and never serialize exception strings.

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
policy. Query patterns reuse the current safe-token language, literal-escape
terms, and carry explicit byte, time, and result limits. Base installation and
production fallback depend only on SQLite FTS5. Dependency admission records
lock integrity, provenance, maintenance, licenses, and Python plus Rust SCA
coverage; absent coverage requires the spec's Ask-first decision.

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

**Spec map:** AC-0014, AC-0015, AC-0016, AC-0025, AC-0026, AC-0027

**Mode:** goal-based integration

**Tests:** no stub (goal-based). `tests/integration/test_rgapi_candidate.py`
uses the optional environment, structured rows, an incomplete-result fixture,
and a process-spawn sentinel (AC-0015, AC-0016). A base-environment job removes the extra and runs
the existing write/rebuild/recall smoke path with `PATH` containing no `rg`.
That base job verifies AC-0014. The optional job adds escape, traversal,
symlink, junction, non-regular-file, resolve-error, regex-metacharacter,
1,024-byte boundary, timeout, and max-result fixtures for AC-0025 and AC-0026.
The symlink and junction fixtures place unique content outside the docs root
and use a file-open sentinel to prove the walker neither opens nor returns it.
The dependency admission check verifies AC-0027 and stops for the Ask-first
decision when either ecosystem lacks scanner coverage.

**Approach:** declare a pinned optional evaluation dependency, adapt structured
search rows to candidate slugs, sort explicitly, and propagate `complete` and
`stop_reason` into the comparison record. Resolve each returned file before
reading it, require confinement under the canonical docs root, and reject
aliases and non-regular files. Configure traversal not to follow symlinks or
junctions and apply the root and file-type filter before the matcher can open
content; post-result validation remains defense in depth. Build literal
patterns from the existing safe token language before applying the fixed work
limits. Do not import the optional package from `src/memex`.

**Done when:** the optional integration and dependency/license audit pass while
the base environment remains fully functional without the module or CLI.

### T4: Repair benchmark semantics and add source-governed workloads

**Depends on:** T2, T3

**Spec map:** AC-0031, AC-0032, AC-0033, AC-0036, AC-0037

**Mode:** TDD plus goal-based local source import

**Tests:** `tests/unit/test_eval_workloads.py` owns
`test_realistic_queries_are_answerable_and_family_labeled`,
`test_gutenberg_import_is_bounded_offline_and_deterministic`,
`test_salesforce_fixture_is_fact_only_and_offline`, and
`test_positive_queries_require_relevance_and_family`. The tests pin all
relevant labels for repeated symptoms, session verbs, shared book
authors/titles, and product aliases; provenance fields; schema rejection;
bounded local Gutenberg import; zero network calls; and absence of committed
source bodies or book text. `tests/unit/test_weighted_retriever.py` owns
`test_eligibility_filters_apply_before_source_limit`.

Run the bounded local import from the repository root after placing the
maintainer-downloaded catalog and its provenance sidecar at the exact temporary
paths below. The command replaces only the committed fixture target after every
validation passes:

```bash
uv run python -m eval.run import-gutenberg --catalog /tmp/pg_catalog.csv.gz --provenance /tmp/pg_catalog.provenance.json --output eval/data/gutenberg-books.jsonl
```

```python
# STUB: AC-0033
import pytest

from eval.corpus import QuerySpec
from eval.workloads import validate_queries


def test_positive_queries_require_relevance_and_family() -> None:
    with pytest.raises(ValueError, match="query family"):
        validate_queries([QuerySpec("find book", ["book"], "hard", family="")])
```

**Approach:** repair the realistic queries so their visible terms determine
their labels. Add a small committed Gutenberg metadata fixture produced from
a maintainer-supplied local copy of the official weekly CSV catalog by an
explicit bounded import command. Add a
separate, hand-authored Salesforce Financial Services fact-card fixture whose
official citations are provenance, not copied content. Extend query records and
metrics for multi-relevance, nDCG@10, family, corpus, and explicit negatives.

**Done when:** both external-domain harnesses run fully offline, query labels
are answerable, the realistic ambiguity defect is covered, and all source and
filter canaries pass.

### T5: Implement genuine multi-channel reciprocal-rank fusion

**Depends on:** T2, T4

**Spec map:** AC-0011, AC-0012, AC-0013, AC-0020, AC-0021, AC-0023, AC-0035,
AC-0036

**Mode:** TDD

**Tests:** `tests/unit/test_weighted_retriever.py` owns
`test_multichannel_rrf_searches_fields_independently`,
`test_multichannel_rrf_overfetches_before_k60_fusion`, and
`test_multichannel_rrf_deduplicates_with_stable_ties`; the existing access and
`top_k` tests remain the boundary checks. `tests/unit/test_eval_candidate_behavior.py`
pins the pure `k=60` formula.

```python
# STUB: AC-0035
from pathlib import Path

from eval.weighted_retriever import WeightedLexicalRetriever


def test_multichannel_rrf_searches_fields_independently(data_dir: Path) -> None:
    result = WeightedLexicalRetriever(data_dir / "mem.db").retrieve("atlas", top_k=10)
    assert result.search_engine == "field-channel-rrf-k60"
```

**Approach:** replace the misleading single weighted FTS search in the
evaluation candidate with genuinely independent field-qualified searches and a
stable identifier channel. Fuse rank positions, not BM25 scores. Keep this in
evaluation scope until it passes every amended gate.

**Done when:** the candidate contract and trust-boundary tests pass on a real
SQLite index and its metadata precisely describes the algorithm executed.

### T6: Re-evaluate all workloads and select a candidate

**Depends on:** T4, T5

**Spec map:** AC-0001 through AC-0010, AC-0016, AC-0028 through AC-0030,
AC-0033, AC-0034, AC-0038

**Mode:** TDD plus goal-based integration

**Tests:** run the exact commands below from the repository root. The first
command evaluates baseline and every candidate against the repaired realistic,
Gutenberg, and Salesforce workloads at 10K; the second runs the selected
candidate and baseline through the 100K scale gate. `tests/unit/test_eval_selection.py`
owns `test_selection_rejects_missing_family_or_failed_workload_floor` and
`test_selection_report_includes_workload_manifest_and_ndcg`.
`tests/unit/test_retrieval_comparison.py` owns
`test_high_baseline_uses_absolute_hard_floors_and_non_regression` for the
ceiling-aware AC-0001 and AC-0002 branches.

```python
# STUB: AC-0001, AC-0002 high-baseline branch
from eval.comparison import CandidateMetrics, evaluate_candidate


def test_high_baseline_uses_absolute_hard_floors_and_non_regression() -> None:
    baseline = CandidateMetrics(
        0.940,
        0.820,
        {"overall": 0.940, "easy": 0.950, "medium": 0.930},
        100.0,
        {10_000: 40.0, 100_000: 80.0},
        True,
    )
    candidate = CandidateMetrics(
        0.935,
        0.815,
        {"overall": 0.935, "easy": 0.945, "medium": 0.925},
        80.0,
        {10_000: 40.0, 100_000: 80.0},
        True,
    )

    verdict = evaluate_candidate(baseline=baseline, candidate=candidate)

    assert verdict.gates["hard_recall_at_10"].passed is True
    assert verdict.gates["hard_mrr"].passed is True
```

```python
# STUB: AC-0034, AC-0038
from eval.selection import WorkloadMetrics, validate_workload_metrics


def test_selection_rejects_missing_family_or_failed_workload_floor() -> None:
    metrics = WorkloadMetrics(
        recall_at_10=0.89,
        mrr=0.60,
        ndcg_at_10=0.80,
        hard_recall_at_10=0.80,
        by_family={"alias": 0.90},
    )
    assert validate_workload_metrics(metrics).passed is False
```

```bash
uv run python -m eval.run selection --size 10000 --seed 42 --top-k 10 --workload realistic --workload gutenberg --workload salesforce --evidence-dir /tmp/memex-eval-10k
uv run python -m eval.run selection --promotion --workload realistic --workload gutenberg --workload salesforce --evidence-dir /tmp/memex-eval-promotion
```

**Approach:** retain one sanitized report with workload manifests and reject
the candidate on any failed constituent gate. Record repaired results as a new
benchmark series and label historical synthetic scores non-comparable.

**Done when:** one report names a same-candidate pass for every gate. If no
candidate is eligible, the report records the failed gates and this task blocks
spec completion before production promotion.

### T7: Promote the selected strategy through shared recall

**Depends on:** T6

**Spec map:** AC-0011, AC-0012, AC-0013, AC-0017, AC-0018, AC-0019, AC-0020,
AC-0021, AC-0022, AC-0023, AC-0024

**Mode:** TDD plus manual QA

**Tests:** `tests/integration/test_recall_winner.py` owns
`test_selected_ranker_wins_through_memex_and_cli` and the compatibility matrix;
its plan-owned fixture query is `atlas risk integration`. Record this literal
manual QA command and its observed first slug in
`docs/specs/quality-gated-retrieval/notes/verification-ledger.md`:

```bash
MEMEX_DATA_DIR=/tmp/memex-winner-smoke uv run memex recall "atlas risk integration"
```

**Approach:** move only the passing mechanism into the existing infrastructure
retrieval owner and leave every adapter on `Memex.recall`. A winner requiring
`rgapi` still stops for the Ask-first runtime dependency decision.

**Done when:** all compatibility and user-path checks pass through the shared
service.

### T8: Refresh durable documentation and run release gates

**Depends on:** T7

**Spec map:** Durable Outputs, AC-0039

**Mode:** TDD plus goal-based check

**Tests:** `tests/unit/test_docs_retrieval_controls.py` owns
`test_architecture_pins_retrieval_evaluation_security_controls` (AC-0039).
Run `uv run mkdocs build --strict`, `uv run ruff check .`,
`uv run ruff format --check .`, `uv run mypy src tests`, and `uv run pytest`.

```python
# STUB: AC-0039
from pathlib import Path


def test_architecture_pins_retrieval_evaluation_security_controls() -> None:
    architecture = Path("docs/architecture/overview.md").read_text(encoding="utf-8")
    assert "Retrieval evaluation security controls" in architecture
    assert "no network" in architecture.casefold()
```

**Approach:** update the guide, architecture overview, implementation notes,
research survey, and changelog when applicable. Describe only the shipped
winner and the valid benchmark series.

**Done when:** every named gate passes and closeout accounts for each durable
output row.

## Rollout

The evaluator and optional candidate land without changing production recall.
After T6 produces a passing winner, T7 changes the internal default in one
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
- External documentation changes over time and its access terms differ.
  Gutenberg imports use a maintainer-supplied copy of its official
  machine-readable catalog; Salesforce facts are curated and reviewed without
  automated retrieval. Repository evaluation code performs no network access.

## Changelog

- 2026-09-17: initial plan from the confirmed quality-gated lexical retrieval
  slice; `rgapi==0.1.22` is an optional in-process experiment, with FTS5 kept as
  the portable default and fallback until all gates pass.
- 2026-09-18: amended after the first 10K run exposed underidentified synthetic
  queries. Added answerability checks, independent Gutenberg and Salesforce
  workloads, absolute readiness floors, and genuine field-channel RRF.
