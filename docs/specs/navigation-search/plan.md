# Plan: Navigation search

- **Spec:** [`spec.md`](spec.md)
- **Status:** Executing
- **Repository anchors:** ADR-0001 (Markdown is the truth, the index is
  disposable), ADR-0002 (shared behavior in the facade, thin adapters);
  `src/memex/infrastructure/store/navigation.py` (`render` fixes the row
  format), `src/memex/domain/reserved.py` (`classify_reserved`),
  `src/memex/infrastructure/search/bm25_retriever.py` (query boundary and
  visibility rules to mirror), `src/memex/infrastructure/store/wiki_store.py`
  (`TYPE_DIRS`, `_node_from_dict`), `src/memex/application/memory.py:recall`,
  `src/memex/cli.py`.

> **Plan contract:** Tasks, Tests, Touches, and Done when are the build gates.

## Approach

Add one module, `store/navigation_search.py`, that turns generated
navigation rows into a ranked `RecallResult` without SQLite. Keep the facade
in charge of engine choice: `Memex.recall` gains `engine` and, on the FTS5
path, checks `IndexManager.count()` once; zero rows with pages listed in
navigation routes the call to the new engine and renames `search_engine` so
callers can see the degradation. The CLI passes a `choices` flag straight
through. Every predicate the engine needs already exists (`is_structural`,
`_query_tokens`, `_stable_dedupe`, `check_slug`, `_node_from_dict`,
`parse_front_matter`, `pack_to_budget`) and is imported, not copied.

## Constraints

- Owned files only: the new module, `Memex.recall` and its helper, the CLI
  recall parser and dispatch, the new test file, and this spec directory.
- MCP unchanged in this slice (recorded as an ask-first in the spec).
- No new dependency; standard library plus existing Memex modules.
- Diagnostics carry engine names and counts only.

## Construction tests

**Unit:** `uv run pytest tests/unit/test_navigation_search.py -q --no-cov`
(16 tests). Regression: `tests/unit/test_facade.py`, `tests/unit/test_cli.py`,
`tests/unit/test_budget_recall.py` (43 tests) still pass.
**Static:** `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`
on the four owned files.
**Live:** isolated `MEMEX_DATA_DIR` under `/private/tmp/claude-501/`: write
two pages, recall with each engine, empty `wiki_index`, recall again, read
the log tail.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Guide | T4 | `--engine` example from the live check | Guide matches CLI help |
| Architecture and infrastructure AGENTS table | T4 | Module row under `store/` | Map matches module |
| Changelog | T4 | Unreleased entry | Names flag, fallback, limits |
| Implementation notes | T4 | Front-matter-only and no-access-statistics note | Note matches code |

## Design (LLD)

### Design decisions

- Higher score is better for this engine (weighted overlap), unlike FTS5's
  ascending `bm25()`; `RecallHit.score` is documented per engine rather than
  normalized, since callers already read `search_engine`.
- Candidates are walked best-first and front matter is read per candidate
  until `top_k` visible hits are found, so a `tags` filter and hidden pages
  cannot silently shrink the result below `top_k` while matches remain.
- Row links are validated lexically (`slug.md`, `check_slug`) after resolving
  each index directory once; the earlier per-row `Path.resolve` cost 45 of
  69 ms per ten searches on a 500-page store.
- The fallback skips `time_range` requests: the engine cannot honor them, and
  raising from a plain FTS5 call would surprise callers; those requests keep
  the empty FTS5 answer.

### Data & schema

`_Row(title, description, path, slug, node_type, scope, project_dir)` —
parsed from one line, no page opened. Hits are ordinary `RecallHit`s; no
model change was needed.

### Interfaces & contracts

- `NavigationSearch(wiki_dir, *, default_top_k=10, clock=utc_now_iso).search(query, *, top_k, node_type, time_range, tags, include_expired, include_inactive, scope, project_id) -> RecallResult`
- `SEARCH_ENGINE = "navigation-index-md"`,
  `FALLBACK_SEARCH_ENGINE = "navigation-index-md-fallback"`
- `Memex.recall(..., engine: Literal["fts5", "navigation"] = "fts5")`
- `memex recall <query> --engine {fts5,navigation}`

### Failure, edge cases & resilience

- Unreadable, symlinked, malformed, or oversized-front-matter pages are
  skipped as candidates; the search still answers.
- Legacy or undecodable `index.md` files are skipped via `classify_reserved`.
- Links with a directory component, `..`, or a non-kebab stem are ignored.

### Quality attributes (NFRs)

500 pages, isolated store, Apple Silicon: FTS5 2.7 ms, navigation 10.3 ms
per recall; deterministic across runs.

## Tasks

### T1: Failing tests

- **Tests:** `tests/unit/test_navigation_search.py` covering AC-0001..AC-0011.
- **Touches:** the new test file.
- **Done when:** the file fails on the missing module. Done.

### T2: Engine module

- **Tests:** T1 engine tests pass.
- **Touches:** `src/memex/infrastructure/store/navigation_search.py`.
- **Done when:** parsing, ranking, filters, visibility, front-matter-only
  reads, and `time_range` rejection pass; ruff and mypy clean. Done.

### T3: Facade and CLI

- **Tests:** T1 facade, fallback, and CLI tests pass.
- **Touches:** `Memex.recall`, `Memex._navigation_recall`, CLI `--engine`.
- **Done when:** all 16 tests pass and the live check shows the three engine
  names with count-only log lines. Done.

### T4: Shared documentation

- **Touches:** changelog, guide, architecture overview, infrastructure
  AGENTS table, implementation notes — via the integrating agent.
- **Done when:** the snippets returned with this slice are merged.

## Rollout

- **Delivery:** default behavior changes only when the index has zero rows
  and navigation lists pages; otherwise opt-in via `engine`. Reversible by
  removing the flag and the count check.
- **Infrastructure:** none.
- **External-system integration:** none.
- **Deployment sequencing:** none.

## Risks

- MCP callers cannot choose the engine; the package rule prefers parity.
- Body-only matches are invisible to this engine; users may expect FTS5
  parity from the same command.
- Another slice added an entry parser (`_entry_link`) to `navigation.py`; the
  two parsers agree on the escape rule but live apart.

## Changelog

- 2026-09-23: plan drafted and executed; per-row `resolve` replaced by
  once-per-index resolution after profiling.
