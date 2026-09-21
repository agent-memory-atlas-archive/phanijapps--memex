# Changelog

Notable user-visible changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Memex versions
through 0.2.4 are reconstructed from the version-bump commits; later work remains
unreleased until a release tag is created.

## [Unreleased]

### Added

- Searchable page descriptions: an optional single-line `description` (≤512
  UTF-8 bytes) on every write path (`--description` / MCP `description` /
  Python), searched at a neutral FTS weight, returned on recall hits, scrubbed
  for credentials, and preserved through edit, backup/restore, and
  export/import. Generated OKF-style `index.md` directory navigation lists
  titles and descriptions one directory at a time (root index declares
  `okf_version: "0.2"`); `index` and `log` are reserved slugs for new writes,
  pre-existing pages at those names are preserved, and stale SQLite indexes
  rebuild transparently at schema v5 without touching Markdown. A
  pre-description binary on a v5 store silently mis-ranks recall (old
  weights land on shifted FTS columns) and reports generated `index.md`
  files and `description` keys as malformed pages — delete `mem.db` and
  remove generated indexes before downgrading.
- Token-budgeted recall and hook injection, a weak-match injection floor, page
  status lifecycle, manual approval, provenance fields, write-boundary secret
  scrubbing, `memex status`, and zero-yield verification warnings.
- `memex viz`, an on-demand read-only localhost dashboard for pages, sessions,
  token use, and store health.
- Offline synthetic and realistic retrieval evaluation with Recall@K, MRR,
  precision, distractor, difficulty, and scale reporting.
- Deterministic episode summaries and optional harness-assisted episode
  enrichment.
- Optional project task recall through `memex recall --question` and the
  existing `memex_recall` MCP tool. It combines up to three caller-written
  questions into a bounded, source-linked context and names retrieval gaps.

### Changed

- MCP exposes five agent-facing tools. Transcript capture remains in harness
  hooks; manual transcript ingestion, transcript cleanup, import, and export
  remain on the CLI.
- MCP `memex_write` requires an explicit `global` or `project` scope. Omitted
  and invalid scopes are rejected before writing. Project IDs are still derived
  from the server workspace when omitted.
- Stale SQLite schema versions rebuild automatically from Markdown pages.
- Episode and capture metadata retain richer session, model, reasoning-effort,
  Git, and token-usage context when the harness provides it.
- Recall now uses the `semantic-and-fallback-fts5` SQLite FTS5 ranker, which
  passed repaired realistic, Gutenberg, and Salesforce quality gates while
  reducing hard-query context tokens and latency and keeping recall offline.

### Fixed

- Codex capture no longer re-ingests compacted replacement history or records
  enrichment subprocesses as new sessions.
- Claude Code capture now extracts session headers consistently.
- Repeated transcript capture merges later turns without duplicating earlier
  content.

## [memex][0.2.4] — 2026-09-15

### Changed

- Renamed user-facing "wiki" storage terminology to memory pages under
  `~/.memex/docs/`; `[pages]` is the primary config section and legacy `[wiki]`
  remains accepted.
- Corrected source-install and wheel-cache guidance.

## [memex][0.2.3] — 2026-09-15

### Fixed

- The Codex wrapper resolves rollout locations through `CODEX_HOME` and the
  thread store instead of assuming one filesystem layout.

## [memex][0.2.2] — 2026-09-15

### Changed

- Moved session and per-turn token counts from transcript JSONL into the
  transcript metadata sidecar.

## [memex][0.2.1] — 2026-09-15

### Fixed

- Updated the Codex notification wrapper to consume the actual hook event
  schema and log unsupported event categories without recording contents.

## [memex][0.2.0] — 2026-09-15

### Added

- Hardened Codex transcript capture for turn completion, compaction, shutdown,
  tool turns, idempotent merging, and bounded diagnostics.

### Changed

- Moved authoritative memory pages from `~/.memex/wiki/` to
  `~/.memex/docs/`, with in-place migration and legacy-backup restore support.

## [memex][0.1.4] — 2026-09-15

### Fixed

- Kept the Codex `notify` setting in the root config table during installation
  and repaired previously nested placement.

## [memex][0.1.3] — 2026-09-15

### Added

- Transcript session headers with Codex identity, Git, model,
  reasoning-effort, and token-usage metadata.

## [memex][0.1.2] — 2026-09-15

### Added

- Optional MCP registration during harness installation.

## [memex][0.1.1] — 2026-09-15

### Fixed

- Bumped the package version so source reinstalls do not receive a stale cached
  wheel.

## [memex][0.1.0] — 2026-09-15

### Added

- Initial local-first Markdown memory store, SQLite FTS5 retrieval, Python API,
  CLI, MCP tools, transcript hooks, consolidation, backup/restore, harness
  installation, and CI verification.
