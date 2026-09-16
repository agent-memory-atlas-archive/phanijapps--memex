# Spec: v1 guardrails — memory contracts, provenance, and approval

- **Status:** Shipped <!-- Draft | Approved | Implementing | Shipped | Archived -->
- **Owner:** phanijapps
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`docs/v1_enhance.md`](../../v1_enhance.md) wave 1 + C1 (evidence-mined enhancement signals; hindsight/letta/memorywire briefs)
- **Brief:** none
- **Discovery:** none
- **Contract:** none — CLI + front-matter surface; the existing MCP tool schemas absorb changes without a new interface artifact
- **Shape:** mixed (service + data: CLI behavior, config schema, page front matter, write-path guards)

> **Spec contract:** this document defines what "done" means. The implementing
> PR must match this spec, or update it. Verification must be derivable from it.
>
> **Not every section is contract.** `Boundaries`, `Testing Strategy` and
> `Acceptance Criteria` are what a completion gate reads, and an amendment
> changes them. `Objective`, `Durable Outputs`, `Follow-ons` and `Assumptions`
> are working material: they orient a reader and an author corrects them in place
> as the work teaches, without an amendment and without a review round.

## Objective

Memex memory pages carry honest provenance, size-bounded retrieval, and a
human approval gate, enforced by deterministic checks:

1. **Recall is budget-bounded, not count-bounded.** `memex recall` and every
   hook injection pack results to a token budget (default 4096, configurable):
   page text counts against the budget, metadata does not, a hit that does not
   fit is skipped in favor of smaller ones, and the top-ranked hit is always
   returned whole. Hook injection additionally stays silent when the best
   match falls below a minimum relevance floor.
2. **Pages know where they came from and whether they count.** Every page
   carries optional `occurred_at` (when the fact happened, distinct from when
   it was recorded), a `status` (`active` | `pending` | `superseded` |
   `archived`), and provenance fields (`source`, `harness`, `confidence`) in
   reserved namespaces users cannot forge (all three rejected as user input). Recall and hook injection see
   `active` pages only by default.
3. **Consolidation can require human approval.** A `memex.toml` setting
   routes consolidation-created pages to `status: pending`; approval is a
   one-command flip that makes the page recallable.
4. **Secrets never reach disk.** Every write boundary (CLI, MCP, transcript
   ingest, consolidation) redacts a bundled catalog of credential patterns
   before storing, with typed markers.
5. **The store answers for itself.** `memex status` reports index freshness,
   last capture per harness (from a persisted consolidation/capture run log
   this feature introduces at `~/.memex/logs/runs.jsonl`),
   pending-approval and archived counts, and consecutive zero-yield
   consolidations; `memex verify` warns on a zero-yield
   streak. No file inside a cloned repository can enable capture or injection, and
   session-to-repository attribution uses only the harness-recorded cwd
   (existing behavior, pinned by guard tests).

## Durable Outputs

- **User-facing promise** — `docs/gitpages/guide.md`: new sections for
  token-budget recall, page status lifecycle, approval flow, and the secret
  scrubber. Updated in the same PR as the behavior.
- **Current product truth** — `README.md` command table gains `status`,
  `approve`, `merge`, and `forget --mode archive`; one line on approval +
  scrubber.
- **Decision rationale** — `docs/implementation-notes.md`: entries for each
  shipped guardrail citing its signal source (A3/A4/B4/B5/C1/C2/D1/D2/E2/F2/F4/G2); E2's
  attribution invariant stays covered by plan-level guard tests (not a
  criterion — the behavior already ships; the guards make regressions red).
- **Reusable learning** — none beyond implementation notes (patterns catalog
  is code + tests, not prose).

## Boundaries

### Always do
- Keep every CI test offline and deterministic; the only network-touching
  test is the opt-in ollama integration test, skipped automatically when the
  local model is absent.
- All new front-matter fields are optional with defaults; pages written by
  older versions parse unchanged, and readers treat a missing `status` as
  `active`.
- Update the docs site and `implementation-notes.md` in the same PR as each
  behavior change.

