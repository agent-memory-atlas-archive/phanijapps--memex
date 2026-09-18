# Spec: Quality-gated retrieval

- **Status:** Draft
- **Owner:** Memex maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`ADR-0001`](../../adr/0001-use-markdown-pages-as-memory-source-of-truth.md), [`ADR-0002`](../../adr/0002-use-layered-package-and-shared-adapter-contracts.md)
- **Brief:** `docs/product/briefs/memory-retrieval-and-evidence.md`
- **Discovery:** none
- **Contract:** none — the existing `Memex.recall` and `RecallResult` contracts remain compatible
- **Shape:** service

> **Spec contract:** this document defines what "done" means. The implementing
> PR must match this spec, or update it. Verification must be derivable from it.
>
> **Not every section is contract.** `Boundaries`, `Testing Strategy` and
> `Acceptance Criteria` are what a completion gate reads, and an amendment
> changes them. `Objective`, `Durable Outputs`, `Follow-ons` and `Assumptions`
> are working material: they orient a reader and an author corrects them in place
> as the work teaches, without an amendment and without a review round.

## Objective

Memex returns a smaller, more accurate set of relevant memories without making
recall slower. A selected lexical ranker improves hard-query retrieval on the
seed-42 realistic corpus, reduces the estimated tokens rendered for each
correct hard-query result, and stays within the latency limits at 10,000 and
100,000 memories. The public Python, CLI, MCP, and hook recall behavior remains
compatible. SQLite FTS5 remains the portable default until one candidate passes
every gate in the same paired evaluation; `rgapi` is an optional in-process
experiment and never a required command-line tool.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| User-facing promise | Recall ranking and result compactness change when a candidate ships | `docs/gitpages/guide.md` | Memex maintainers | Updated recall description and verified commands | The guide describes the selected behavior without exposing experimental candidates as supported configuration |
| Current architecture | Retrieval ownership and the offline evaluation boundary change | `docs/architecture/overview.md` | Memex maintainers | Updated recall flow, `eval/` responsibility, search confinement, safe-query, and report-sanitization controls | The map names the shipped ranker, deterministic ordering, disposable derived state, and retrieval-specific trust boundaries |
| Decision rationale | A dependency and default-ranker decision must remain explainable | `docs/gitpages/implementation-notes.md` | Memex maintainers | Paired-result summary and dependency disposition | The note identifies the winning candidate or records that no candidate shipped |
| Reproducible evidence | The promotion gate depends on measured comparisons | Evaluation JSON emitted by `eval.run` and retained as PR evidence | Implementing contributor | Baseline and candidate configuration, source revision, environment, metrics, and gate verdict | Reviewers can reproduce the decision from the committed evaluator and the recorded command; generated corpora and reports are not committed |
| Release history | Applicable only when the default ranker changes | `docs/product/changelog.md` | Memex maintainers | One user-visible retrieval entry | Closeout verifies an entry exists only if the default changed |

## Boundaries

### Always do

- Compare each candidate with the shipped baseline on fresh, isolated stores
  generated with the same seed, corpus size, query set, `top_k`, token budget,
  process, and isolated runner environment.
- Apply the accuracy, token-efficiency, and speed gates to one candidate and
  reject the candidate when any gate fails; a blended score cannot compensate
  for a failed gate.
- Preserve deterministic rank order with a stable slug tie-break, all existing
  recall filters, access-statistic side effects, and the public page-level
  `RecallHit` and `RecallResult` shapes.
- Treat a timed-out or truncated candidate search as incomplete and ineligible
  for promotion; never score partial results as a complete run.
- Confine every candidate file to the resolved `MEMEX_DATA_DIR/docs` root,
  preserve the existing safe query-token boundary, and emit only bounded,
  sanitized evaluation diagnostics.
- Run every evaluation with a fresh `MEMEX_DATA_DIR` outside the developer's
  real `~/.memex` and leave Markdown pages as the source of truth.

### Ask first

- Promote `rgapi`, or any other new package, from an optional experiment to a
  required runtime dependency.
- Change a documented Python, CLI, MCP, hook, configuration, or result-shape
  contract.
