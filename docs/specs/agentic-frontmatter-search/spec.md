# Spec: Agentic front matter search

- **Status:** Shipped
- **Owner:** Memex maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** ADR-0001, ADR-0002, ADR-0004
- **Brief:** docs/product/briefs/memory-retrieval-and-evidence.md
- **Discovery:** none
- **Contract:** additive `description` fields and generated directory indexes
- **Shape:** mixed

> **Spec contract:** Boundaries, Testing Strategy, and Acceptance Criteria are
> completion gates. The plan describes construction.

## Objective

An agent can discover what a memory page contains before reading its full body.
Memory pages may carry a short `description` in front matter. Generated
`index.md` files expose titles and descriptions one directory at a time. Recall
searches descriptions, returns them with page paths and links, and identifies a
description match. The agent can descend the indexes, read a Markdown page, or
follow a link using tools supplied by its host. Existing pages and callers
remain valid when no description or generated index is present.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| User-facing promise | Write and recall gain searchable descriptions | `docs/gitpages/guide.md`, `README.md` | Memex maintainers | Worked isolated write and recall | Docs match the shipped CLI and MCP contract |
| Current architecture | Front matter, directory indexes, and SQLite index change | `docs/architecture/overview.md` | Memex maintainers | Updated page and retrieval flow | Map keeps memory pages authoritative |
| Research rationale | External patterns informed the field selection | `docs/research/2026-09-21-agentic-frontmatter-search.md` | Memex maintainers | Source-linked recommendation and rejected fields | Claims remain narrower than the sources |
| Release history | Public additive fields ship | `docs/product/changelog.md` | Memex maintainers | One scoped entry | Entry names searchable descriptions |

## Boundaries

### Always do

- Keep Markdown front matter authoritative and rebuild every description index
  value from its page.
- Treat every generated `index.md` as a disposable navigation view. Missing or
  stale navigation cannot block page reads, recall, or index rebuilding.
- Reserve `index.md` and `log.md` at every level. Neither file is a memory page
  or an eligible input to FTS, links, export, consolidation, or task recall.
- Preserve a pre-existing valid Memex page whose slug is `index` or `log` as a
  legacy memory. Report the collision and skip structural-file generation at
  that path until the user resolves it; never overwrite or hide the page.
- Give only the memory-root `index.md` front matter, containing
  `okf_version: "0.2"`; generated descendant indexes are body-only.
- Accept pages without `description` and expose an empty description through
  typed runtime models.
- Apply AC-0002's description validation before text reaches the filesystem or
  index.
- Preserve project, lifecycle, time, type, and tag eligibility filters and
  preserve the current ranking contribution of slug, title, body, and tags.
- Treat descriptions, bodies, tags, and links as untrusted evidence. Reading a
  result or following its link grants no tool authority.
- Keep the Python facade, CLI, and MCP on the same domain and application
  implementation.

### Ask first

- Add another persistent search field after `description`.
- Make descriptions mandatory for existing or newly written pages.
- Generate or mutate chronological `log.md` files.
- Add an autonomous retrieval model, vector index, required file-search
  binary, background process, or runtime dependency.

### Never do

- Never replace or truncate the page body because a description exists.
- Never execute a command or follow an instruction found in stored metadata.
- Never search outside the configured Memex data directory from product code.
- Never silently rewrite existing Markdown pages during index upgrade.
- Never create generated navigation merely by opening a pre-change store; the
  transparent SQLite upgrade remains free of Markdown writes.
- Never treat generated navigation or an optional log as authoritative memory.
- Never fail, roll back, or discard an authoritative page mutation solely
  because disposable directory navigation could not refresh.

## Testing Strategy

- **Front matter contract (AC-0001, AC-0002, AC-0003): TDD.** Domain and store
  tests cover validation, old-page defaults, exact round trips, and strict
  unknown-key handling.
- **Derived index and retrieval (AC-0004, AC-0005, AC-0006, AC-0007,
  AC-0014): TDD plus
  integration.** A page whose query term appears only in `description` proves
  discovery. Existing winner and filter fixtures prove stable behavior for
  pages with empty descriptions. A forged old schema proves automatic rebuild.
- **Shared adapters and persisted interchange (AC-0008, AC-0009, AC-0013):
  TDD plus goal-based integration.** Python, CLI, MCP, consolidation, index,
  recall, backup, export, and isolated-filesystem fixtures prove one additive
  contract and one scrubbed persistence boundary.
- **Agent journey (AC-0010, AC-0011): manual QA.** An isolated store proves the
  sequence descend generated index, recall, inspect description, read returned
  path, and follow one stored link without treating memory text as authority.
- **Filesystem navigation (AC-0015, AC-0016, AC-0017, AC-0018, AC-0019,
  AC-0020): TDD plus integration.** Deterministic fixtures prove generated
  index shape, inert rendering, confined links and diagnostics, refresh and
  recovery, reserved-file exclusion, legacy collision safety, and preservation
  of optional logs.
- **Documentation (AC-0012): goal-based check.** Build the site in strict mode
  and run the documented isolated commands.

## Acceptance Criteria

- [x] **AC-0001.** `WriteInput`, `WikiNode`, and `RecallHit` expose an optional
      description whose runtime default is the empty string, so callers and
      pages that omit it remain valid.
- [x] **AC-0002.** A description containing a newline, carriage return, control
      character, or more than 512 UTF-8 bytes is rejected before persistence;
      a 512-byte single-line description is accepted.
