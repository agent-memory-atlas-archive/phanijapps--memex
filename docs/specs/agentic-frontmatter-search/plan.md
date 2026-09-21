# Plan: Agentic front matter search

- **Spec:** [`spec.md`](spec.md)
- **Status:** Done
- **Repository anchors:** `src/memex/domain/models.py`,
  `src/memex/infrastructure/wiki_store.py`,
  `src/memex/infrastructure/index_manager.py`,
  `src/memex/infrastructure/bm25_retriever.py`,
  `src/memex/application/memory.py`, `src/memex/cli.py`,
  `src/memex/mcp_server.py`, and their unit and acceptance tests.

> **Plan contract:** Tasks, Tests, Touches, and Done when are the build gates.

## Approach

Add one optional page descriptor through the existing shared models and strict
front-matter codec. Mirror it into a new FTS5 column and bump the disposable
index schema. Generate OKF-compatible `index.md` navigation from pages while
reserving both `index.md` and `log.md` from memory scans. Keep the existing four
search-field weights unchanged by inserting the description column with its own
neutral weight. Return a description snippet when that field matched. Carry the
additive input and output through CLI, MCP, import/export, and consolidation,
then document the bounded index/search/read/follow loop.

The implementation uses full mode because it changes a persistent page format,
the disposable index schema, and public adapter inputs and outputs.

## Constraints

- ADR-0001 keeps Markdown authoritative.
- ADR-0002 keeps adapters thin and shared contracts typed.
- ADR-0004 keeps harness installation user-controlled.
- No new dependency, service, model call, background process, or mandatory
  external search executable enters the runtime.
- Existing pages are not migrated or rewritten.

## Construction tests

**TDD:** model, front matter, index migration, description-only retrieval,
snippet source, generated navigation, reserved-file exclusion, adapter parity,
and import/export behavior.

**Goal-based integration:** rebuild an isolated store and verify the same hit
before and after deleting the derived index.

**Manual QA:** use `MEMEX_DATA_DIR=/tmp/...` to descend generated indexes,
write, recall, read, and follow one linked page through the installed contract.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Guide and README | T4 | Isolated command transcript | Published docs match CLI and MCP |
| Architecture | T4 | Updated page/index flow | Markdown authority remains explicit |
| Research note | Pre-plan evidence | Source-linked recommendation | Selected and rejected ideas are distinct |
| Changelog | T4 | Scoped entry | Entry matches shipped behavior |

## Design (LLD)

### Data contract

`description: str = ""` is additive on `WriteInput`, `WikiNode`, and
`RecallHit`. It is serialized directly in front matter. Validation is shared in
the domain model and enforces AC-0002. Persisting write paths scrub it before
the page, index, backup, export, or recall can expose the stored value.

### Search contract

`wiki_index.description` mirrors the page. `wiki_fts` adds `description`
between title and body. The production BM25 call supplies explicit weights for
all five columns so the old slug, title, body, and tag values do not move.
Snippet selection checks body, description, then title and reports the matching
source. Existing fallback semantics remain unchanged.

### Upgrade contract

The index schema version increments. Schema inspection treats a missing
description column as stale, and the facade rebuilds the disposable index from
Markdown. Watcher and freshness checks compare the mirrored description as well
as the existing body hash so a description-only edit cannot remain stale. The
upgrade never edits a page.

### Agent search contract

Memex remains deterministic. The host agent decides whether evidence is
sufficient. Recall returns a compact signpost, a path, and links; the host may
read that path, issue another recall for a link, or use its own exact file
search on returned file paths and paths obtained by following returned links.

### Directory navigation contract

A shared generator scans `WikiNode` pages, excluding reserved filenames, and
writes one deterministic `index.md` for every populated directory and ancestor.
The root declares OKF v0.2; descendant indexes are body-only. Page state remains
the source of truth. Writes, lifecycle mutations, deletes, and watcher refreshes
regenerate only the affected directory chain. Full rebuild can regenerate all
indexes. A structural `log.md` is ignored and preserved. Valid legacy Memex
pages at either reserved filename remain normal memories and block structural
generation at the colliding path with a verification diagnostic. New slug
allocation treats both reserved names as already occupied.

The generator escapes page titles and descriptions as text and is the only
writer of navigation links. It resolves every generated target under the docs
root before writing. Navigation diagnostics use bounded categories, stable ids,
and confined relative paths; they never echo memory content or raw exceptions.

Navigation refresh is best effort after a page mutation commits. A refresh
failure cannot roll back or fail the authoritative mutation; verification
reports missing, stale, or collision-blocked navigation, and full regeneration
repairs it. The watcher excludes structural reserved files, so generator writes
cannot feed back into the memory lifecycle.