- Relax a corpus, accuracy, token, latency, determinism, portability, or
  compatibility gate.
- Accept degraded dependency-vulnerability coverage when a Python or Rust SCA
  scanner cannot inspect the pinned dependency tree.
- Add a persistent field, index schema, top-level package, storage engine, or
  network service.

### Never do

- Never require an `rg` executable or spawn a search subprocess on the recall
  path.
- Never make `rgapi` mandatory while the base Memex installation supports
  platforms for which the pinned release has no wheel and a source build needs
  an undeclared Rust toolchain.
- Never make SQLite or an experimental search result authoritative over the
  Markdown page that produced it.
- Never introduce embeddings, a cross-encoder, an LLM call, a graph database,
  a hosted search service, or a background daemon in this slice.
- Never expose an experimental ranker as user-selectable production
  configuration before it passes the promotion gate.
- Never include memory content, credentials, raw non-generated queries,
  absolute or user-specific paths, or stack traces in retained reports.

## Testing Strategy

- **Paired metric and gate logic (AC-0001, AC-0002, AC-0003, AC-0004,
  AC-0005, AC-0006): TDD.** Unit tests use
  fixed baseline/candidate records at the exact threshold and immediately on
  each failing side, so every comparison can independently turn red.
- **Reproducible corpus evaluation (AC-0007, AC-0008, AC-0009, AC-0010,
  AC-0028): goal-based integration.**
  The offline evaluator runs baseline and candidate against fresh seed-42
  stores because accuracy, rendered-token cost, latency, and completeness are
  observable only across corpus generation, indexing, retrieval, and report
  serialization.
- **Ranking and compatibility (AC-0011, AC-0012, AC-0013, AC-0020, AC-0021,
  AC-0022, AC-0023, AC-0024): TDD plus integration.** Pure
  fusion and tie-breaking fixtures pin deterministic order; the existing
  retriever and facade suites exercise the filter matrix, side effects, and
  output datatypes through the real SQLite index.
- **Optional Python integration (AC-0014, AC-0015, AC-0016, AC-0025,
  AC-0026, AC-0027): goal-based packaging and integration.** Base-install tests run without `rgapi`; the optional path runs
  only where the pinned package is available and proves structured in-process
  search without invoking a child process.
- **User path (AC-0017, AC-0018, AC-0019): manual QA backed by an end-to-end
  command.** An
  isolated `memex recall` invocation confirms that the selected default returns
  ranked output through the shipped CLI without exposing experimental controls.

The sibling plan owns exact stubs and command lines.

## Acceptance Criteria

- [ ] **AC-0001.** On the 10,000-memory seed-42 realistic corpus, the selected
      candidate's hard-query Recall@10 is at least 0.05 higher than its paired
      baseline; for example, a baseline of 0.320 requires at least 0.370. The
      candidate-selection gate enforces the absolute difference and rejects
      0.369.
- [ ] **AC-0002.** On that same paired run, the selected candidate's hard-query
      MRR is at least 0.05 higher than baseline; for example, a baseline of
      0.400 requires at least 0.450. The candidate-selection gate enforces the
      absolute difference and rejects 0.449.
- [ ] **AC-0003.** On that same paired run, the candidate's Recall@10 regression
      from baseline is no greater than 0.005 for every member of the closed set
      `{overall, easy, medium}`; a 0.005 regression passes and 0.0051 fails.
- [ ] **AC-0004.** On that same paired run, the candidate's rendered-context
      token cost per correct hard query is at most 80% of baseline. The metric
      packs each query's ordered `top_k=10` hits with
      `context_injection.pack_to_budget(..., max_tokens=4096)`, renders the
      packed `RecallResult` with `context_injection.format_context_block`, sums
      `context_injection.estimate_tokens` over those rendered strings, and
      divides by the count of hard queries whose expected page remains in the
      packed context. The gate rejects a run with zero correct hard queries
      before division.