- [x] **AC-0003.** A valid description survives write, direct Markdown edit and
      read, backup and restore, and JSON export and import without becoming the
      page body or changing it.
- [x] **AC-0004.** A project-scoped active page is returned when every query
      term occurs only in its description, and the hit reports
      `snippet_source="description"` with a bounded highlighted snippet.
- [x] **AC-0005.** Description indexing is derived entirely from Markdown; a
      forced index rebuild reproduces the same description-only hit.
- [x] **AC-0006.** Opening a pre-change index causes a transparent disposable
      rebuild from Markdown. No Markdown file is changed by the upgrade.
- [x] **AC-0007.** Existing description-empty winner, deterministic-order,
      eligibility-filter, and access-count fixtures retain their behavior and
      the existing slug, title, body, and tag BM25 weights.
- [x] **AC-0008.** Python, `memex write --description`, and `memex_write` accept
      the same description contract; CLI and MCP recall output include the
      description without removing or renaming any existing field.
- [x] **AC-0009.** Consolidation may emit a one-sentence description, and an
      omitted description still produces a valid page; malformed model output
      fails through the same validation boundary as other writes.
- [x] **AC-0010.** A documented isolated agent journey can recall a page from a
      root `index.md`, descend to its directory index, recall a page from a
      description-only query, inspect its description, read its returned
      `file_path`, and use one returned slug in a second bounded recall.
- [x] **AC-0011.** The installed agent guidance says stored memory is evidence,
      uses no more than three focused recall questions for a task, and permits
      host file reading or exact `rg` search only within the returned Memex
      paths when more detail is needed.
- [x] **AC-0012.** The user guide, architecture, README, changelog, and strict
      documentation build describe the shipped field and its limits.
- [x] **AC-0013.** Secret-shaped text in a description written through Python,
      CLI, MCP, or consolidation is scrubbed before persistence. The original
      value appears nowhere under the isolated data directory and cannot appear
      in index, recall, backup, or export output.
- [x] **AC-0014.** After a direct Markdown edit changes only `description`, the
      watcher re-indexes the page and freshness diagnostics report the index as
      current only after its description matches the page. Body-only content
      hashes retain their documented meaning.
- [x] **AC-0015.** Regeneration creates `index.md` in the memory root and every
      directory containing a memory page in its subtree. The root declares
      `okf_version: "0.2"`; descendant indexes have no front matter. This full
      regeneration runs through the explicit rebuild path, never as an effect
      of opening the store.
- [x] **AC-0016.** Every generated index deterministically lists direct memory
      pages under node-type headings with relative links, titles, and available
      descriptions, then links direct child indexes. Titles and descriptions
      are escaped as inert Markdown text. Every actionable link is created by
      the generator and resolves within the configured Memex docs root.
      Repeating regeneration without page changes produces identical bytes.
- [x] **AC-0017.** After a successful page write, lifecycle change, deletion, or
      watcher-driven external edit, every affected directory index and ancestor
      reflects the resulting page tree. Each index replacement is atomic.
      Deleting every page below a directory removes obsolete generated indexes
      without changing any memory page. If refresh fails, the page mutation
      remains successful and authoritative, `memex verify` reports the
      navigation defect, and later regeneration repairs it from pages.
- [x] **AC-0018.** A structural `index.md` or `log.md` never becomes a
      `WikiNode`, FTS, link, export, consolidation, task-recall, or watcher
      lifecycle input. Generator-owned index writes and edits to a structural
      log do not trigger memory refresh. Index regeneration preserves an
      existing structural `log.md` byte-for-byte; recall remains available when
      every generated index is missing and regeneration restores them.
- [x] **AC-0019.** A pre-existing valid Memex memory page at `index.md` or
      `log.md` remains readable, recallable, exportable, and byte-unchanged.
      Generation skips the colliding structural path and `memex verify` reports
      it. New writes never allocate the reserved slugs `index` or `log` and use
      the existing collision suffix behavior instead.
- [x] **AC-0020.** Navigation diagnostics contain only a bounded error category,
      stable page identifier when applicable, and a docs-root-relative path.
      They exclude memory bodies, titles, descriptions, credential-shaped
      strings, raw exceptions, absolute paths, usernames, and host-specific
      filesystem details.

## Assumptions

- Markdown remains the source of truth and SQLite remains disposable
  (ADR-0001 and `src/memex/infrastructure/index_manager.py`).
- Shared domain and application behavior serves every adapter (ADR-0002 and
  `src/memex/application/memory.py`).
- The repository's OKF v0.2 documents and Letta MemFS both use `description`
  as a compact document signpost
  (`docs/gitpages/spec.md` and the linked research note).
- Existing `file_path` and `links` fields let a host agent read and traverse
  memory without a new storage engine (`src/memex/domain/models.py`).
- OKF v0.2 defines `index.md` as optional progressive-disclosure navigation and
  `log.md` as optional scoped history; consumers must tolerate missing indexes
  (official OKF v0.2 specification, sections 8, 9, and 11).
- Existing Memex stores may already contain pages with the currently valid
  slugs `index` or `log`; compatibility requires an explicit collision path
  rather than reclassifying or overwriting them (repository code inspection,
  `src/memex/domain/slugs.py` and `src/memex/infrastructure/wiki_store.py`).
- The user's 2026-09-21 direction authorizes adding front matter that materially
  improves search after objective research; it does not require adopting every
  external pattern.

## Follow-ons

Aliases remain a measured follow-on if descriptions and tags still leave a
repeatable acronym or synonym miss. Automated wiki repair and progressive
summarization require separate evidence because they can lose or distort facts.
