# Memex v1 Enhancement Signals

**Branch:** `feature/v1-signals` · **Status:** proposal (no code on this branch)
**Sources explored (via three parallel research subagents):**

1. **Hindsight** (vectorize-io) — read from a full local clone: README, 12 developer docs, the 853-line coding-agents integration doc. 52 features inventoried. Evidence quality: **strong** (source files read directly).
2. **Letta research** (letta.com/research) — the full 2023–2026 research index (16 items) fetched; linked posts are model knowledge, labeled as such. Evidence quality: **medium**.
3. **memorywire** (arXiv:2606.01138v4, "A Vendor-Neutral Wire Format for Agent Memory Operations") — full paper HTML read end-to-end. Single-author v0.x preprint, self-evaluated; numbers are directional, not authoritative. Evidence quality: **medium**.

These are **not apples-to-apples**: Hindsight is a PostgreSQL+pgvector *server* product; Letta is a memory platform + research lab; memorywire is a wire-format spec paper. Memex is a local-first, single-user, filesystem-truth, BM25-only harness layer. The filter applied throughout: *does this survive in a world with no vectors, no server, no daemon, and deterministic CI?*

---

## 0. Validation signals — nothing to build, but load-bearing

These confirm memex's bets and should be cited, not implemented:

- **"Is a Filesystem All You Need?"** (Letta, Aug 2025): Letta Filesystem scored **74.0% on LoCoMo** by storing conversational histories in a file — *"beating out specialized memory tool libraries."* The plain-files-with-real-format bet is externally validated.
- **Context Repositories** (Letta, Feb 2026): Letta Code converged on **git-based, versioned memory for coding agents** — memex's design space. Mine their conventions as they publish.
- **memorywire's RRF adversarial result**: rank-based fusion (RRF, k=60) stayed at recall@5 = 1.0 / leak 0.0 under a poisoned rank-0 source, while score-MAX collapsed to 0.500 with 80% leak. Rank space is robust; score maxima are hijackable. Any future memex fusion must be rank-based.
- **Hindsight's keyword honesty**: their default "BM25" backend is actually TF-IDF, disclosed in docs. Memex's FTS5 is *true* BM25 — an accidental edge worth stating in docs.

---

## A. Retrieval quality (BM25-only upgrades)

### A1. Per-field RRF fusion (k=60) — `M`
**Source:** memorywire §3.5 (intra-store pattern), Hindsight retrieval.md.
**Signal:** run BM25 separately over title / body / tags, fuse the three ranked lists with Reciprocal Rank Fusion (`k=60`), which needs no score calibration because it consumes only ranks — deterministic, vector-free, CI-stable. memorywire's own recall path does exactly this inside a single store.
**Proposal:** extend `BM25Retriever` with per-field FTS5 columns (already separate in `wiki_fts`), compute three ranks, RRF-fuse. Keep single-field BM25 as fallback. A/B on a labelled query fixture set (see F3) before switching the default.

### A2. Deterministic multiplicative boosts — `M`
**Source:** Hindsight retrieval.md (fully-specified math).
**Signal:** `final = bm25_rank × recency(α) × proof_count(α)` applied in **rank space**, multiplicative-not-additive ("a weak-but-recent memory must not leapfrog a strong one"), with all constants documented; `query_timestamp` passed explicitly for determinism.
**Proposal:** rank-space boosts over the fused list from A1 using fields memex already has: `last_access` recency (365-day linear decay, clamped), `access_count`/proof-count (`0.5 + ln(n)/10`), and `importance`. Anchor time to an explicit `query_timestamp` param so CI is byte-stable.

### A3. Token-budget recall contract — `S`
**Source:** Hindsight retrieval.md.
**Signal:** the retrieval contract is `max_tokens` (default 4096), not top-k: *metadata is free; only memory text counts; packing skips a too-long hit and continues; if nothing fits, the top-1 result is returned whole.*
**Proposal:** add `max_tokens` to `recall` and the hook injection path (MCP tool + `memex hook prompt`), packing §5.4 context blocks to a budget. This is index-agnostic and precisely right for context-window injection.

### A4. No-match honesty floor — `S`
**Source:** memorywire §5.1 lesson (0/8 no-match probes confidently filled).
**Signal:** retrieval-for-injection needs an explicit "return nothing" path; a weak match beats no match in today's naive top-k.
**Proposal:** a minimum BM25-rank floor for *hook injection only* (agent-initiated `recall` stays unfloored). Weak matches inject silence rather than noise.

---

## B. Page semantics & consolidation quality