### Ask first
- Changing the semantics of existing temporal fields (`expires_at`,
  `valid_from`, `valid_to`) or their recall filtering.
- Any new third-party dependency (the scrubber catalog is stdlib `re`).

### Never do
- No vector, embedding, or cross-encoder retrieval — BM25 stays the only
  ranking source (structural).
- No new top-level package, no new storage engine, no background daemon
  (structural).
- No repository-carried configuration may enable capture, injection, or
  consolidation — enablement lives in `~/.memex/` and explicit user action
  only (the D2 invariant; violations are a security finding).
- No redaction of transcript JSONL after the fact — scrubbing happens at the
  write boundary or not at all; existing files are untouched.

## Testing Strategy

Every objective outcome pairs with a mode:

- **Token-budget contract (Obj 1; AC-0001)** — TDD: packer unit tests over fixture
  RecallResults (fits/skips/top-1-always, metadata-free accounting) plus a
  hook E2E asserting the emitted block stays under budget. Deterministic:
  token counting is the `len(text) // 4 + 1` estimator introduced with the
  packer (T3) and pinned by its unit tests.
- **Injection floor (Obj 1; AC-0002)** — TDD: hook returns empty string for matches
  below the floor while explicit `memex recall` still returns them.
- **Front-matter lifecycle + provenance (Obj 2; AC-0003, AC-0004, AC-0005, AC-0006, AC-0008)** — TDD: round-trip tests for
  the new fields through WikiStore; recall filter matrix over
  status×include flags; reserved-namespace rejection at the write boundary
  (`memex write --meta source=...` is refused).
- **Approval flow (Obj 3; AC-0007)** — TDD: with `[governance] approval = "manual"`
  in memex.toml, consolidation output lands `pending`, is invisible to
  recall, and `memex approve <slug>` flips it; config default `auto` behaves
  as today. Goal-based: one FakeLLM consolidation E2E per mode.
- **Scrubber (Obj 4; AC-0009)** — TDD: the pattern catalog is pinned by a fixture of
  real-shaped secrets (API keys, tokens, PEM blocks) asserting typed
  `[REDACTED:<kind>]` markers before any file write; a canary test asserts
  no marker text ever reaches a transcript or page.
- **Status command + zero-yield (Obj 5; AC-0011, AC-0012)** — TDD: `memex status` JSON shape
  against a seeded store; `memex verify` exit codes with and without a
  zero-yield streak. Fixture source is the `runs.jsonl` log persisted by the
  consolidation-run-logging task (T1b). Determinism: seeded `runs.jsonl` fixtures.
- **Enablement invariant (Obj 5; AC-0010)** — TDD: a fixture repo containing
  plausible config files (`memex.toml`, `.memex.toml`, hooks) asserts the
  installer and runtime ignore all of them; only `$HOME`-scoped config is read.
- **Constitution header (Obj 1, injection; AC-0013)** — content pin: the session-start
  block's three-line header is asserted verbatim once (wording is content, not
  logic).
- **LLM integration (whole; AC-0014)** — goal-based, opt-in: one end-to-end
  consolidation against local ollama (`glm-5.3-flash:cloud`), asserting a
  valid JSON node parses and stores; skipped (not failed) when ollama or the
  model is unreachable. Covers provider plumbing only — quality is FakeLLM
  territory.

## Acceptance Criteria

- [x] **AC-0001.** `memex recall --max-tokens 500` returns hits whose combined page
      text fits 500 tokens by the estimator, and hook injection packs to the
      same contract with a default budget of 4096 tokens; when the top hit alone exceeds
      the budget it is returned whole and alone; metadata fields are excluded
      from the accounting. (Test: packer unit + CLI E2E)
- [x] **AC-0002.** `memex hook prompt` emits nothing when the best hit's BM25 rank
      is below the configured floor, while `memex recall` with the same query
      returns it. (Test: hook unit with floor config)
- [x] **AC-0003.** `occurred_at` round-trips through write/read/backup/restore and
      appears in `RecallHit`; capture fills it from the source event
      timestamp when the harness records one. (Test: WikiStore round-trip +
      codex parser fixture)