## Tasks

### T1: Persist and index descriptions

**Depends on:** none

**Touches:** domain models, wiki store, index manager, BM25 retriever, model and
storage tests

**Tests:**
- TDD: boundary validation and legacy defaults in the domain/store suites.
- TDD: description-only retrieval, snippet source, unchanged empty-description
  ranking, and stale-index rebuild in retrieval/index suites.
- TDD: watcher and freshness diagnostics observe a description-only direct
  edit without changing the meaning of the stored body hash.
- Goal-based integration: delete and rebuild an isolated index and compare the
  returned page and description.

**Approach:**
- Add the field to typed models and strict serialization.
- Mirror and search it in FTS5 with an explicit five-column weight vector.
- Rebuild old derived indexes by schema inspection.

**Done when:** The T1 tests prove AC-0001, AC-0002, AC-0003, AC-0004,
AC-0005, AC-0006, AC-0007, and AC-0014.

### T2: Keep every adapter and interchange path consistent

**Depends on:** T1

**Touches:** facade, CLI, MCP, import/export, consolidator, adapter and
interchange tests

**Tests:**
- TDD: Python, CLI, and MCP accept the same valid and invalid descriptions and
  recall serializes the field.
- TDD: JSON round trip and consolidation omission/description cases.
- TDD: secret-shaped descriptions through Python, CLI, MCP, and consolidation
  are absent from the isolated data directory, recall, backup, and export.

**Approach:**
- Thread the field through existing shared inputs and DTO conversion.
- Teach consolidation to request a short description while retaining the
  domain validator as the enforcement boundary.

**Done when:** The T2 tests prove AC-0008, AC-0009, and AC-0013.

### T3: Generate deterministic directory navigation

**Depends on:** T2

**Touches:** wiki store scanning, navigation generator, memory mutations,
watcher, rebuild, backup/restore boundaries, and filesystem tests

**Tests:**
- TDD: root and descendant shape, ordering, title/description entries,
  inert-text escaping, confined generator-owned links, child-directory links,
  idempotent bytes, and empty-directory cleanup.
- TDD: reserved-file exclusion across scans, FTS, links, export,
  consolidation, task recall, and watcher inputs; `log.md` byte preservation.
- TDD: legacy memory collisions remain fully usable and unchanged, new writes
  suffix reserved slugs, generation skips the path, and verification reports it.
- TDD: injected navigation-write failure leaves the page mutation successful;
  verification reports the defect and regeneration repairs it.
- TDD: diagnostics contain only approved categories, stable ids, and confined
  relative paths under fixtures containing secrets, hostile markup, absolute
  paths, and raw exception text.
- Goal-based integration: delete every generated index, prove recall still
  works, regenerate, and compare the restored navigation with the page tree.

**Approach:**
- Add one shared generator over validated pages and atomic writes.
- Refresh the affected ancestor chain after page mutations and watcher updates;
  regenerate the whole tree during rebuild.

**Done when:** The T3 tests prove AC-0015, AC-0016, AC-0017, AC-0018,
AC-0019, and AC-0020.

### T4: Make the agent journey visible and verify it live

**Depends on:** T3

**Touches:** harness guidance, README, guide, architecture, changelog, docs
tests

**Tests:**
- Manual QA: isolated root-index descent, description-only recall, file read,
  and one link-following recall with observed output.
- Goal-based check: `uv run mkdocs build --strict` and guidance content pins.

**Approach:**
- Describe the bounded search/read/follow loop and the untrusted-evidence rule.
- Document optional host `rg` use over returned file paths and paths reached
  from returned links without adding a Memex subprocess dependency.

**Done when:** The T4 checks prove AC-0010, AC-0011, and AC-0012.

## Rollout

The next Memex open may rebuild only the stale SQLite index; opening a store
does not write Markdown navigation. A fresh store gains navigation as pages are
written. An upgraded store gains the complete navigation tree through explicit
`memex rebuild-index`, while later page mutations refresh their affected paths.
Existing pages continue with an empty description until a user or agent edits
them. Existing `log.md` files remain untouched. Newly installed harness
guidance takes effect through the existing explicit install/update flow.

## Risks

- Poor descriptions can add noise. The body remains authoritative and the
  field stays optional and short.
- An extra FTS column can perturb scores if weights shift. Explicit weights and
  empty-description winner fixtures pin the old contribution values.
- Agent file search could escape memory storage if guidance is vague. The
  documented loop limits exact search to returned Memex paths.
- Generated indexes can drift if a mutation path omits refresh. The shared
  generator, affected-chain integration tests, and full regeneration command
  provide recovery without changing pages.

## Changelog

- 2026-09-21: Initial plan from the agentic front matter research.