### B1. Evidence-backed pages — `M`
**Source:** Hindsight observations.
**Signal:** consolidated beliefs carry **exact supporting quotes, a proof count, and source references**; they are *refined, never silently overwritten*; contradictions recorded as evolution ("previously X, now Y"), raw sources always preserved underneath.
**Proposal:** extend the consolidation prompt + `WriteInput` with `evidence: [{quote, source_ref}]` and `proof_count`; the §11 prompt gains the refine-not-overwrite rule and contradiction-as-evolution format. Stored in front matter; surfaced in recall output.

### B2. Delta-mode consolidation refresh — `M`
**Source:** Hindsight mental-models (delta refresh).
**Signal:** told to "preserve the unchanged parts," an LLM **will still drift** — Hindsight's answer is delta mode: "apply only the changes the new knowledge implies, leaving everything else physically untouched." Byte-stable except intended edits — the most CI-friendly property a page can have.
**Proposal:** consolidation default becomes delta: the prompt receives the existing page + new episode facts and outputs *only changed lines* (or a patch); unchanged pages are not rewritten at all (skip via B3 staleness). `memex verify` gains a "consolidation didn't churn unchanged pages" check.

### B3. Scope-guarded staleness & refresh — `M`
**Source:** Hindsight mental-models refresh triggers.
**Signal:** pages rebuild only when *something in their own scope* changed ("a busy bank does not cause unrelated models to churn"); staleness is a computed signal; bursts fold into one rebuild (`min_refresh_interval`).
**Proposal:** front-matter `scope:` (linked slugs / tags / git paths); `is_stale` computed by comparing page `updated` against its scope's latest changes; consolidation processes only stale pages. Kills the whole-store re-distillation cost.

### B4. Dual timestamps: `occurred_at` vs `recorded_at` — `S`
**Source:** Hindsight retain.
**Signal:** every fact tracks *when it happened* and *when it was learned*, separately — enables "what did we believe in June" and recency ranking that doesn't confuse old events with old writes.
**Proposal:** add optional `occurred_at` to front matter (memex has `created/updated`; the semantic distinction is new). Transcript capture fills both for free (session time vs event time).

### B5. Status lifecycle: active → superseded/archived — `S`
**Source:** Hindsight invalidate (archive-not-delete, reversible); memorywire forget/merge semantics.
**Signal:** invalidated memories move out of the active set so *recall never needs a skip filter*; fully reversible; observations can't be hand-curated (curate sources, derived regenerates).
**Proposal:** front-matter `status: active|superseded|archived`; recall filters non-active by default; `memex forget --mode archive`; a `memex merge A B` that supersedes B into A with history preserved. Markdown *is* the archive.

### B6. Perspective typing: `world` vs `experience` — `S`
**Source:** Hindsight fact typing (decided by who spoke).
**Signal:** one front-matter dimension separating *about-the-project facts* from *what-the-agent-did* — cheap, useful filter at recall ("what do I know" vs "what have I done").
**Proposal:** optional `perspective: world|experience` front matter; capture fills it from turn roles; recall filter flag.

### B7. Consolidation scope = per-repo, worktree-aware — `M`
**Source:** Hindsight observation scopes (`shared` default with published rationale) + bank identity via `git rev-parse --git-common-dir`.
**Signal:** *"Which agent happened to be typing does not change whether a convention is true"* — one belief set per repo, never per-session; worktrees share the main checkout's identity.
**Proposal:** memex scoping: repo identity = common-dir git root; pages consolidated per-repo (a `repo:` tag on distilled pages); `harness install` records it. Blocks the two-blind-copies failure mode.

---

## C. Governance & provenance

### C1. Pending-status HITL staging — `M`
**Source:** memorywire HITL governance channel.
**Signal:** writes can stage as *pending* — excluded from recall until a human approves; the diff is the approval surface.
**Proposal:** consolidation (and optionally agent writes) can land `status: pending`; recall/hooks exclude pending pages; approval = edit + flip status (git diff is the review UI); `memex verify` reports pending count. Opt-in per repo.

### C2. Provenance front matter + reserved namespaces — `S`
**Source:** memorywire op fields (confidence/source/expires_at); Hindsight reserved `source:`/`harness:` tags ("attribution always reflects the agent that actually wrote it").
**Signal:** every page declares where it came from, at what confidence, with reserved namespaces users can't forge.
**Proposal:** standardize `source: transcript|git|manual|consolidation`, `harness:`, `confidence:` in front matter (capture path fills them); reject user-supplied values in reserved namespaces at the write boundary.

### C3. Expire predicates + fail-closed bulk guards — `S`
**Source:** memorywire expire DSL (`no_recall_in_days`, …) + its highest-priority fix (empty policy silently matched everything) and no-scope-forget guard.
**Signal:** declarative expiry beats ad-hoc decay calls; **every unscoped bulk mutation must fail closed**.
**Proposal:** `memex expire --no-recall-in-days 30 --dry-run` implementing the predicate over index stats; `forget`/`expire` without scope require explicit `--all` (never infer "everything" from empty args); pinned by CI tests.

