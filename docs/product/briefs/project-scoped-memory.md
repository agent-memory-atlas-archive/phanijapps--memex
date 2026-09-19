# Brief: Project-scoped memory

- **Slug:** `project-scoped-memory`
- **Status:** Shipped
- **Received:** 2026-09-18
- **Owner:** Memex maintainers
- **Initiative:** `ini-001`

## Outcome

Memex organizes memory by project so agents can work with the memory relevant
to the current project while retaining the ability to search both the project
and the global memory collection.

## Scope

### In scope

- Determine a collision-safe project identity from a normalized Git remote
  when one is available.
- Otherwise derive a privacy-preserving local identity from the resolved Git
  repository root or non-Git working folder. Use the repository or folder name
  only as the display label.
- Organize memory by that project identity.
- Let the calling model or agent choose local search for the current project
  or global search across stored memory for each query.
- Store transcript files under `transcripts/<yyyy-mm-dd>/`.
- Define the target layout and compatibility rules that an externally invoked
  migration procedure uses for existing flat memory and transcript files.
- Provide an explicit operation to clear all stored transcripts.
- Retain related episode pages when transcripts are cleared, marking their
  transcript links as retired rather than leaving broken references.

### Placement and migration policy

| Material | Default for new writes | Existing flat-file migration target |
| --- | --- | --- |
| Episodes | Current project derived from recorded session context; global only when that context is absent or untrusted | External procedure: project when a recorded transcript establishes one; otherwise global |
| Entities, procedures, summaries | Current project; a caller may explicitly select global | External procedure: global, preserving current behavior until explicitly re-scoped |
| Preferences | Global; a caller may explicitly select a project override | External procedure: global |
| Raw transcripts | `transcripts/<yyyy-mm-dd>/`; the episode page owns project association | External procedure: date-partitioned transcript directory; linked episode retains its derived scope |

Every page carries `scope` (`project` or `global`). Project pages also carry
an opaque `project_id` and a display-only `project_label`. Page and index
identity is scope-aware: `{scope, project_id, type, slug}`. Recall results and
links carry that namespace so equal slugs in different projects remain
distinct; local search filters it and global search returns it.

### Non-goals

- Hosted synchronization or any remote memory service.
- Automatic merging of distinct projects merely because their display names
  match.
- Modifying the user's repository to establish project identity.
- Deleting episode memories when their raw transcripts are cleared. Such
  episodes retain a retired transcript link.
- Automatic migration logic in the Memex runtime or package source.
- Changing the scope-selection contract into a fixed policy that prevents the
  calling model or agent from choosing local or global retrieval.

## Constraints and delivery appetite

- Preserve Markdown as the source of truth and keep SQLite a disposable,
  rebuildable index.
- Keep the runtime focused on the new layout, scoped search, transcript storage,
  and clearing. The manually invoked `project-memory-migration` skill performs
  legacy data moves outside `src/memex`.
- The external procedure must not silently merge projects. A relocated
  remote-less repository or folder is distinct unless a later contract provides
  an explicit mapping.
- Canonicalize a Git remote before deriving an opaque, non-reversible project
  ID. Strip credentials and never persist a raw remote URL, internal hostname,
  or absolute local path in Markdown, SQLite, logs, or results. A local
  identity uses an equivalent store-local privacy-preserving derivation.
- Preserve or explicitly retire every existing `transcript_ref` during
  migration and clearing.
- Require explicit confirmation before clearing transcripts, state what is
  permanently removed, and report results without exposing transcript content.
- Expose a local/global scope selector to the calling model or agent; do not
  impose a fixed retrieval-scope policy.

Security review is proportionate to the changed boundaries: path confinement,
untrusted Markdown and metadata handling, migration safety, destructive-clear
confirmation, and memory-content privacy. It does not expand into unrelated
authentication or network review.

## Assumptions and risks

- **Assumption:** A normalized Git remote is the strongest available automatic
  project identity. Repository and folder names are display labels only.
- **Risk:** A remote-less repository or folder that moves can no longer be
  recognized from its former local path. It must be treated as distinct rather
  than silently merging unrelated memory.
- **Risk:** Partitioning changes where durable Markdown memories are located
  and may affect existing capture, recall, index rebuild, and harness behavior.
- **Risk:** Global search can expose memory outside the current project. The
  scope selected for a query must therefore be explicit to the calling model
  or agent.
- **Risk:** Date-partitioning transcripts changes durable paths. Episode
  `transcript_ref` values, transcript ingestion, backup and restore, and
  existing transcript files must remain compatible.
- **Risk:** Clearing transcripts is irreversible. The behavior must state
  the retired-link representation and ensure episode pages do not appear to
  retain a readable transcript after their raw files are deleted.

## Delivery shape

Likely boundaries include project identity resolution, durable memory layout
and compatibility, project/global search behavior, and date-partitioned
transcript storage with clearing. Legacy migration is an external procedure,
not a runtime delivery boundary.
`author-delivery-brief continue` must confirm the minimum independently
shippable slices before any spec enters the Spec map.

## Governance references

- [`ADR-0001: Use Markdown pages as the memory source of
  truth`](../../adr/0001-use-markdown-pages-as-memory-source-of-truth.md)
  constrains any memory partitioning: Markdown remains authoritative and
  SQLite remains disposable derived state.

## Source provenance

- Direct trusted user instructions in the authoring session on 2026-09-18.
  The decision record below preserves the confirmed source decisions in this
  durable artifact.

## Decision record

- The calling model or agent chooses local or global search for each query.
- Legacy files migrate through an externally invoked harness, skill, or
  prompted procedure; the selected delivery is the manually invoked
  `project-memory-migration` skill, and Memex runtime code does not perform
  migration.
- Clearing transcripts deletes raw transcript files but retains episode pages
  with retired transcript links.
- Hosted synchronization and deletion of transcript-less episode pages require
  separate contracts.
- Project identity favors collision safety: a normalized Git remote when
  available, otherwise a privacy-preserving local derivation.

## Spec map

| Spec | Status |
| --- | --- |
| `project-scoped-memory-migration` | Approved |
