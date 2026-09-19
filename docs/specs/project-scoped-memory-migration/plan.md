# Plan: Project-scoped memory

- **Spec:** [`spec.md`](spec.md)
- **Status:** Done
- **Repository anchors:** ADR-0001; `wiki_store.py`, `index_manager.py`, and `transcript_hook.py`; their unit and acceptance tests.

## Approach

Add namespace fields to the shared domain model, make Markdown storage and its
rebuildable SQLite index namespace-aware, then route the same typed behavior
through CLI, MCP, and transcript lifecycle operations. Runtime opens only the
new layout; the installed skill owns legacy moves.

## Constraints

- Markdown remains primary; SQLite stays disposable.
- No runtime dependency, hosted service, or runtime migration code.
- Validate untrusted metadata and never log memory contents.

## Construction tests

**Integration tests:** scoped write/recall/rebuild; transcript date path,
retirement, CLI/MCP parity.

**Manual verification:** isolated `memex` write, local/global recall, transcript
ingest, and confirmed clear.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Shared storage contract | T1-T4 | unit/integration tests | full suite |
| User/architecture docs | T5 | docs checks | strict build |
| Migration procedure | T5 | skill validator | validated skill |

## Design (LLD)

### Data & schema

Front matter owns `scope`, optional opaque `project_id`, display-only
`project_label`, and transcript-reference state. SQLite mirrors these fields;
namespace identity is `{scope, project_id, type, slug}`.

### Interfaces & contracts

Shared inputs and recall hits carry scope metadata. CLI and MCP adapt the same
application operation; no adapter has separate storage semantics.

### Failure, edge cases & resilience

Invalid metadata, unsafe paths, and unconfirmed clear requests mutate nothing.
When an adapter selects project scope without an explicit ID, it derives an
opaque identity from the Git remote or local folder. Retired references are not
readable.

## Tasks

### T1: Scoped page identity is durable

**Depends on:** none

**Tests:** TDD tests for front-matter round trips, opaque identity, and duplicate slugs across namespaces. Covers AC-0001, AC-0002.

**Approach:** Extend domain/page metadata and namespace-aware WikiStore lookup, scan, and writes.

**Done when:** scoped page tests pass without content logging.

### T2: Rebuildable index filters scoped recall

**Depends on:** T1

**Tests:** index/retrieval tests for local/global selection after force rebuild. Covers AC-0002, AC-0003, AC-0006.

**Approach:** Mirror namespace metadata in SQLite and query it consistently.

**Done when:** index/retrieval tests pass after rebuild.

### T3: Adapters share scoped behavior

**Depends on:** T1, T2

**Tests:** CLI/MCP integration tests. Covers AC-0007.

**Approach:** Thread typed scope through application, CLI, MCP, and operation descriptions.

**Done when:** adapter tests pass.

### T4: Transcripts are dated and retireable

**Depends on:** T1, T2

**Tests:** ingestion, list/provenance, and confirmed-clear tests. Covers AC-0004, AC-0005.

**Approach:** Derive UTC date from capture, discover date paths, and retire episode references on clear.

**Done when:** transcript tests pass on an isolated store.

### T5: Publish and verify the contract

**Depends on:** T3, T4

**Tests:** strict docs build and external skill validation.

**Approach:** Update docs and retain the external skill as the only legacy-move procedure.

**Done when:** quality gates and isolated CLI smoke pass.

## Rollout

New stores use scoped layout. Existing stores remain untouched by runtime code
and use the separately confirmed migration skill. Restore the pre-migration
backup to roll back; SQLite rebuilds from pages.

## Risks

- Durable path changes affect links and public results.
- Transcript references must remain valid across date directories and retirement.

## Changelog

- 2026-09-18: Initial plan; legacy moves intentionally remain external.