### C4. Provenance purge, quarantine-first — `M`
**Source:** memorywire PurgeBench — provenance-driven purge RC **0.64** vs content-anomaly detection **0.036** (~18×); entangled-poison lesson (auto-delete destroys the benign fact it rides on).
**Signal:** purge by provenance works, content classifiers don't; poisoned memories must be **quarantined for review, never auto-deleted**.
**Proposal:** `memex purge --source <x> [--dry-run]` listing affected pages with their provenance before any write; quarantined pages get `status: quarantined` (excluded from recall, kept on disk). Invest in git rollback, not classifiers.

---

## D. Security

### D1. Secret scrubber at the write boundary — `S`
**Source:** Hindsight Memory Defense — 45 MIT-licensed regex patterns (API keys, tokens, DB URLs, PEM blocks, SSN/cards), redacted *before storage* with typed markers (`[REDACTED:github_token]`).
**Proposal:** port the pattern set into `memex write` / transcript ingest / consolidation; redact before file write; log category only (never the match). Pairs with the existing "never log memory contents" rule.

### D2. Fail-closed enablement invariant — `S`
**Source:** Hindsight opt-in: *"There is deliberately no repo-carried config … a cloned repository must not be able to turn memory on. A privacy switch has to fail closed."*
**Proposal:** state and test the invariant: memex hooks/config live only under `$HOME` (or explicit user env); nothing in a cloned repo can enable capture or injection. Add a CI check that no adapter reads repo-local config.

---

## E. Capture & harness hardening

### E1. Harness-quirk compatibility table — `S` (docs, then tests)
**Source:** Hindsight's 853-line coding-agents doc — effectively a harness-compatibility RFC: ms-vs-s timeout units, missing Stop events, transcript-less hosts (journal it yourself), per-turn vs on-stop write-back, cancelled turns, shared config files with mutually rejected keys.
**Proposal:** `docs/harness-matrix.md` capturing the same facts for memex's four adapters + the ones Hindsight catalogued that memex may support later; each quirk becomes a hook-layer test where possible.

### E2. Attribution from recorded cwd only — `S`
**Source:** Hindsight session-import safety: never infer repo from paths ("`/` and `.` both encode to `-` … a wrong guess files someone else's conversation into your bank"); sessions that record nothing are **skipped and the count reported**.
**Proposal:** capture uses only the session's *recorded* cwd (Codex `session_meta.cwd`, pi session header, Claude transcript) — never filename guessing; skips are counted in the capture log. (Memex's parsers already do this; make it a documented invariant + test.)

### E3. Git seeding & gitlog upsert — `M`
**Source:** Hindsight autoSeed (`seedLimit: 300` recent commits) + `gitIngest: message|full|none` — an aggregated `gitlog:<repo>` document *upserted when HEAD moves* (idempotent, dedup by stable doc id).
**Proposal:** `memex seed --from-git [--limit 300] [--depth message|full]`: distills commit history into a repo-summary page on cold start; idempotent upsert keyed on HEAD; feeds B7 repo scoping.

### E4. Fail-open ladder, formally — `S`
**Source:** Hindsight degradation chain: reflect → knowledge pages → raw recall → *memoryless turn*, every step logged; "failures never break the agent."
**Proposal:** memex hooks already fail-silent; formalize the ladder in docs + diagnostics: injection failure → pull-only mode notice; capture failure → recovery command hint in the capture log. Never block a turn.

---

## F. Self-measurement & CI (the deterministic layer's teeth)

### F1. Memory-credit usage tracking — `M`
**Source:** Hindsight `usage.jsonl`: one JSON line per finished turn — which memory tools the agent called, whether the reply credited memory; local only; `stats` summarizes per agent.
**Signal:** a **CI-checkable effectiveness metric** — not "memory exists" but "memory was *used*."
**Proposal:** MCP tool calls already bump `access_count`; add per-session `usage.jsonl` (tool calls, recall hits, credit heuristic) under `~/.memex/logs/`, plus `memex stats` summarizing recall/credit rate per harness.

### F2. Zero-yield distillation audit — `S`
**Source:** Hindsight: a retain that extracts nothing is *recorded* (`memory_unit_count: 0`, `no_facts` metric) with the honest note that extraction is nondeterministic — "treat zero as 'needs another pass', not a verdict."
**Proposal:** consolidation reports land in the capture log with `nodes_created: 0` flagged as zero-yield (already surfaced in the report — add the log line + `memex verify` warning on consecutive zero-yield sessions).

