# Memory optimization survey

> Discipline: applied (practitioner-pattern survey)

**Decision:** keep Markdown as the durable memory and SQLite as a disposable
index. Optimize ranking, evidence precision, and temporal correctness before
adding embeddings, a graph database, or automatic hierarchy management.

This review applies two July–August 2026 preprints to Memex's measured
retrieval behavior:

- [Filesystem-Based Memory for LLM Agents: Organization, Evolution, and
  Sustainability](https://arxiv.org/html/2607.26637v1)
- [SodaMem: Evidence-Grounded Temporal Graph Memory for LLM
  Agents](https://arxiv.org/html/2608.08055v1)

## Findings that apply now

### Optimize retrieval economy, not directory depth

**[low]** Organized filesystem stores reduced search cost on the larger
PersonaMem conditions, but no organization strategy improved correctness
consistently. The paper reports roughly half the retrieval cost for reorganized
stores at 32K and 128K scale, while accuracy varied by task and preservation
policy. The result supports measuring bytes or tokens returned per correct hit;
it does not support automatic folder expansion as a quality strategy.
[Paper evidence](https://arxiv.org/html/2607.26637v1). Confidence is limited by
one preprint and short experimental histories.

Memex should keep its shallow type directories and make titles, tags, body
sections, and paths stronger retrieval signals. The existing realistic corpus
already shows the relevant problem: at 10,000 pages Recall@10 is 68.9%, but
hard-query Recall@10 is 32.0%. This is a ranking failure, not a filesystem
layout failure. [Repository evidence](specs/memory-eval/realistic-corpus-plan.md).

### Preserve claims when consolidating

**[low]** Reorganization can silently discard details unless the manager
is explicitly required to retain every fact. Condensation helped one evaluated
condition and substantially hurt others, so lossy summarization is not a safe
default. [Paper evidence](https://arxiv.org/html/2607.26637v1). Confidence is
limited by one preprint and task-dependent outcomes.

For Memex, consolidation should retain source evidence, update an existing
identity instead of producing duplicates, and mark old claims as superseded
rather than deleting them. Those invariants should be evaluated before prompt
or scheduling optimizations. **[inference]**

### Add temporal and provenance semantics incrementally

**[low]** SodaMem's most transferable mechanism is a typed fact with a
source span, mention time, occurrence or validity time, and an explicit
relationship to replaced or contradictory facts. Its retrieval combines
lexical, semantic, graph, and temporal signals, then applies time as a soft
bonus unless the question requires a hard constraint.
[Paper evidence](https://arxiv.org/html/2608.08055v1). Confidence is limited by
a single preprint, self-grading, non-uniform baseline comparisons, and reported
answer costs that exclude ingestion and judging.

Memex already has the compatible foundations: Markdown provenance, `occurred_at`,
validity windows, status, wikilinks, and FTS5. The next useful increment is
source-section evidence and explicit supersession or contradiction metadata,
not a second canonical store. **[inference]**

### Benchmark lexical fusion before adding dense retrieval

**[low]** Both papers use or evaluate multiple retrieval signals, but
neither demonstrates that embeddings are necessary for Memex's corpus and
constraints. The filesystem study found that adding BM25 changed cost more
reliably than correctness; SodaMem evaluates its complete multi-part system
without isolating the contribution of every retrieval tunnel.
[Filesystem paper](https://arxiv.org/html/2607.26637v1) and
[SodaMem](https://arxiv.org/html/2608.08055v1). Confidence is limited by the
lack of a Memex-specific ablation.

Memex should first compare field-weighted BM25, title/body/tag reciprocal-rank
fusion, query backoff, and deterministic temporal or importance boosts. Keep
the shipped ranker unchanged until paired runs improve hard-query Recall@K and
MRR without unacceptable latency or context growth. **[inference]**

## Priority for Memex

1. **Make evaluation reproducible.** Use a fresh store, surface evaluator
   failures, calculate metrics over all queries, and record the revision,
   seed, corpus shape, ranker, and metrics in machine-readable output.
2. **Run paired lexical ranker experiments.** Compare the current OR-joined
   page-level BM25 baseline with per-field fusion and deterministic boosts.
3. **Measure retrieval economy.** Add rendered context bytes or estimated
   tokens per correct result alongside Recall@K, MRR, and latency.
4. **Make consolidation evidence-preserving.** Test duplicate rate, claim
   retention, contradiction handling, prompt size, and idempotent updates.
5. **Prototype section-level evidence.** Derive heading and source-span cards
   from Markdown while leaving pages authoritative and the index rebuildable.

## Explicit non-goals

- Do not replace Markdown with a graph database.
- Do not add mandatory embeddings or a hosted service.
- Do not let an LLM reorganizer delete or silently condense durable claims.
- Do not treat SodaMem's 92.8% headline as directly comparable to Memex; its
  best-of-three, self-graded protocol and excluded ingestion cost prevent that.

## Known unknowns

- Neither paper measures multi-month repository memory under repeated edits.
- Memex has no paired ranker ablation yet, so the best lexical fusion is
  unknown.
- Section-level indexing may reduce context size while increasing index size
  and duplicate hits; both effects need measurement.
- The value of explicit contradiction edges over current status and validity
  fields has not been measured.
- Capture, consolidation, rebuild, and end-to-end hook costs lack stable 100K
  baselines, so they cannot yet be ranked against retrieval quality work.
