# Spec: Readable project folders

- **Status:** Shipped
- **Owner:** Memex maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** ADR-0001
- **Brief:** none
- **Discovery:** none
- **Contract:** none — existing page front matter and shared Python/CLI/MCP behavior
- **Shape:** data

## Objective

Project memory pages live in directories a person can identify at a glance. A
project with a usable Git origin is stored under `docs/projects/git-<repo>/`;
a local Git repository without an origin and a non-Git workspace use the
workspace folder name. The directory is a readable locator, while the existing
opaque `project_id` remains the logical identity that separates projects.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| User storage contract | Required | `docs/gitpages/spec.md` and `docs/gitpages/guide.md` | maintainers | Documented folder examples and migration boundary | Strict docs build passes |
| Architecture | Required | `docs/architecture/overview.md` | maintainers | Locator and identity ownership | Docs build passes |
| Existing-store procedure | Required | installed `project-memory-migration` skill | maintainers | Preview and backup instructions updated for readable paths | Skill validation and a dry-run preview pass |
| Delivery evidence | Required | `docs/specs/readable-project-folders/notes/verification-ledger.md` | work-loop | Isolated-store tests and smoke results | Reviewed before closeout |

## Boundaries

### Always do

- Keep `project_id` as the logical namespace key in page metadata and the index.
- Derive a safe single path component from the remote repository basename or local folder name.
- Keep Markdown authoritative and SQLite rebuildable from it.
- Refuse a proposed readable folder already associated with a different project ID.

### Ask first

- Move or rewrite files in an existing user data directory; follow the external migration procedure's backup, preview, and operation-specific confirmation.
- Introduce a public alias/configuration surface for resolving same-name collisions.
- Change the existing project identity derivation or privacy guarantees.

### Never do

- Merge distinct projects because their readable names match.
- Persist a raw remote URL, credentials, internal hostname, or absolute source/workspace path in project metadata or the folder locator.
- Add legacy-store migration code to `src/memex`, a new top-level module boundary, or a new runtime dependency.

## Testing Strategy

TDD checks the naming and collision invariants with GitHub, self-hosted Git,
local Git, and non-Git inputs because each has a deterministic expected
directory. Storage integration tests check that front matter, lookup, equal
slugs, and a force index rebuild still honor `project_id`. Goal-based checks
validate documentation and the external migration preview. A manual smoke
uses an isolated `MEMEX_DATA_DIR` to write and recall a project page, then
inspects its path; it never uses the developer's live store.

## Acceptance Criteria

- [x] AC-0001: For an automatically derived project with no existing page directory, a usable Git origin ending in repository `memex`, including a self-hosted origin, stores a new page under `docs/projects/git-memex/<type>/`.
- [x] AC-0002: For an automatically derived project with no existing page directory and no usable Git origin, a local Git repo or non-Git folder named `memex` stores a new page under `docs/projects/memex/<type>/`.
- [x] AC-0003: Every proposed project-page destination resolves inside the resolved Memex data directory beneath non-symlink `docs/projects/` components; an unsafe name or symlink escape is refused without a write, while a valid name produces a readable single-component directory.
- [x] AC-0004: When the proposed readable directory belongs to a different `project_id`, the write fails without modifying either project's pages.
- [x] AC-0005: Project-scoped pages in readable directories retain their opaque `project_id` and display label in front matter; newly generated project metadata contains no raw remote, credentials, internal host, or absolute source path.
- [x] AC-0006: Equal page slugs in distinct project IDs remain separately retrievable, including after a force index rebuild from Markdown.
- [x] AC-0007: Python, CLI, MCP, and dashboard reads resolve project pages through the same readable-directory storage contract.
- [x] AC-0008: Normal runtime operations do not relocate legacy ID-named directories; the external migration procedure previews destinations and refuses collisions before any confirmed move.
- [x] AC-0009: Pages in a legacy ID-named directory remain retrievable by project ID, including after a force index rebuild, until the separately confirmed move.
- [x] AC-0010: A write for a project whose pages occupy one legacy ID-named directory continues in that directory until the separately confirmed move, without creating a second directory for the same project ID.
- [x] AC-0011: If two directories contain the same project ID, type, and slug, page lookup and force rebuild refuse the ambiguous pair instead of silently selecting or overwriting one.
- [x] AC-0012: A write through Python, CLI, or MCP that supplies an explicit project ID without an explicit validated folder locator uses that project's existing directory, or the ID-named directory when no directory exists.

## Follow-ons

None. A public alias mechanism is outside this contract.

## Assumptions

- Technical: Git origin currently supplies an opaque identity, with local path fallback (source: `src/memex/infrastructure/workspace_context.py`).
- Technical: project pages currently use `docs/projects/<project_id>/` (source: `src/memex/infrastructure/wiki_store.py`).
- Product: Git remotes use `git-<repo>` regardless of hosting provider; local Git without origin and non-Git use the folder name (source: user confirmation 2026-09-19).
- Product: same-named projects must not silently merge (source: `docs/product/briefs/project-scoped-memory.md`).
- Process: existing-store moves require a separate backed-up preview and operation-specific confirmation (source: installed `project-memory-migration` skill).