### F3. Local recall eval fixtures — `M`
**Source:** Letta Context-Bench / Leaderboard (evaluating models *at managing* memory); Hindsight's published benchmark harness posture.
**Proposal:** a deterministic, offline eval: seeded corpus of pages → labelled queries → assert recall@k ≥ threshold in CI; a consolidation round-trip fixture (episodes in → pages out → recall finds them). This is the A/B harness A1/A2 require, and it turns "memory quality" into a gate memex verify can enforce.

### F4. `memex status` — `S`
**Source:** Hindsight `hindsight_sync_status` (synced? gitlog freshness? survey state? in-flight ops?).
**Proposal:** one command: index freshness, last capture per harness, pending approvals (C1), quarantined pages (C4), zero-yield streak (F2). Diagnosis without opening SQLite.

---

## G. Context injection (Letta-derived)

### G1. Budgeted always-on memory block — `M`
**Source:** Letta memory blocks: small, always-in-context, per-block char budgets — durable facts resident every turn by construction, not by retrieval luck.
**Proposal:** the session-start hook gains a fixed-budget block (e.g. 1–2k tokens): top pages by deterministic ranking (importance × recency × proof) with **ranked overflow** — the block is a guaranteed-resident core; §5.4 injection remains the retrieval layer on top. Pairs with A3's budget contract.

### G2. Mini context constitution — `S`
**Source:** Letta Context Constitution + the red-team finding that models have *"a deep self-identification with ephemerality that cannot be repaired with prompting alone."*
**Signal:** two lessons: (a) state a short set of memory principles at session start; (b) **don't rely on prompting for write-back** — memex's deterministic hooks/consolidation are exactly the right backstop, and the injection should frame memories as the agent's *own durable state*, not external trivia.
**Proposal:** a 5-line constitution header on the session-start block (memories are yours; sessions die, these don't; write durable facts; recall before assuming; provenance is sacred). Cheap, testable wording.

---

## Explicitly rejected (noise, with reasons)

| Rejected | Source | Why |
|---|---|---|
| Vector/embedding retrieval, cross-encoder reranking, graph traversal | Hindsight TEMPR; Letta archival | memex's design mandate; Letta's own filesystem result undercuts the necessity claim |
| LLM extraction on every write | Hindsight retain | LLM only on explicit consolidation, by charter |
| Server process / hosted banks / multi-tenant sync | Hindsight, Letta Cloud | local-first, single-user |
| Fuzzy entity resolution | Hindsight | wrong-merge risk; deterministic exact-match vocabularies instead (C2) |
| Sleep-time daemon / background rewriting | Letta sleep-time compute | no daemons; B3 scope-guarded *hook-triggered* refresh achieves the cadence without a process |
| Memory-native RL "memory models" | Letta research thesis | thesis-level validation of portable token memory; not buildable here |
| LiteLLM auto-memory wrappers | Hindsight | implicit capture is anti-charter (explicit hooks/MCP contract) |
| memorywire wire format adoption | memorywire | v0.x unstable spec, single author; take the *field semantics* (C2/C3), not the protocol |

## Adopted doctrine (no code required)

- **Pull beats push for retrieval** (Hindsight): "Retrieval the agent asked for informs what it's doing; retrieval it didn't ask for tends to derail it" — memex's hybrid (one session-start inject, pull thereafter) is the validated middle.
- **Pages are projections** (Hindsight): transcripts are the storage; distilled pages are the rendering — "pages heal themselves rather than rot."
- **Documents are truth** (Hindsight): curation never edits the transcript it came from.
- **Per-repo, not per-agent beliefs** (Hindsight scopes rationale).
- **Rank-space, never score-max, fusion** (memorywire adversarial result).
- **One state root** (Hindsight reset story): everything under `~/.memex`; no scattered client state.

## Suggested sequencing

| Wave | Items | Theme |
|---|---|---|
| 1 (quick wins, ≤ a day each) | A3, A4, B4, B5, C2, D1, D2, E2, F2, F4, G2 | contracts, front matter, guards, scrubber |
| 2 (retrieval) | F3 → A1 → A2 | eval harness first, then fuse, then boost |
| 3 (consolidation) | B1, B2, B3, B7, E3 | evidence, delta refresh, staleness, per-repo |
| 4 (governance & measurement) | C1, C3, C4, F1, G1, E1 | HITL, expiry, credit metrics, core block |

## Evidence caveats

- Hindsight brief: from the local clone of `main` — docs-read, not server-internals-read; benchmark claims are vendor framing.
- Letta brief: research index is fetched evidence; mechanism details are labeled model knowledge — verify before citing numbers beyond the two quoted (74.0% LoCoMo, ephemerality finding).
- memorywire: single-author v0.x preprint, self-built benchmarks (n=10–12, 1 seed); its *engineering lessons* are high-confidence, its *scores* directional only.
