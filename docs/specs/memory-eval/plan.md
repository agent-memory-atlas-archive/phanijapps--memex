# Memory Layer Evaluation Plan

**Status:** planning only — no implementation. Shapes the next spec.

## What "testing the memory layer" means

Memex has three separable quality surfaces. Each needs its own evaluation:

1. **Retrieval quality** — when you ask, does BM25 find the right memory in the top K?
2. **Scale behavior** — what breaks (or degrades) at 10K, 100K, 1M memories?
3. **End-to-end utility** — does an agent WITH memory actually outperform one WITHOUT?

These are orthogonal: retrieval can be perfect at 100 memories but degrade at 100K (more distractors). Scale can be fast but retrieval irrelevant. Utility is the real question — the rest are diagnostics.

---

## 1. Synthetic Corpus + Ground-Truth Query Set (the foundation)

**Problem:** you can't evaluate retrieval without knowing what SHOULD be found.

**Approach:** a `memex eval generate` command that builds a deterministic synthetic corpus:

| Parameter | Values |
|---|---|
| `--size` | 100 / 1K / 10K / 100K / 1M memories |
| `--types` | distribution across entity/preference/procedure/summary |
| `--link-density` | avg [[slug]] cross-references per memory |
| `--overlap` | % of memories with similar content (tests discrimination) |
| `--staleness` | % of memories with old timestamps (tests recency decay) |
| `--status-mix` | % active/pending/archived/superseded |

Each memory gets a **known set of queries that should find it** (the ground truth). Queries are generated from the memory's content: title terms, body keywords, tag combinations, related-memory references. Some queries target exactly one memory; others target a cluster of related memories.

**Corpus shape matters more than size.** A 100K corpus of random lorem-ipsum tests nothing. The generator should produce realistic coding-agent memories: "user prefers ruff over flake8", "deploy uses blue-green", "session 2026-09-15 found auth bug in line 42".

**Deliverable:** `tests/eval/corpus/` — fixture files at each scale, deterministic (seeded RNG), with a manifest mapping query → expected slug(s) → expected rank tier (top-1 / top-5 / top-10 / miss).

---

## 2. Retrieval Quality Metrics

Run the ground-truth query set against the store at each scale:

| Metric | Definition | What it tells you |
|---|---|---|
| **Recall@K** | % of queries where the target appears in top-K (K=1,5,10) | The core "does it find it" number |
| **MRR** (Mean Reciprocal Rank) | avg(1/rank of target) | How high the right answer ranks |
| **Precision@K** | % of top-K results that are relevant | How much noise the agent sees |
| **Distractor rate** | % of results that are similar-but-wrong (from the overlap corpus) | BM25's discrimination ability |
| **Filter accuracy** | does `--type` filter exclude correctly | Correctness, not quality |

**The key experiment:** run the same query set at 100 / 1K / 10K / 100K and plot Recall@10 vs. corpus size. If BM25 quality degrades beyond ~10K, that's the evidence for shipping A1 (RRF fusion) and A2 (rank-space boosts) from `v1_enhance.md`.

**Reference point:** Letta's "Is a Filesystem All You Need?" scored **74% on LoCoMo** with plain files. If memex BM25 scores comparably, the bet is validated.

---

## 3. Scale Benchmarks (performance)

Measure at each corpus size:

| Metric | How to measure | Threshold |
|---|---|---|
| **Write latency** | time to `memex write` (p50, p99) | < 50ms at 100K |
| **Recall latency** | time to `memex recall` (p50, p99) | < 100ms at 100K |
| **Hook injection latency** | `memex hook session-start` wall time | < 500ms (agent UX) |
| **Index rebuild time** | `memex rebuild-index --force` wall time | < 30s at 100K |
| **Token-budget packing accuracy** | does the packed result stay within budget? | Always |
| **Storage per memory** | disk bytes per memory page | < 5KB |
| **FTS index bloat** | mem.db size vs. wiki dir size | < 2× wiki dir |
| **Concurrent read/write** | hook inject while write is running | No lock contention errors |

**The key experiment:** write throughput and recall latency vs. corpus size. SQLite FTS5 should handle 100K easily; 1M is where it gets interesting.

---

## 4. Consolidation Quality (LLM-dependent)

**Problem:** the LLM creates distilled nodes — are they any good?

**Approach:** a set of **known transcripts with expected outcomes**:

| Input | Expected |
|---|---|
| 5-turn transcript: "user says they prefer ruff, agent confirms, they discuss flake8 vs ruff" | 1 preference node: "user-prefers-ruff-over-flake8" |
| 20-turn transcript with tool calls, debugging, resolution | 1-2 procedure/summary nodes about the debugging approach |
| Transcript with no durable facts | 0 new nodes (zero-yield is correct here) |
| Two transcripts about the same topic | Node updated, not duplicated |
| Transcript with contradictory facts | Evolution preserved ("previously X, now Y") |

