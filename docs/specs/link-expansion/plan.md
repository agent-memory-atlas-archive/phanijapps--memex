# Plan: Link-graph expansion in recall packing

- **Spec:** [`spec.md`](spec.md)
- **Status:** Implementing

## Anchors

- `src/memex/infrastructure/search/link_manager.py` — `wiki_links` rows
  `(source_scope, source_project_id, source_slug, target_slug, rel)`; targets
  are bare slugs.
- `src/memex/infrastructure/search/bm25_retriever.py` —
  `BM25Retriever.neighbours` joins the link graph to the index under the one
  visibility rule (active status, validity window, scope/project) recall
  applies.
- `src/memex/application/context_injection.py` — `estimate_tokens`,
  `pack_to_budget`, `format_context_block`, `build_injection` (session-start).
- `src/memex/application/task_recall.py` — `assemble_task_recall` renders the
  task context and charges it to `request.max_tokens`.
- `eval/agent_workflow.py` — `_current_injection_result` scores every
  `File:` line of the block, so expanded pages count as coverage.

## Approach

1. New `src/memex/application/graph_expansion.py`:
   `expand_links(memex, seeds, *, depth=1, max_tokens) -> Expansion`.
   Breadth-first from the seed hits; one SQL join from `wiki_links` to
   `wiki_index` per frontier node, resolving the target in the source's
   namespace or global scope, filtered by the retriever's visibility clauses
   for the recall's own `scope`/`project_id` (`build_injection`: global;
   task recall: the request's project); body read only to the snippet
   margin; each level sorted by slug; first discovery fixes the route.
   `_pack` keeps everything when the total fits, otherwise reserves the
   marker and keeps entries until the first that does not fit.
   `render_expansion` yields block lines plus the marker.
2. `format_context_block(result, *, linked=())` appends the linked lines
   before the footer. `build_injection(..., depth=1)` packs direct hits as
   before, expands into `budget - estimate_tokens(block)`, and returns the
   expanded block only when it fits.
3. `with_linked_pages(memex, request, result, selected, *, depth=1)` appends
   linked lines after the gap lines when the result still fits
   `request.max_tokens`; `assemble_task_recall` stays pure.
4. Re-pin the benchmark and add the 2026-09-23 amendment table.

## Construction tests

`tests/unit/test_link_expansion.py` (15 tests, all against an isolated
`Memex` store under `tmp_path`):

- level order and alphabetical tie-break at depth 1 and 2, routes, determinism
- block shape: header names concept, depth, and route; description preferred;
  body never rendered; snippet fallback capped at 200 characters
- cycle safety at depth 5 and seed exclusion
- budget cut, omitted count, marker text, rendered size within budget; an
  exact-fit budget keeps every entry with no marker
- two-line block when description and body are blank
- visibility: archived, soft-forgotten, pending, other-project, same-slug
  other-project neighbours never expanded under either recall scope
- project seed to global page: expanded under global recall, not under
  project recall; global seed on the session-start path stays global
- negative depth rejected
- `build_injection`: direct hits first, links after, marker when links do not
  fit, total within budget
- `with_linked_pages`: same sources and prefix as the plain result,
  marker within `max_tokens`

Isolated benchmark check: one script runs `run_benchmark()` twice in the same
tree with `build_injection` bound to `depth=0` and then the default, so the
expansion effect is separated from concurrent retriever edits.

## Tasks

- [x] Record the four benchmark tuples before any change.
- [x] Write the failing unit tests.
- [x] Implement `graph_expansion.py`.
- [x] Wire `build_injection` and `format_context_block`.
- [x] Wire task recall through `with_linked_pages`.
- [x] Re-run the benchmark; pin `expected_metrics`; amend the baseline report.
- [x] Owned-file gates: ruff format, ruff check, mypy, pytest.
- [x] Review fixes: exact-fit packing, namespace-or-global resolution with
      the recall's scope, body cut in SQL, blank summary line dropped.
- [x] Integrator: `Memex.recall_task` calls `with_linked_pages`; the interim
      `memex=None` parameter on `assemble_task_recall` is gone.
- [x] Integrator: shared docs from the returned snippets.