- [x] **AC-0004.** pages with `status` other than `active` are excluded from recall
      and hook injection by default; `--include-inactive` (CLI) and
      `include_inactive` (MCP/API) return them with their status in the hit.
      A missing status field reads as `active`. (Test: filter matrix)
- [x] **AC-0005.** `memex forget <slug> --mode archive` sets `status: archived`
      in place of deleting; the file remains on disk and is excluded by AC-0004's
      default. (Test: CLI + store)
- [x] **AC-0006.** `memex merge <target> <source>` moves `source`'s body into
      `target` as an appended section, sets `source` to
      `status: superseded` with a `superseded_by` link, and syncs the index.
      (Test: CLI E2E)
- [x] **AC-0007.** with `[governance] approval = "manual"`, consolidation-created
      pages land `status: pending`; `memex approve <slug>` flips status to
      `active` and re-indexes; with `approval = "auto"` (default) behavior is
      unchanged from today. (Test: FakeLLM consolidation both modes)
- [x] **AC-0008.** `memex write --meta source=x --meta harness=y --meta confidence=0.99` is
      rejected with an actionable error naming the reserved namespaces; capture and
      consolidation set them automatically and correctly. (Test: write
      boundary unit)
- [x] **AC-0009.** a fixture corpus of secret-shaped strings (OpenAI/Anthropic/GitHub
      tokens, AWS keys, PEM block, DB URL, JWT) written through every
      boundary (CLI, MCP tool, ingest, consolidate) is stored with
      `[REDACTED:<kind>]` markers and the originals appear nowhere under
      `~/.memex`. (Test: scrubber matrix + fs grep)
- [x] **AC-0010.** a cloned fixture repo containing `memex.toml`, `.memex.toml`,
      and hook-shaped files produces zero capture or injection; `memex
      status` reads config from the home scope only. (Test: invariant test)
- [x] **AC-0011.** `memex status` emits JSON with: index freshness vs page hashes,
      last capture timestamp per harness, pending and archived counts, and
      consecutive zero-yield consolidation count. (Test: seeded-store shape
      assert)
- [x] **AC-0012.** `memex verify` exits nonzero with a zero-yield warning when the
      capture log shows ≥3 consecutive consolidations with zero nodes; exits
      zero otherwise. (Test: log fixture)
- [x] **AC-0013.** every hook-injected block begins with the five-line memory
      constitution header, asserted verbatim. (Test: content pin)
- [x] **AC-0014.** the opt-in ollama integration test runs one real consolidation
      against `glm-5.3-flash:cloud` end-to-end and is skipped, not failed,
      when the model is unreachable. (Test: integration, marked)

## Assumptions

- Technical: runtime Python 3.12+, gates ruff/mypy-strict/pytest coverage≥90
  (pyproject.toml).
- Technical: recall is top-k only today; FTS5 already exposes per-field
  columns (bm25_retriever.py, index_manager.py L51-54).
- Technical: front matter is a closed key set — new fields extend
  `_FRONT_MATTER_KEYS` and the parser (wiki_store.py L26/L294).
- Technical: consolidation is full-rewrite, no delta mode (consolidator.py).
- Process: specs live in `docs/specs/`; adversarial-reviewer config exists in
  `.codex/agents/` but no matching pi subagent is installed — the closest
  independent `reviewer` substitutes, noted in the review record.
- Process: scope is v1_enhance.md wave 1 plus C1 (user confirmation
  2026-09-16); MCP annotations dropped as already shipped (verified in
  mcp_server.py).
- Product: HITL approval is config-gated via memex.toml (user confirmation
  2026-09-16); LLM integration testing rides local ollama
  `glm-5.3-flash:cloud` (probe: `ollama list` 2026-09-16), all other tests
  stay offline with FakeLLM.

## Follow-ons

- Wave 2 (retrieval: eval fixtures → RRF fusion → boosts), wave 3
  (consolidation quality), wave 4 remainder (expire DSL, credit metrics,
  git seeding) — see `docs/v1_enhance.md` sequencing.
