# Memory optimization survey

> Discipline: applied (practitioner-pattern survey)

**Decision:** keep Markdown as the durable memory and SQLite as a disposable
index. Optimize ranking, evidence precision, and temporal correctness before
adding embeddings, a graph database, or automatic hierarchy management.

This review applies four 2026 preprints to Memex's measured
retrieval behavior:

- [Filesystem-Based Memory for LLM Agents: Organization, Evolution, and
  Sustainability](https://arxiv.org/html/2607.26637v1)
- [SodaMem: Evidence-Grounded Temporal Graph Memory for LLM
  Agents](https://arxiv.org/html/2608.08055v1)
- [memorywire: A Vendor-Neutral Wire Format for Agent Memory
  Operations](https://arxiv.org/html/2606.01138v4)
- [Memory as Ontology: A Constitutional Memory Architecture for Persistent
  Digital Citizens](https://arxiv.org/html/2603.04740v1)

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
sections, and paths stronger retrieval signals. The repaired quality-gated
benchmark confirmed this was a ranking problem, not a filesystem-layout
problem: the selected `semantic-and-fallback-fts5` ranker reached overall
Recall@10 `0.9819588`, hard Recall/MRR `0.9809524`, and hard tokens per correct
result `935.18` in the clean promotion run. [Repository evidence](specs/quality-gated-retrieval/notes/verification-ledger.md).

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

**[medium]** The first two papers use or evaluate multiple retrieval signals, but
neither demonstrates that embeddings are necessary for Memex's corpus and
constraints. The filesystem study found that adding BM25 changed cost more
reliably than correctness; SodaMem evaluates its complete multi-part system
without isolating the contribution of every retrieval tunnel.
[Filesystem paper](https://arxiv.org/html/2607.26637v1) and
[SodaMem](https://arxiv.org/html/2608.08055v1). Memex now has repository-local
evidence for the first lexical step: the clean promotion report selected
`semantic-and-fallback-fts5` over the baseline and field-fusion candidate across
repaired realistic, Gutenberg, and Salesforce workloads. Confidence for Memex's
current ranker is higher than the paper-only recommendation, but it is still a
benchmark result rather than a claim about every real user memory store.

Memex should keep the shipped SQLite FTS5 winner as the production default and
continue evaluating larger representation changes behind the same paired gates:
hard-query quality, workload floors, token cost per correct result, and p99
latency. **[inference]**

### Keep memory operations portable and provenance-aware

**[low]** `memorywire` proposes a vendor-neutral wire format for agent memory
operations. Its author-built microbench is small: 100 facts, 50 queries, and
42 labelled non-empty queries. The paper reports Recall@5 `1.0`, p50 ingest
`37.8 ms`, p50 recall `40.6 ms`, zero false positives on 8 no-match probes, and
68 adapter-conformance checks passing with 12 skipped and 0 failed. In an
adversarial rank-injection setup with two benign results and one malicious
result, adversarial RRF retained Recall@5 `1.0` with zero leak while MAX fell to
`0.5` recall and 80% attacker results. [Paper evidence](https://arxiv.org/html/2606.01138v4).
Confidence is limited by a synthetic small corpus, single-machine
self-evaluation, and incomplete LongMemEval/LoCoMo coverage.

For Memex, this supports stable memory identifiers, explicit scopes,
provenance, separate recall/no-match/latency metrics, and optional future
interoperability. It does not justify a runtime dependency, replacement store,
or protocol commitment in the production recall path. **[inference]**

### Treat governance as a product boundary, not a speed claim

**[low]** `Memory as Ontology` describes a constitutional, tiered governance
architecture for persistent digital citizens. The paper includes a preliminary
four-agent multi-week pilot and prototype, but it does not report standard
retrieval, latency, precision/recall, or comparative benchmark results.
[Paper evidence](https://arxiv.org/html/2603.04740v1). Confidence is therefore
conceptual rather than empirical.

For Memex, the transferable lesson is readable and versionable memory,
continuity evaluation, and risk-tiered governance for higher-stakes memory
changes. Memex remains Memory-as-Tool infrastructure: Markdown is the source of
truth, SQLite FTS5 is the disposable index, and this paper makes no performance
claim for the ranker. **[inference]**

## Priority for Memex

1. **Make evaluation reproducible.** Use a fresh store, surface evaluator
   failures, calculate metrics over all queries, and record the revision,
   seed, corpus shape, ranker, and metrics in machine-readable output.
2. **Keep ranker changes behind paired gates.** The first promotion selected
   `semantic-and-fallback-fts5`; future candidates should remain offline,
   same-corpus comparisons before production.
3. **Preserve retrieval economy as a gate.** Continue tracking rendered tokens
   per correct result alongside Recall@K, MRR, nDCG@10, and latency.
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

- No surveyed paper measures multi-month repository memory under repeated edits.
- The selected lexical ranker is benchmark-backed, but real-world memory stores
  may have different vocabulary, duplication, and query distributions.
- Section-level indexing may reduce context size while increasing index size
  and duplicate hits; both effects need measurement.
- The value of explicit contradiction edges over current status and validity
  fields has not been measured.
- Capture, consolidation, rebuild, and end-to-end hook costs lack stable 100K
  baselines, so they cannot yet be ranked against retrieval quality work.
