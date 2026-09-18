# Brief: Memory retrieval and evidence quality

- **Slug:** `memory-retrieval-and-evidence`
- **Status:** Draft
- **Received:** 2026-09-17
- **Owner:** Memex maintainers
- **Initiative:** `ini-001`

## Outcome

As a Memex store grows and its facts change over time, coding agents retrieve
the smallest useful set of current, source-backed memories accurately and
quickly, without losing important detail during consolidation. Memex remains
local-first: Markdown pages are authoritative, and every search or relationship
structure remains a disposable derivative.

## Success measures

- **Accuracy gate:** on the 10,000-memory seed-42 realistic corpus, a selected
  ranker improves hard-query Recall@10 by at least 5 percentage points and hard
  MRR by at least 0.05. Overall, easy, and medium Recall@10 may not regress by
  more than 0.5 percentage points in the same paired clean-store run.
- **Token-efficiency gate:** the same candidate reduces rendered context tokens
  per correct hard-query result by at least 20% without relaxing the accuracy
  gate or omitting provenance required to verify the hit.
- **Speed gate:** the same candidate keeps retrieval p99 below 50 ms at 10,000
  memories and below 100 ms at 100,000 memories, and no measured scale may be
  more than 10% slower than its paired baseline.
- A candidate becomes the default only when it passes the accuracy,
  token-efficiency, and speed gates together. A gain in one dimension cannot
  compensate for failure in another.
- Recall identifies the source page and section for every returned evidence
  unit while preserving the existing page-level public contract.
- Time-sensitive fixtures prefer the active fact and retain access to the
  superseded or contradictory source when explicitly requested.
- Repeated consolidation of unchanged input produces no duplicate page and no
  unintended content churn; claim-retention fixtures preserve all cited facts.

## Scope

### In scope

- Compare page-level BM25 with title/body/tag field weighting, reciprocal-rank
  fusion, query backoff, and deterministic rank-space boosts.
- Record paired baseline and candidate results, including Recall@K, MRR,
  latency, and rendered-context cost, before changing the shipped default.
- Derive compact evidence units from Markdown headings or source spans and
  return their page and section provenance.
- Represent occurrence or validity time, active or superseded status, and
  contradiction or update relationships in durable Markdown fields. SQLite may
  derive indexes and adjacency from those fields but cannot become a second
  source of truth.
- Make consolidation identity-aware, idempotent, evidence-preserving, and
  scoped to relevant existing memories instead of the entire corpus.
- Add deterministic fixtures for stale preferences, contradictions, repeated
  consolidation, evidence retention, and context-budget behavior.
- Update the shared Python API, CLI, MCP, hooks, documentation, and verification
  behavior together wherever a selected slice changes their common contract.

### Non-goals

- Replacing Markdown pages with SQLite, a graph database, or another canonical
  store.
- Mandatory vector embeddings, cross-encoder reranking, a hosted service, or a
  background daemon.
- Automatic directory-tree reorganization as a retrieval-quality strategy.
- Destructive compression, deletion, or silent rewriting of source facts.
- Treating either reviewed paper's headline accuracy or cost as directly
  comparable to Memex's evaluator.
- Optimizing transcript capture, index rebuilds, or hook scheduling unless a
  measured result makes one of them necessary for this outcome.

## Constraints and delivery appetite

- Preserve ADR-0001: Markdown is authoritative, while FTS5 rows, section
  evidence, link adjacency, and temporal indexes are rebuildable. Any temporal
  relationship required for correct behavior after an index rebuild must be
  recoverable from Markdown.
- Prefer deterministic SQLite and standard-library mechanisms. A new runtime
  dependency or product-boundary change requires a separate decision.
- Keep stored memories untrusted. Validate query, metadata, path, source-span,
  and relationship input at their boundaries, and never log memory contents.
- Preserve documented public APIs unless a separately versioned spec approves
  an intentional break.
- Benchmark candidates behind an experimental path. Do not change the default
  ranker merely because an approach is promising in another system.
- Treat accuracy and token efficiency as co-primary outcomes, with speed as a
  hard constraint. Reject candidates that materially trade one away for
  another, even when a blended score would improve.
- Deliver in independently testable slices. Stop or revise an approach when it
  fails its paired quality, context-cost, or latency gate rather than absorbing
  speculative infrastructure.

## Assumptions and risks

- **Assumption:** Memex's main measured retrieval weakness is ranking, because
  the current corpus often finds the right page below rank one and hard-query
  performance falls fastest at scale.
- **Assumption:** Page headings and existing front matter contain enough
  structure to derive useful evidence units without an LLM ingestion step.
- **Risk:** Field fusion can over-rank titles and tags while further burying the
  body passages needed for reasoning questions.
- **Risk:** Section indexing can shrink returned context but inflate the index,
  produce duplicate hits from one page, and complicate page-level filters.
- **Risk:** Temporal bonuses can make recent but weak evidence outrank durable
  facts. Time remains a soft signal unless an explicit validity filter applies.
- **Risk:** Provenance and relationship metadata can become authoritative only
  in SQLite. Anything required after rebuild must be recoverable from Markdown.
- **Risk:** Consolidation changes cross an LLM and file-write boundary, where a
  malformed response or identity error can lose claims or create duplicates.

## Delivery shape

The likely boundaries are ranker evaluation and selection, context and evidence
units, temporal fact lifecycle, and consolidation correctness. These are
candidate boundaries only. `author-delivery-brief continue` must confirm the
minimum independently shippable slices before any spec enters the Spec map.

## Governance references

- [`ADR-0001`](../../adr/0001-use-markdown-pages-as-memory-source-of-truth.md)
  fixes Markdown as the source of truth and SQLite as disposable derived state.
- [`ADR-0002`](../../adr/0002-use-layered-package-and-shared-adapter-contracts.md)
  requires shared domain and application behavior across adapters.
- [`ADR-0003`](../../adr/0003-use-one-llm-port-with-api-and-harness-providers.md)
  constrains consolidation to the existing application-level LLM port.
- [`ADR-0004`](../../adr/0004-require-user-scope-enablement.md) prevents
  repository content from enabling capture, injection, or consolidation.

## Source provenance

- [`memory-optimization-survey.md`](../../memory-optimization-survey.md) at Git
  commit `e8ba2701dfaac6159ad0971753a3d7b1bed53f1b` applies the two research
  papers to Memex and records confidence limits and known unknowns.
- [`realistic-corpus-plan.md`](../../specs/memory-eval/realistic-corpus-plan.md)
  records the seed-42 1,000- and 10,000-memory baseline and the ranking failure
  on hard queries.
- [`v1_enhance.md`](../../v1_enhance.md) defines the existing A1/A2 and B1-B3/B7
  enhancement signals that overlap this outcome.
- [Filesystem-Based Memory for LLM Agents](https://arxiv.org/html/2607.26637v1)
  is the source for retrieval-economy and preservation observations.
- [SodaMem](https://arxiv.org/html/2608.08055v1) is the source for provenance,
  temporal fact, supersession, contradiction, and multi-signal retrieval ideas.

## Spec map

No delivery slices have been confirmed.

## Ready gaps

No canonical Ready gaps remain. The initial success thresholds are binding and
may be tightened when comparison evidence warrants it; they cannot be weakened
merely to admit a candidate. Delivery-slice selection remains a separate human
decision after the Ready transition, so no spec is authorized by this Draft.
