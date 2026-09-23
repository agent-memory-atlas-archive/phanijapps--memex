# Spec: Incremental navigation refresh

- **Status:** Implementing
- **Owner:** Memex maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** none
- **Brief:** none
- **Discovery:** none
- **Contract:** none — internal store behavior behind the existing write, forget, approve, merge, and hook paths
- **Shape:** service

> **Spec contract:** Boundaries, Testing Strategy, and Acceptance Criteria are
> completion gates. The plan describes construction.

## Objective

A coding agent that writes, updates, or deletes one memory page pays for that
page and its directory index, not for every sibling page in the directory. The
generated `index.md` files keep the exact bytes a full regeneration would
produce, so `memex verify` stays green and readers see no format change, while
a directory holding a thousand pages accepts a write in the same time as an
empty one.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Release history | Per-write cost changes | `docs/product/changelog.md` | Memex maintainers | Unreleased "Changed" bullet | Bullet names the splice and the fallback |
| Shipped deviation | Facade re-reads the mutated page | `docs/gitpages/implementation-notes.md` | Memex maintainers | One paragraph on the single-page re-read | Note matches `Memex._refresh_navigation` |

## Boundaries

### Always do

- Produce index bytes equal to `render(directory, scan_dir(directory))` after every single-page refresh.
- Use the existing reserved-file classification to decide whether an `index.md` is generator-owned.
- Keep `rebuild-index` on the full regeneration path.
- Keep diagnostics bounded: docs-relative paths only, never page content.

### Ask first

- Change the rendered index format (headings, ordering, escaping, front matter).
- Change the watcher's directory-level refresh contract.

### Never do

- Never parse a sibling page during a single-page refresh that finds a generator-shaped index.
- Never overwrite a legacy page or an unclassifiable file at `index.md`.

## Testing Strategy

- **Determinism oracle (AC-0001, AC-0002, AC-0005): seeded randomized unit test.** A fixed-seed sequence of creates, title and description updates, and hard deletes across two type directories asserts `NavigationGenerator.diagnose` is empty after every step, so each index equals the full render and no index is missing or orphaned.
- **Bounded cost (AC-0003, AC-0004): unit tests with a `Path.read_text` spy and a `scan_dir` spy.** One write with 4 siblings and one with 199 siblings open the same two files; create, update, and delete never call `scan_dir`.
- **Fallbacks (AC-0006, AC-0007, AC-0008): unit tests.** Missing index, hand-written structural index, ambiguous row, unlisted deleted page, orphan index (bare heading), unparsable mutated page, legacy page at the index path.
- **Verify (AC-0009): unit test.** `verify` reports `navigation-consistent` ok after a mixed sequence of incremental refreshes.

## Acceptance Criteria

- [x] **AC-0001.** After one page create, update, or delete, the directory's `index.md` bytes equal the full render of that directory's parsed pages.
- [x] **AC-0002.** After the last page of a directory is deleted, that directory's index is removed and the nearest ancestor that still holds pages lists the surviving child directories exactly as the full render does.
- [x] **AC-0003.** A single-page refresh that finds a generator-shaped index opens exactly two `.md` files under the docs root, the page and its directory index, regardless of sibling count.
- [x] **AC-0004.** A single-page refresh that keeps the directory populated does not open any ancestor `index.md`.
- [x] **AC-0005.** `rebuild-index` rewrites every needed index from a full scan.
- [x] **AC-0006.** When the directory index is missing, is a structural file the generator did not write, is a bare heading with no rows, or lists the page under more than one heading, the refresh falls back to the full chain render and the resulting bytes equal the full render.
- [x] **AC-0007.** When a delete concerns a page the index does not list, or the mutated page cannot be parsed by the store, the refresh falls back to the full chain render, so no stale row survives.
- [x] **AC-0008.** A legacy memory page at `index.md` is left byte-identical and reported as `collision`.
- [x] **AC-0009.** `memex verify` reports `navigation-consistent` ok after creates, updates, and deletes performed through the facade.
- [x] **AC-0010.** Per-write cost does not grow with sibling count: on one tree and one run of the bench in the plan, the facade write at 1000 pages costs no more than the write at 0 pages, and `refresh_page` costs at least 10x less than the chain `refresh` of the same directory at 600 pages and above (throwaway evidence 2026-09-23: write 26.9 / 19.9 / 15.7 ms at 0 / 600 / 1000 pages; refresh_page 12.7 ms vs chain 509.1 ms at 600, 6.9 ms vs 745.2 ms at 1000). The bounded-cost unit tests (AC-0003) are the regression guard; the timings are evidence, not a test.

## Follow-ons

- Memex maintainers: `WikiStore._read_path` is the only single-page reader; add `def read_path(self, path: Path) -> WikiNode: return self._read_path(path)` to `WikiStore` and switch `Memex._refresh_navigation` to it (the store module is outside this change's ownership). Then give `_refresh_navigation` a keyword `node: WikiNode | None` so `write`, `forget`, `approve`, and `merge` pass the node they already hold and skip the re-read.
- Memex maintainers: hoist the local `WikiStoreError` import in `Memex._refresh_navigation` into the module's `memex.domain.errors` import line; it is local only because the import block was outside this change's ownership.

## Assumptions

- Technical: a page's slug is always its file stem, so the entry link `slug.md` identifies its sorted position (source: `WikiStore._read_path`, `node.slug = path.stem`).
- Technical: the escaped title never contains a bare `]`, so the first unescaped `](` in an entry line opens the generator's own link (source: `navigation._escape`, `_ESCAPE_CHARS` includes `[]\`).
- Technical: ancestor indexes hold no page entries of their own; they change only when a child directory gains or loses its first page (source: `WikiStore.scan_dir` returns `[]` for non-type directories).
- Process: the facade paths that call the refresh pass only the page path, so the facade re-reads that one page to obtain title, description, and type (source: `Memex._refresh_navigation` call sites, probe 2026-09-23).
