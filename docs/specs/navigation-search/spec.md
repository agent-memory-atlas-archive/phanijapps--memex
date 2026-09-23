# Spec: Navigation search

- **Status:** Implementing
- **Owner:** Memex maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** ADR-0001, ADR-0002
- **Brief:** none
- **Discovery:** none
- **Contract:** none — extends the existing recall operation with a keyword-only `engine` argument and a CLI flag
- **Shape:** service

> **Spec contract:** Boundaries, Testing Strategy, and Acceptance Criteria are
> completion gates. The plan describes construction.

## Objective

A coding agent whose Memex store has no usable SQLite index (a fresh clone
of a synced `docs/` tree, a deleted `mem.db`, or an emptied `wiki_index`
table) still gets ranked recall instead of an empty answer. The generated
`index.md` navigation files already list every page's title, link, and
description; recall ranks those rows directly, reads the front matter of the
pages it returns, and never opens a page body. The same engine is available
on request (`engine="navigation"`, `memex recall --engine navigation`) so a
user can compare it with the FTS5 ranker or run without SQLite FTS5 at all.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| User-facing promise | New CLI flag and degraded-index behavior | `docs/gitpages/guide.md` | Memex maintainers | `--engine` example and the titles-and-descriptions limit | Guide matches an isolated live invocation |
| Current architecture | New `store/navigation_search.py` module | `docs/architecture/overview.md`, `src/memex/infrastructure/AGENTS.md` | Memex maintainers | Module listed under `store/` with its ownership | Map matches shipped module |
| Release history | User-visible behavior change | `docs/product/changelog.md` | Memex maintainers | Unreleased entry | Entry names the flag, the fallback, and the limits |
| Shipped deviations | Reads only front matter, no access statistics | `docs/gitpages/implementation-notes.md` | Memex maintainers | Note on the engine's limits | Note matches code |

## Boundaries

### Always do

- Classify reserved files with `classify_reserved`/`is_structural`; a legacy
  page at an index path is a memory and its text is never parsed for rows.
- Reuse the FTS5 query boundary (`_query_tokens`, `MAX_QUERY_BYTES`,
  `MAX_QUERY_TOKENS`) instead of copying it.
- Apply the recall visibility rules (active status, `valid_from`/`valid_until`
  window) from front matter before returning a hit.
- Rank deterministically: weighted overlap descending, then slug ascending,
  then path.
- Log only engine names and counts; never the query or page text.
- Exercise the engine only against an isolated `MEMEX_DATA_DIR`.

### Ask first

- Expose `engine` through MCP (`memex_recall`) — the package rule says both
  adapters expose a capability or neither does; this slice was scoped to the
  Python API and CLI.
- Record access statistics for navigation hits (would need index rows).
- Change the title/description weights or add slug or tag matching to the
  ranking.

### Never do

- Never read a page body: the engine reads `index.md` files and the front
  matter block of chosen candidates only.
- Never add a dependency; the engine is standard library plus existing Memex
  modules.
- Never let a row link escape its own directory: only `slug.md` links to
  sibling pages in `global/<type>/` or `projects/<locator>/<type>/` count.

## Testing Strategy

- **Unit (AC-0001..AC-0011):** `tests/unit/test_navigation_search.py` writes
  pages through the `Memex` facade so the generated indexes are real, then
  exercises row parsing (escaped titles and descriptions, project pages),
  ranking and tie-break determinism, filters, visibility, `time_range`
  rejection, a legacy `index.md` page, a spy proving only the front matter of
  the returned page is read (and read once, in project scope too), the byte
  ceiling of the front-matter reader, the zero-row fallback, parity of the
  default recall, the navigation engine, and the fallback over a tree with
  global and project pages, the `time_range` notice on an empty index,
  `max_tokens` packing, and the CLI flag including argparse rejection of an
  unknown engine.
- **Live check:** `memex recall <query> --engine navigation` and a recall
  after `DELETE FROM wiki_index` against `MEMEX_DATA_DIR` under
  `/private/tmp/claude-501/navigation-search-store`.

## Acceptance Criteria

- [x] AC-0001 `NavigationSearch(wiki_dir).search(query)` returns a
  `RecallResult` with `search_engine == "navigation-index-md"` whose hits come
  from structural `index.md` rows; `total_indexed` counts every parsed row.
