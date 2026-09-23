# Plan: Incremental navigation refresh

- **Spec:** [`spec.md`](spec.md)
- **Status:** Executing
- **Repository anchors:** `src/memex/infrastructure/store/navigation.py` (`render`, `refresh`, `_write_index`, reserved-file classification via `memex.domain.reserved.is_structural`); `Memex._refresh_navigation` and `_on_page_written` in `src/memex/application/memory.py`; tests in `tests/unit/test_navigation.py`; deviation: the facade reads the mutated page through the store's private `_read_path` because no public single-path reader exists.

> **Plan contract:** `Touches`, `Tests`, and `Done when` are pinned; the rest is working material.

## Approach

Split `render` into a parser-shaped middle: entries keyed by node type then slug, plus child-directory names, serialized by one `_compose`. `refresh_page(page_path, node, scan_dir)` reads the directory's `index.md`, checks it is structural with the existing classifier, parses it back into that middle form with `_parse_index` (verbatim entry lines, only each link inspected), removes the page's row, inserts the fresh row rendered by the same `_entry` used by `render`, and writes through the existing atomic `_write_index`. Anything the parser does not recognise, an ambiguous row, an unlisted delete, or an orphan index falls back to the unchanged `refresh(directory, scan_dir)` chain path. When the directory loses its last page the index is removed and ancestors are walked up only until one still holds pages. The facade determines create-or-update versus delete by whether the page file exists and re-reads that one page. The riskiest part is byte equality between splice and full render; a seeded randomized oracle guards it.

## Constraints

- Rendered index format is fixed by the agentic-frontmatter-search spec (AC-0015..AC-0020) and `memex verify`'s `navigation-consistent` check.
- The watcher keeps calling `refresh(directory, scan_dir)`; that contract is unchanged.
- Only the two facade methods that call the refresh may change in `memory.py`.

## Construction tests

**Integration tests:** `test_verify_navigation_stays_consistent_through_incremental_refreshes` (facade write, update, delete, then `verify`).
**Manual verification (throwaway evidence, not a test):** the bench below, run once per page count with `MEMEX_DATA_DIR` under a scratch directory. It seeds N entity pages in one directory, then times 20 facade writes, 20 `_refresh_navigation` calls, and 20 chain `refresh` calls of the same directory. Results 2026-09-23 on the reference laptop: before the splice, 354.1 ms per write at 600 pages. After: `pages=0 write_ms=26.9 refresh_page_ms=10.4 chain_refresh_ms=42.5`, `pages=600 write_ms=19.9 refresh_page_ms=12.7 chain_refresh_ms=509.1`, `pages=1000 write_ms=15.7 refresh_page_ms=6.9 chain_refresh_ms=745.2`. Absolute numbers move run to run by about 10 ms; the flat shape and the 40x to 100x gap to the chain refresh are the claim.

```python
"""Per-write navigation cost vs sibling count, plus the chain refresh for comparison."""
import shutil, sys, time
from pathlib import Path
from memex.application.memory import Memex
from memex.domain.models import WriteInput
from memex.infrastructure.config import ConfigLoader

root = Path(sys.argv[2])  # scratch data dir, never ~/.memex
shutil.rmtree(root, ignore_errors=True)
memex = Memex(ConfigLoader().load(data_dir=root))
n = int(sys.argv[1])
for i in range(n):
    memex.write(WriteInput(type="entity", title=f"seed page {i:04d}", body="b", description="d"))
entities = memex.wiki_store.wiki_dir / "global" / "entities"
rounds = 20
t0 = time.perf_counter()
bench = [memex.write(WriteInput(type="entity", title=f"bench {i:04d}", body="b")) for i in range(rounds)]
write_ms = (time.perf_counter() - t0) * 1000 / rounds
t0 = time.perf_counter()
for node in bench:
    memex._refresh_navigation(node.file_path)
refresh_ms = (time.perf_counter() - t0) * 1000 / rounds
t0 = time.perf_counter()
for _ in range(rounds):
    memex.navigation.refresh(entities, memex.wiki_store.scan_dir)
chain_ms = (time.perf_counter() - t0) * 1000 / rounds
print(f"pages={n} write_ms={write_ms:.1f} refresh_page_ms={refresh_ms:.1f} chain_refresh_ms={chain_ms:.1f}")
memex.close()
```

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| Changelog bullet | T3 | `shared_doc_snippets.changelog` | Bullet merged under Unreleased |
| Implementation note on the single-page re-read | T3 | `shared_doc_snippets.implementation_notes` | Note merged |

## Design (LLD)

### Interfaces & contracts

`NavigationGenerator.refresh_page(page_path: Path, node: WikiNode | None, scan_dir: ScanDir) -> NavigationReport`; `node is None` means deleted. Traces to AC-0001..AC-0004, AC-0006..AC-0008. `refresh` and `regenerate` unchanged (AC-0005).

### Failure & resilience

Every unrecognised index shape returns `None` from `_parse_index` and takes the full chain path, so a wrong guess costs time, never bytes. A mutated page the store cannot parse (`WikiStoreError`) also takes the chain path: the page is invisible to a full render, so its row is dropped rather than left stale. Filesystem failures remain `write_failed` report entries; the facade still swallows exceptions and logs a bounded warning.

## Tasks

### T1 — Failing tests
Touches: `tests/unit/test_navigation.py`.
Tests: randomized oracle; constant open count (4 vs 199 siblings); no `scan_dir` call; fallbacks; ancestor walk on last delete; verify green; rebuild unchanged.
Done when: the new tests fail against the chain refresh for cost reasons and pass for correctness reasons.

### T2 — Splice implementation
Touches: `src/memex/infrastructure/store/navigation.py`, `Memex._refresh_navigation`.
Tests: T1 suite green; ruff and mypy clean on the touched files.
Done when: `uv run pytest tests/unit/test_navigation.py -q --no-cov` passes and the bench shows a flat per-write cost between 600 and 1000 pages.

### T3 — Records
Touches: this directory; shared snippets returned to the integrating agent.
Done when: changelog and implementation-notes text exist.

## Changelog

- 2026-09-23: drafted and executed in one pass; measured 354.1 ms → 14.2 ms per write at 600 pages.
- 2026-09-23: review fixes. Unparsable mutated page falls back to the chain refresh (test added); orphan-index fallback pinned by a test; AC-0010 restated as a relative claim with the bench inlined here; the public `read_path` and the import hoist recorded as follow-ons because `wiki_store.py` and the import block sit outside this change's ownership.
