# Plan: v1 guardrails — memory contracts, provenance, and approval

- **Spec:** [`spec.md`](spec.md)
- **Status:** Done
- **Repository anchors:** `AGENTS.md` (layered `src/memex` mandate, shared
  domain services, security rules); `src/memex/infrastructure/wiki_store.py`
  (closed front-matter key set — extension point for every new field);
  `src/memex/application/context_injection.py` (§5.4 block — budget packer
  hooks in here); `tests/unit/test_session_headers.py` (front-matter
  round-trip pattern to copy); `tests/unit/test_install_mcp.py` (boundary
  test pattern for config invariants).

## Approach

Extend the domain model first (status, occurred_at, provenance fields as
optional front matter with `active` defaults), then let each boundary adopt
them: recall filters in the retriever, the budget packer in
`context_injection`, the scrubber as a domain function called by the facade's
write path (single choke point for CLI + MCP + consolidate + ingest), and the
approval gate in the consolidator behind a `[governance]` config read.
`memex status` composes existing index/log surfaces — no new store. Riskiest
part: the scrubber catalog must redact before any write without false
positives on ordinary prose; it lands behind its own task with a pinned
fixture corpus. Order: model → storage → retrieval/budget → scrubber →
approval → status/verify → constitution + docs.

## Constraints

- Spec `docs/specs/v1-guardrails/spec.md` (Boundaries: no vectors, no new
  dependency, no daemon, no repo-carried enablement, no after-the-fact
  transcript redaction).
- AGENTS.md: shared domain services and datatypes across adapters; stdlib
  preference (scrubber is stdlib `re`); never log memory contents.
- Backwards compatibility: pages and transcripts written before this change
  parse and recall unchanged (missing fields default).

## Construction tests

Cross-cutting: `tests/unit/test_guardrails_compat.py` — one suite asserting
pre-change fixture pages/transcripts parse, recall, backup, and restore
unchanged with the new fields absent. Runs alongside every task's own tests.

## Design (LLD)

### Model and schema

`domain/models.py`: `PageStatus = Literal["active","pending","superseded","archived"]`;
`WikiNode.status: str = "active"`, `occurred_at: str | None`, `source/harness/confidence: str | None`.
`WriteInput` mirrors them; validation rejects `source`/`harness` values that
did not originate from the capture/consolidation path (facade enforces; the
model validates shape). `wiki_store._FRONT_MATTER_KEYS` extends; missing
status parses as `"active"`.

### Interfaces

Facade `recall(...)` gains `include_inactive: bool = False` and
`max_tokens: int | None`; CLI flags `--include-inactive`, `--max-tokens`;
MCP `memex_recall` gains both (schema enums unchanged elsewhere). New CLI:
`memex status`, `memex approve <slug>`, `memex forget --mode archive`,
`memex merge <target> <source>`.

### Data flows

Budget packing: `context_injection.pack_to_budget(hits, max_tokens)` —
estimator `len(text)//4+1` (introduced here, pinned by tests); skip-and-continue; top-1 always whole; used by
both the §5.4 block and CLI output shaping. Scrubbing:
`domain/scrub.py::scrub(text) -> (clean, kinds)` called in `Memex.write`,
transcript ingest, and consolidator node-write; markers `[REDACTED:<kind>]`.
Approval: `[governance] approval = "auto"|"manual"` in `MemexConfig`;
consolidator stamps `pending` when manual.

### Resilience

`status` reads only existing surfaces (index rows, capture log tail) — any
missing artifact degrades to `null`, never raises. Scrubber failure mode is
fail-closed: an unreadable pattern file (none shipped — catalog is code)
cannot silently disable redaction because the catalog is a frozen tuple.

## Tasks