- [x] AC-0002 Rows are parsed into title (unescaped), description
  (unescaped, empty when the row has none), slug, node type from the heading,
  scope from the path (`global/` or `projects/`), and project directory.
- [x] AC-0003 Score is title-weight 2.0 plus description-weight 1.0 per
  distinct query token; ties break on slug ascending, then path; two searches
  over the same tree return identical `(slug, score)` sequences.
- [x] AC-0004 Query bounds are those of the FTS5 retriever: over
  `MAX_QUERY_BYTES` or `MAX_QUERY_TOKENS`, or no alphanumeric token, raise
  `ValueError`; `top_k` outside [1, 100] raises `ValueError`.
- [x] AC-0005 `node_type` and `tags` (all listed tags) filter hits;
  `scope="global"` spans global and project pages and `scope="project"` with
  `project_id` narrows to that project, exactly as the FTS5 retriever does,
  so the default recall, `engine="navigation"`, and the fallback return the
  same slug set; project scope without `project_id` and an unknown scope
  raise `ValueError`.
- [x] AC-0006 Archived pages are hidden unless `include_inactive=True`; pages
  outside their validity window are hidden unless `include_expired=True`.
- [x] AC-0007 `time_range` raises `ValueError` whose message names
  `navigation-index-md`, from the engine and from `Memex.recall`.
- [x] AC-0008 A legacy Memex page at an `index.md` path contributes no rows
  and is not counted in `total_indexed`.
- [x] AC-0009 For returned hits only the front matter is read: with
  `top_k=1` exactly one page file is opened once (in global and in project
  scope), the bytes consumed stop at the closing `---`, and `Path.read_text`
  is never called on a page.
- [x] AC-0010 `Memex.recall(..., engine="navigation")` serves the engine;
  with the default `engine="fts5"`, an index holding zero rows while
  navigation lists pages returns `search_engine ==
  "navigation-index-md-fallback"` honoring `top_k` and `max_tokens`; an empty
  store stays on the FTS5 path with no hits; a zero-row index with
  `time_range` set answers nothing on the FTS5 path and logs one WARNING
  (`engine=fts5 indexed_rows=0 reason=time_range`), never the query.
- [x] AC-0011 `memex recall --engine {fts5,navigation}` defaults to `fts5`,
  passes the choice through, and rejects any other value.

## Limits (working material)

- Titles and descriptions only: a query that matches body text alone returns
  nothing from this engine.
- Exact token match only: the FTS5 index uses Porter stemming
  (`tokenize='porter unicode61'`), this engine does not, so `setting` does
  not match a page titled `Broker settings` here while FTS5 returns it.
- Linear in the total size of the `index.md` files, plus one front-matter
  open per examined candidate; candidates that fail a tag or visibility
  check cost a read without producing a hit. Measured on a 500-page isolated
  store: 10.3 ms per recall against 2.7 ms for FTS5.
- No stop-word or document-frequency pruning: every alphanumeric query token
  scores. No access statistics are recorded.
- A project filter learns each project directory's id from the front matter
  of the first candidate read there (locators are opaque); that read is the
  same one that fills the hit, so no candidate is opened twice.
- `time_range` on a zero-row index answers nothing (the fallback cannot honor
  it); the WARNING notice is the only signal of the degraded state.
- Pages exist but no `index.md` has been generated: the engine sees zero rows
  and the fallback stays on FTS5. `memex rebuild-index` regenerates navigation.
- The reader stops at the closing delimiter; the operating system's buffered
  read may still fetch up to one 8 KB block of the file.

## Assumptions

- Generated rows follow `NavigationGenerator.render`: `- [Title]` followed by
  the sibling link (`slug.md` in parentheses) with an optional ` — description`, under `## <Typedir>` headings, and
  `]`, `[`, `*`, `_`, `` ` ``, `<`, `>`, `\` escaped with a backslash.
- Pages live at `global/<type>/<slug>.md` or
  `projects/<locator>/<type>/<slug>.md`; any other layout is ignored.
- A stored page's front matter fits in 16 KB (16,384 bytes of UTF-8, counted
  as bytes, not characters).
