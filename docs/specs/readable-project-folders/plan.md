# Plan: Readable project folders

- **Spec:** [`spec.md`](spec.md)
- **Status:** Done
- **Repository anchors:** ADR-0001; `docs/architecture/overview.md`; `workspace_context.py`, `wiki_store.py`, `index_manager.py`; `tests/unit/test_wiki_store.py` and `tests/acceptance/test_project_scoped_memory.py`.

## Approach

Separate the human-readable directory locator from the existing opaque project
identity. Derive a safe locator from a Git remote repository name or the local
workspace folder, route project page paths through one storage seam, and keep
front matter and SQLite keyed by `project_id`. Do not move any live user files
in runtime code. Update the external maintenance procedure so an existing
store can be previewed and moved only after separate confirmation.

## Constraints

- Markdown is authoritative; SQLite is disposable.
- Existing identity semantics and the shared Python/CLI/MCP contract remain intact.
- No new dependency, runtime migration path, or automatic merge on a name collision.

## Construction tests

**Integration tests:** isolated-store scoped write, lookup, recall, dashboard
read, and force rebuild across two projects and global memory.

**Manual verification:** use an isolated `MEMEX_DATA_DIR` for the documented
CLI write/recall flow and inspect the resulting path; run the external
procedure only in preview mode until separate confirmation.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| User storage contract | T3 | guide/spec update | strict docs build |
| Architecture | T3 | overview update | docs build and review |
| Existing-store procedure | T3 | skill update and dry-run preview | validated skill and preview record |
| Delivery evidence | T1-T3 | tests and smoke | verification ledger |

## Design (LLD)

### Data & schema

The folder segment is a locator, not a project key. The workspace-context
resolver supplies a non-persisted folder locator along with the opaque ID and
display label: Git origins produce `git-<repo>`; absent or unusable origins use
the local root folder name. The shared write input carries that safe locator
through the facade to storage. An explicit project ID from any adapter does
not inherit the current working directory's locator: absent an explicit
validated locator, it retains its existing directory or uses the ID-named
directory when no directory exists. The existing slug normalization bounds
the locator to one safe component. Storage rejects symlinked `docs` or
`projects` ancestors, resolves each candidate destination, and checks
confinement within the data directory after symlink resolution.
Front matter remains the owner of opaque `project_id` and
display `project_label`; SQLite mirrors page metadata and retains its existing
absolute `file_path` access field.

### Interfaces & contracts

The shared store resolves paths for all adapters. Public scope selectors
continue using `project_id`; no caller derives identity from the folder
segment. Runtime reads and the external migration procedure recognize existing
ID-named folders; runtime startup does not relocate them.

## Tasks

### T1: Readable path selection passes isolated storage tests

**Depends on:** none

**Tests:**
- **Mode: TDD.** Extend `tests/unit/test_wiki_store.py` and the project
  identity tests with GitHub, self-hosted, local-Git, non-Git, unsafe-name,
  symlinked `docs`/`projects` ancestors, escaping project-dir links, and
  collision examples for AC-0001 through AC-0005.
- Stub: `assert written.file_path.endswith("docs/projects/git-memex/preferences/example.md")`
  for a Git origin fixture whose repository basename is `memex`.

**Approach:**
- Preserve `project_identity`'s opaque-ID algorithm while extending workspace
  context with a safe, non-persisted folder locator.
- Carry the locator through the shared write input and facade; check an
  existing destination's project ID before writing.

**Done when:** the new storage tests pass with no live data directory accessed.

### T2: All read paths and rebuilds resolve readable folders

**Depends on:** T1

**Tests:**
- **Mode: TDD.** Extend `tests/acceptance/test_project_scoped_memory.py`
  and relevant store/index/dashboard tests for AC-0006, AC-0007, and AC-0009
  through AC-0012. Include one same-ID mixed-layout fixture with duplicate
  type/slug to prove lookup and rebuild refuse ambiguity.
- Stub: `assert {hit.project_id for hit in memex.recall("marker", scope="global").hits} == {first_id, second_id}`
  after isolated writes and a force rebuild.

**Approach:**
- Route project-scoped lookups, scans, links, and index rebuild through the
  same folder-to-ID resolution. Preserve a single legacy directory on write;
  refuse duplicate namespace keys across mixed layouts.
- Keep SQLite as a mirror of page metadata rather than a locator authority.

**Done when:** acceptance and read-path tests pass after deleting/rebuilding
the isolated index.

### T3: The published contract and external procedure match the shipped layout

**Depends on:** T1, T2

**Tests:**
- **Mode: goal-based check.** Strict docs build, skill validation, and a
  dry-run preview of an isolated old-layout fixture for AC-0008.
- **Mode: visual / manual QA.** Isolated CLI write and recall with observed
  readable path for AC-0001 or AC-0002.

**Approach:**
- Update user and architecture docs and the external migration skill.
- Record preview, backup requirements, and unresolved collision behavior;
  perform no live move without the separate confirmation.

**Done when:** docs build, skill validation, quality gates, and isolated CLI
smoke pass; the verification ledger records results.

## Rollout

Fresh writes use readable directories after the runtime release. Existing
ID-named directories remain untouched until an explicitly confirmed external
migration. The maintenance procedure backs up the store, previews
source-to-target paths, stops on unresolved collisions, and rebuilds SQLite
after a confirmed move. Rollback restores that backup.

## Risks

- Existing ID-named pages can be missed if a read path assumes the new layout
  before the external move; isolated mixed-layout tests must expose this.
- Two remote repositories or local folders may propose the same readable
  segment; fail closed rather than mixing their pages.
- A Git origin change can change the proposed locator while retaining or
  changing the underlying identity; the migration preview must identify it.

## Changelog

- 2026-09-19: Initial plan after approval of `git-<repo>` remote naming.