### T1: Front-matter schema — status, occurred_at, provenance
- **Spec map:** Obj 2; AC-0003, AC-0004 (field layer), AC-0008 (shape layer)
- **Mode:** TDD
- **Tests:** round-trip suite in `tests/unit/test_frontmatter_v1.py` mirroring
  `test_session_headers.py` patterns — each new field, missing-field
  defaults (`status`→`active`), backup/restore parity; parser cwd-attribution guard fixtures live in
  `tests/unit/test_run_log.py`'s capture cases (non-AC characterization). Verifies AC-0003, AC-0004.
- **Approach:** extend `domain/models.py`, `WriteInput`, `wiki_store`
  `_FRONT_MATTER_KEYS` + `_node_from_dict`; index manager gains the columns and bumps `SCHEMA_VERSION` to "2"; on
  open, a version mismatch drops the stale index and auto-rebuilds from
  the wiki files (one log line) — `mem.db` is disposable by charter, so
  no DDL migration path exists. Guard: open a v1-fixture store and assert
  transparent rebuild.
- **Depends on:** none

### T1b: Consolidation/capture run log
- **Spec map:** Obj 5; AC-0011, AC-0012 (+ non-AC guard: recorded-cwd
  attribution fixtures)
- **Mode:** TDD
- **Tests:** `tests/unit/test_run_log.py` — append/read round-trip for
  `~/.memex/logs/runs.jsonl` (timestamp, kind=consolidation|capture, harness,
  nodes_created, cwd recorded or null); skip-count field. Verifies the data
  source AC-0011/AC-0012 read.
- **Approach:** small append-only writer called from the consolidator and
  transcript hook; no schema, one JSON line per run.
- **Depends on:** none

### T2: Recall status filter
- **Spec map:** Obj 2; AC-0004
- **Mode:** TDD
- **Tests:** filter matrix `active|pending|superseded|archived|missing ×
  include_inactive` over a seeded store in `tests/unit/test_recall_status.py`. Verifies AC-0004.
- **Approach:** SQL clause in `bm25_retriever` alongside the existing expiry
  filter; facade/CLI/MCP flags thread through `RecallHit.status`.
- **Depends on:** T1

### T3: Budget packer + injection floor
- **Spec map:** Obj 1; AC-0001, AC-0002, AC-0013
- **Mode:** TDD
- **Tests:** packer unit (fits/skips/top-1, metadata-free) + hook E2E under
  budget + floor silence vs explicit recall + verbatim constitution pin, in
  `tests/unit/test_budget_recall.py` and `tests/unit/test_cli_hooks.py`
  additions. Verifies AC-0001, AC-0002, AC-0013.
- **Approach:** `context_injection.pack_to_budget`; floor constant +
  `[recall] min_injection_rank` config; constitution header constant on the
  block; `--max-tokens` on CLI and MCP.
- **Depends on:** T2 (hits carry status)

### T4: Scrubber at the write boundary
- **Spec map:** Obj 4; AC-0009
- **Mode:** TDD
- **Tests:** `tests/unit/test_scrubber.py` — fixture corpus of real-shaped
  secrets (OpenAI/Anthropic/GitHub/AWS/PEM/JWT/DB-URL) through
  write/ingest/consolidate/MCP; one fs-grep canary asserting no original
  lands under the data dir. Verifies AC-0009.
- **Approach:** `domain/scrub.py` frozen catalog (stdlib `re`), applied in
  facade write path and ingest; log category counts only, never text.
- **Depends on:** none (parallel with T1–T3)

### T5: Reserved provenance namespaces
- **Spec map:** Obj 2; AC-0008
- **Mode:** TDD
- **Tests:** write-boundary rejection cases (`--meta source=`, `--meta
  harness=`, `--meta confidence=`) + automatic correct stamping by capture/consolidate paths.
  Verifies AC-0008.
- **Approach:** facade validates user-supplied `source`/`harness` keys;
  internal paths set them post-validation (single choke point in `Memex.write`).
- **Depends on:** T1

