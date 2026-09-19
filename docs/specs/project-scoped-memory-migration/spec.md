# Spec: Project-scoped memory

- **Status:** Shipped
- **Owner:** Memex maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** ADR-0001
- **Brief:** `docs/product/briefs/project-scoped-memory.md`
- **Discovery:** none
- **Contract:** none — shared Python, CLI, and MCP contract
- **Shape:** mixed

## Objective

Memex stores new memories in readable project or global namespaces. Calling
agents select local or global recall per query, transcripts are grouped by UTC
capture date, and clearing raw transcripts retains an episode with a retired
reference. Existing stores move only through the manually invoked
`project-memory-migration` skill.

The namespace, recall, index, and transcript contracts ship together because a
partial release could write data that another adapter cannot find or rebuild.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| User contract | Required | `docs/gitpages/spec.md` | maintainers | Updated storage/command docs | Docs build passes |
| Architecture | Required | `docs/architecture/overview.md` | maintainers | Namespace ownership documented | Docs build passes |
| Legacy procedure | Required | `project-memory-migration` skill | maintainers | Validated procedure | Skill validates |

## Boundaries

### Always do

- Keep Markdown authoritative and rebuild SQLite entirely from page metadata.
- Apply namespace behavior identically through Python, CLI, MCP, storage, and index.
- Require confirmation before deleting raw transcript files.
- Support only one explicitly selected local project or all namespaces for a
  recall; legacy-store movement remains outside the runtime boundary.

### Ask first

- Change identity privacy guarantees, add runtime dependencies, or add automatic migration.

### Never do

- Add legacy migration behavior to `src/memex`.
- Persist raw remotes, credentials, internal hosts, or absolute paths.
- Delete episode pages when clearing transcripts.

## Testing Strategy

Namespace, indexing, and retirement invariants use TDD with isolated data
directories. Shared CLI/MCP behavior uses integration tests. Real CLI transcript
ingest, local/global recall, and confirmed clear are exercised manually.

The suite covers positive scoped writes, duplicate slugs in separate namespaces,
local exclusion and global inclusion, rebuild from pages, date-path generation,
and retired episode references. It also proves refusal of unsafe metadata and
unconfirmed clearing, and asserts that no runtime operation relocates a legacy
flat store.

## Acceptance Criteria

- [x] AC-0001: New pages record scope; project pages record opaque project ID and display label, while raw remote and absolute-path values are absent from pages and index.
- [x] AC-0002: Equal type/slug values in different namespaces remain distinct and recall results expose namespace metadata.
- [x] AC-0003: Local recall returns only its selected project; global recall returns matching pages from all namespaces.
- [x] AC-0004: Transcript ingestion stores transcript and metadata below `transcripts/<yyyy-mm-dd>/` and records a resolving relative reference on its episode.
- [x] AC-0005: Confirmed transcript clear deletes raw transcript files, retains episodes, and marks their references retired.
- [x] AC-0006: A force index rebuild preserves scoped recall from Markdown alone.
- [x] AC-0007: Python, CLI, and MCP expose the same scope and transcript-clear behavior.

## Follow-ons

- Maintainers: `project-memory-migration` skill — manually migrate legacy flat stores after preview and confirmation.

## Assumptions

- Technical: Memex is Python 3.12+ with shared package/CLI adapters (source: `pyproject.toml`).
- Technical: current page/index slugs are globally unique, so namespace identity is durable (source: `wiki_store.py`, `index_manager.py`).
- Product: migration remains outside runtime code (source: user confirmation 2026-09-18).
- Process: the slice derives from the Ready brief (source: `workspace.toml`).
