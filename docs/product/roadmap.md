# Roadmap

This roadmap expresses direction, not release commitments. Shipped behavior is
recorded in [`changelog.md`](changelog.md); detailed enhancement evidence and
sequencing live in [`../v1_enhance.md`](../v1_enhance.md).

**Last updated:** 2026-09-17

**Review cadence:** quarterly

**Next review:** 2026-12-16

## Now

- **Stabilize the 0.2 line across real harness sessions.** Keep transcript
  capture, compaction handling, session headers, token accounting, and
  repository attribution correct for pi, Claude Code, and Codex. The latest
  work is exercised by harness-specific parser and lifecycle tests.
- **Measure lexical retrieval before changing it.** Use the offline realistic
  corpus and scale runner under `eval/` to establish Recall@K, MRR, precision,
  latency, and difficult-query failure modes. The current analysis is in
  [`../specs/memory-eval/`](../specs/memory-eval/).
- **Keep shipped guardrails coherent.** Maintain token-budget injection,
  approval, provenance, secret scrubbing, status lifecycle, and health
  reporting as one supported contract. The shipped contract is
  [`../specs/v1-guardrails/spec.md`](../specs/v1-guardrails/spec.md).

## Next

- **Improve BM25 ranking only where the evaluation justifies it.** Trial
  per-field reciprocal-rank fusion and deterministic rank-space boosts against
  the labelled corpus before changing defaults. These are A1 and A2 in the
  enhancement signals.
- **Make consolidation more evidence-preserving.** Explore evidence-backed
  pages, delta updates, scoped staleness, and repository-aware consolidation
  without introducing a background daemon. These are B1–B3 and B7.
- **Complete the release record.** Tag releases, keep this changelog current,
  and align shipped spec lifecycle fields with the code already in the package.

## Later

- Provenance-driven quarantine and guarded bulk expiry.
- Memory-use effectiveness metrics beyond access counts.
- Git-history seeding when it can be made idempotent and repository-scoped.
- A documented harness-quirk matrix backed by executable compatibility tests.
- A small, budgeted always-on memory block if evaluation shows it improves
  agent outcomes without adding distracting context.

## Not in scope

- Vector embeddings, cross-encoder reranking, or a graph database.
- A hosted service, multi-tenant synchronization, or a mandatory daemon.
- Repository-controlled enablement of capture, injection, or consolidation.
- Automatic deletion based on a content classifier; suspicious memories must
  remain inspectable and recoverable.
- Replacing coding harnesses with a general agent runtime.

## Maintenance

Maintainers review this file at least every 90 days. A priority moves to a
feature spec before implementation when it changes a public contract or durable
representation. Completed work leaves the roadmap and enters the changelog;
decision rationale goes to an ADR when the trade-off will matter later.