### T6: Approval gate
- **Spec map:** Obj 3; AC-0007
- **Mode:** TDD + goal-based
- **Tests:** FakeLLM consolidation in both modes (pending invisible →
  approve → visible); `memex approve` CLI; `[governance] approval` parse
  test in `tests/unit/test_approval_gate.py`. Verifies AC-0007.
- **Approach:** `MemexConfig.governance.approval`; consolidator stamps
  status on created nodes; `memex approve` flips + re-indexes.
- **Depends on:** T1, T2

### T7: forget --mode archive + merge
- **Spec map:** Obj 2; AC-0005, AC-0006
- **Mode:** TDD
- **Tests:** CLI E2Es: archive keeps file + excludes from recall; merge
  appends body, supersedes source with `superseded_by`, index synced, in `tests/unit/test_cli_lifecycle.py`. Verifies AC-0005, AC-0006.
- **Approach:** facade methods on top of T1 fields; `superseded_by` rides
  the existing `links` mechanism.
- **Depends on:** T1, T2

### T8: memex status + verify zero-yield
- **Spec map:** Obj 5; AC-0011, AC-0012
- **Mode:** TDD
- **Tests:** seeded-store JSON shape; verify exit codes on capture-log
  fixtures (streak ≥3 warns) in `tests/unit/test_status_command.py`. Verifies AC-0011, AC-0012.
- **Approach:** `application/status.py` composing index freshness check
  (reuses verify internals), capture-log tail parse, status counts.
- **Depends on:** T1, T1b, T6, T7 (archived count)

### T9: Enablement invariant
- **Spec map:** Obj 5; AC-0010
- **Mode:** TDD
- **Tests:** fixture repo with plausible config files asserts zero
  capture/injection; config loader reads home scope only.
- **Approach:** test-only fixture + assertion in
  `tests/unit/test_enablement_invariant.py`; loader already home-scoped —
  the test pins it. Verifies AC-0010.
- **Depends on:** none

### T10: Opt-in ollama integration test
- **Spec map:** Testing Strategy LLM-integration row
- **Mode:** goal-based
- **Tests:** `tests/integration/test_ollama_consolidate.py` marked
  `@pytest.mark.ollama` (marker registered in `pyproject.toml`
  `[tool.pytest.ini_options] markers` — required by `--strict-markers`); one real consolidation via provider
  `ollama`/`glm-5.3-flash:cloud`; skip cleanly when unreachable. Verifies AC-0014.
- **Approach:** env `MEMEX_TEST_OLLAMA=1` gates; provider config from
  `memex.toml` override in the test's tmp dir.
- **Depends on:** T6

### T11: Docs + notes sweep
- **Spec map:** Durable Outputs
- **Mode:** goal-based (mkdocs strict + README render)
- **Tests:** `uv run mkdocs build --strict` green; guide sections present.
- **Approach:** guide sections (budget recall, status lifecycle, approval,
  scrubber, merge/archive), README command table, implementation-notes entries per item
  citing signal IDs.
- **Depends on:** T1–T8

## Risks

- **Scrubber false positives** on ordinary prose (hashes, base64-looking
  text) — mitigated by the pinned corpus including negative cases; catalog
  patterns anchored, not substring-loose.
- **Token estimator drift** vs real tokenizer — acceptable: the contract is
  the estimator's budget, deterministic in CI; swapping the estimator later
  is a non-breaking internal change.
- **Approval friction** (pending pages invisible → user confusion) —
  mitigated by `memex status` surfacing pending count and the guide's
  one-line approval flow.

## Changelog

- 2026-09-16: owner review resolved three residual concerns — constitution
  trimmed to three lines; schema change is auto-rebuild-on-mismatch (no DDL);
  the former cwd-attribution criterion demoted to guard tests (behavior already ships). Approved.
- 2026-09-16: drafted from `docs/v1_enhance.md` wave 1 + C1 per user scope
  confirmation; MCP annotations dropped (already shipped).