- [ ] **AC-0005.** Candidate recall p99 is below 50 ms at 10,000 memories and
      below 100 ms at 100,000 memories, measured from immediately before the
      shared recall service call to immediately after its result returns,
      excluding corpus generation and index construction. The sample is every
      query in the generated manifest; p99 is the nearest-rank value
      `sorted(raw_latency_ms)[ceil(0.99 * n) - 1]`, computed before display
      rounding. The latency gate rejects equality with either bound.
- [ ] **AC-0006.** At each measured corpus size in `{10_000, 100_000}`, the
      candidate p99 is no more than 110% of its paired baseline p99. The paired
      latency gate rejects the first size whose ratio exceeds 1.10.
- [ ] **AC-0007.** One candidate passes AC-0001 through AC-0006 in a single
      paired evaluation before it is selected; the report names that candidate
      and emits a failing overall verdict when any constituent gate fails.
- [ ] **AC-0008.** Repeating a seed-42 quality run with identical inputs emits
      identical ordered slugs and quality/token metrics after volatile timing
      and run metadata are excluded.
- [ ] **AC-0009.** Every paired report records the source revision and dirty
      flag, Python and Memex versions, operating-system family and CPU
      architecture,
      corpus generator and seed, requested and generated corpus sizes, query
      count, `top_k`, token budget, renderer and token-estimator identities,
      percentile method, ranker identity and parameters, per-gate values, and
      the overall verdict. Environment metadata is limited to operating-system
      family and CPU architecture; the report excludes hostnames, device names,
      usernames, profile paths, and user-specific filesystem paths.
- [ ] **AC-0010.** The evaluator refuses a non-empty caller-supplied data
      directory without deleting or changing any entry, while an empty
      directory and the evaluator-created temporary directory both complete.
- [ ] **AC-0011.** For identical indexed pages and recall arguments, the shipped
      candidate makes the same per-page eligible/ineligible decision as the
      baseline for every member of `{node_type, time_range, all-tags matching,
      include_expired, include_inactive}`. Ranked membership and order may
      differ after this eligibility step.
- [ ] **AC-0012.** Every returned hit has a unique slug after multiple candidate
      sources contribute the same page.
- [ ] **AC-0013.** One explicit recall increments `access_count` exactly once
      for every returned page and never for an unreturned page, including when
      multiple candidate sources contribute the same page.
- [ ] **AC-0014.** A base installation with no `rgapi` module imports Memex and
      completes write, rebuild, and recall through SQLite FTS5 without an
      `rg` executable on `PATH`.
- [ ] **AC-0015.** The optional `rgapi==0.1.22` experiment completes its search
      integration fixture while a child-process sentinel records zero process
      spawn attempts.
- [ ] **AC-0016.** A timeout, `max_results` stop, or other incomplete `rgapi`
      result is marked incomplete in the evaluation report and receives a
      failing promotion verdict even when its observed quality and latency
      values otherwise pass.
- [ ] **AC-0017.** With an isolated store containing one relevant and one
      irrelevant page, `memex recall <query>` returns the relevant page first
      through the shipped CLI.
- [ ] **AC-0018.** The shipped `memex recall --help` and recall output expose no
      experimental-backend selector or diagnostic.
- [ ] **AC-0019.** A successful isolated `memex recall <query>` invocation exits
      zero.
- [ ] **AC-0020.** Every returned result uses consecutive one-based ranks after
      candidate fusion, deduplication, and `top_k` limiting.
- [ ] **AC-0021.** One hundred repeated production-path calls over a tie fixture
      produce one identical slug order whose final tie-break is ascending slug.
- [ ] **AC-0022.** A committed winner-discriminating fixture for which the
      paired report's selected candidate and baseline produce different first
      slugs returns the selected candidate's first slug through both
      `Memex.recall` and `memex recall`.
- [ ] **AC-0023.** The shipped candidate preserves the existing `top_k`
      validation bounds: 1 and 100 are accepted, while 0 and 101 raise the
      existing `ValueError`.
- [ ] **AC-0024.** The production ranker identity observed by the
      winner-discriminating integration test equals the selected candidate
      identity in the paired promotion report.