**Metrics:**
- **Distillation accuracy**: does the LLM extract the right fact?
- **Duplication rate**: % of consolidations that create a near-duplicate of an existing node
- **Zero-yield correctness**: when zero nodes is the right answer, does it produce zero?
- **Contradiction handling**: does it preserve evolution or silently overwrite?

**LLM model dependency:** run the same transcripts against each provider (codex/claude/pi) and compare. This tells you which model is best for consolidation.

---

## 5. End-to-End Agent Utility (the real test)

**Problem:** retrieval metrics don't answer "does memory actually help?"

**Approach:** a **paired benchmark** — same task, one agent with memex, one without:

```
Agent A (with memex):
  1. Session 1: user teaches facts (preferences, procedures, project knowledge)
  2. Session 2: agent starts fresh, memex injects context at session-start
  3. Agent performs task that requires the taught knowledge
  4. Score: did the agent use the right preference? Follow the right procedure?

Agent B (without memex):
  Same task, no memory, no injection.
  Score: same criteria.
```

**Task scenarios:**
- "What linter does the user prefer?" (direct recall)
- "Deploy this service" (procedure from memory)
- "Continue working on project X" (project knowledge from memory)
- "What did we decide about auth in session 3?" (episodic recall)
- Multi-session continuity: 5 sessions building on each other

**Metrics:**
- **Correct answer rate**: did the agent use the right memory?
- **Time to correct answer**: fewer turns needed with memory
- **Wrong-preference rate**: did it choose the wrong tool/approach?
- **Context injection usefulness**: did the agent acknowledge using the injected context?

This is the LoCoMo-style benchmark — the one that actually validates the product.

---

## 6. Stress Tests (failure modes)

| Test | What it probes |
|---|---|
| Write 10K memories in a burst | SQLite write contention, WAL checkpointing |
| Query with adversarial input (empty, unicode, injection, 10KB string) | Input validation at every boundary |
| Delete 50% of memories, then rebuild index | Orphan cleanup, rebuild correctness |
| Corrupt one .md file (malformed front matter) | `scan_all` error handling, partial rebuild |
| Corrupt one .meta.json (string tokens) | `/sessions` and `/tokens` hardening |
| Write a memory with a 60KB body | `max_body_chars` enforcement |
| Write 100 memories with the same title | Collision suffixing correctness |
| Concurrent `memex viz` + `memex write` | ThreadingHTTPServer + SQLite threading |

---

## Implementation Shape (when we're ready)

```
tests/eval/
├── corpus/
│   ├── generate.py          # synthetic corpus builder (seeded, deterministic)
│   ├── queries/
│   │   ├── small.yaml      # 100 memories, 500 queries, ground truth
│   │   ├── medium.yaml     # 10K memories, 5K queries
│   │   └── large.yaml      # 100K memories, 50K queries
│   └── transcripts/        # known transcripts for consolidation eval
├── benchmarks/
│   ├── retrieval.py        # Recall@K, MRR, Precision@K, distractor rate
│   ├── scale.py            # write/read/rebuild latency at each size
│   ├── consolidation.py    # LLM distillation quality vs known expectations
│   ├── e2e.py              # paired agent-with/without-memory benchmark
│   └── stress.py           # failure-mode tests
└── REPORT.md               # generated results with charts
```

CLI surface:

```bash
memex eval corpus --size 10K --seed 42       # build synthetic store
memex eval retrieval --corpus medium         # run query set, report metrics
memex eval scale --corpus large              # benchmark at scale
memex eval consolidation --transcripts tests/eval/corpus/transcripts/
memex eval e2e --scenarios tests/eval/e2e-scenarios.yaml
memex eval all --report REPORT.md            # run everything, generate report
```

---

## Sequencing

| Phase | What | Why first |
|---|---|---|
| 1 | Corpus generator + ground-truth queries | Foundation for everything else |
| 2 | Retrieval metrics (Recall@K, MRR) | Validates BM25 at scale; informs A1/A2 decisions |
| 3 | Scale benchmarks (latency/throughput) | Performance ceiling before optimization |
| 4 | Stress tests | Reliability before quality |
| 5 | Consolidation quality | LLM-dependent, slower to iterate |
| 6 | End-to-end agent utility | The real validation, needs the most setup |

---

## Prior art referenced

| System | Benchmark | Score | Relevance |
|---|---|---|---|
| Letta filesystem | LoCoMo | 74.0% | Validates plain-file BM25 approach |
| Letta leaderboard | LoCoMo | (varies by model) | Agent-side memory management |
| Hindsight | LongMemEval | (self-reported) | Server-based, for comparison |
| memorywire | 100-fact microbench | recall@5 = 1.000 | Protocol-level, tests fusion |