- [ ] **AC-0025.** The optional file-search candidate admits only relative
      results that resolve to regular `.md` files under the resolved
      `MEMEX_DATA_DIR/docs` root. Absolute results, `..` traversal, symlink or
      junction escapes, non-regular files, and `Path.resolve()` failures
      (`OSError` or `RuntimeError`) mark the candidate incomplete and make its
      promotion verdict fail without exposing the rejected path.
- [ ] **AC-0026.** The optional candidate derives its pattern only from the
      same lower-case `[a-z0-9]+` tokens accepted by the FTS5 path and
      literal-escapes every token before regex compilation. Compilation is
      refused before search when the joined UTF-8 pattern first exceeds 1,024
      bytes; search uses `timeout_ms=100` and `max_results=10_000`, and either
      limit marks the result incomplete under AC-0016.
- [ ] **AC-0027.** Before the optional dependency lands, its admission record
      contains the intended PyPI identity, exact version and lockfile integrity,
      publisher provenance, maintenance evidence, direct and transitive
      licenses, and Python and embedded-Rust vulnerability-scan results. A
      missing scanner or uninspectable dependency tree blocks admission unless
      the owner explicitly approves the degraded coverage under `Ask first`.
- [ ] **AC-0028.** Every retained evaluator failure uses one category from
      `{dependency_unavailable, invalid_query, path_rejected,
      incomplete_search, measurement_failed, report_invalid}` and a bounded
      non-identifying stop reason. A canary fixture proves the report contains
      no memory content, credentials, raw non-generated query, absolute or
      user-specific path, hostname, device name, username, profile path, or
      stack trace.

## Follow-ons

- Memex maintainers: `docs/product/briefs/memory-retrieval-and-evidence.md` —
  derive compact section evidence with page-and-section provenance after this
  ranker slice ships.
- Memex maintainers: `docs/product/briefs/memory-retrieval-and-evidence.md` —
  specify temporal fact lifecycle and contradiction handling separately.
- Memex maintainers: `docs/product/briefs/memory-retrieval-and-evidence.md` —
  specify identity-aware, evidence-preserving consolidation separately.

## Assumptions

- Technical: Memex runs on Python 3.12+, uses `uv`, and treats its package as
  operating-system independent (`pyproject.toml`).
- Technical: Markdown is authoritative and SQLite FTS5 is a disposable derived
  index ([ADR-0001](../../adr/0001-use-markdown-pages-as-memory-source-of-truth.md)).
- Technical: recall is owned by `Memex` and `BM25Retriever`, and `eval/` is
  offline development tooling rather than package runtime
  (`docs/architecture/overview.md`, `src/memex/application/memory.py`,
  `src/memex/infrastructure/bm25_retriever.py`).
- Technical: `rgapi` 0.1.22 is an Apache-2.0 CPython extension that uses
  ripgrep's `ignore`, `grep-regex`, and `grep-searcher` crates, returns
  structured rows, has unordered parallel traversal, and exposes incomplete
  timeout results
  ([PyPI contract](https://pypi.org/project/rgapi/),
  [Cargo manifest](https://raw.githubusercontent.com/AnswerDotAI/rgapi/v0.1.22/Cargo.toml)).
- Technical: `rgapi` 0.1.22 publishes Python 3.12 wheels for Linux x86-64,
  Linux AArch64, and Apple Silicon, but not Windows or Intel macOS; source builds
  require Rust 1.91 and the Python package also depends on `fastcore`
  ([PyPI release metadata](https://pypi.org/pypi/rgapi/0.1.22/json),
  [Python manifest](https://raw.githubusercontent.com/AnswerDotAI/rgapi/v0.1.22/pyproject.toml)).
- Product: accuracy and token efficiency are co-primary outcomes, with speed as
  a hard constraint; the same candidate must pass every gate
  (`docs/product/briefs/memory-retrieval-and-evidence.md`).
- Product: `rgapi==0.1.22` is an optional experimental candidate, FTS5 remains
  the default and fallback, and promotion additionally requires a portable
  packaging decision (user confirmation 2026-09-17).
- Process: spec scope and implementation strategy receive separate human
  approvals after independent review (`docs/CONVENTIONS.md`, `new-spec` and
  `work-loop` procedures).
