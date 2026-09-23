# Spec: Link-graph expansion in recall packing

- **Status:** Implementing
- **Owner:** Memex maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** none
- **Brief:** none
- **Discovery:** none
- **Contract:** none — keyword parameters on existing application callables
- **Shape:** service

> **Spec contract:** Boundaries, Testing Strategy, and Acceptance Criteria are
> completion gates. The plan describes construction.

## Objective

Recall finds pages by query; the typed link graph (`wiki_links`, validated by
`memex verify`) says which pages belong together. Until now no retrieval path
walked that graph: hook injection printed link slugs as text and task recall
ignored them. This slice adds OKF's third primitive, `read_concept(depth)`, as
link-graph expansion: after the direct hits are packed exactly as before,
pages reachable within `depth` hops fill only the budget the hits leave, in a
deterministic breadth-first order, each as a short block (title, path,
description or snippet), with a trailing marker counting anything cut.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| User-facing promise | Session-start block and task recall gain a linked-pages section | `docs/gitpages/guide.md` | Memex maintainers | Worked block showing a `+ ... depth: 1 | via:` entry and the omitted marker | Guide matches an isolated live invocation |
| Current architecture | New application module reads the link graph | `docs/architecture/overview.md` | Memex maintainers | `graph_expansion.py` named beside injection and task recall | Map matches shipped behavior |
| Evaluation evidence | Benchmark rows re-pinned | `docs/research/2026-09-20-task-evidence-baseline.md` | Implementing contributor | 2026-09-23 amendment table | `_report_strategy_metrics == _benchmark_strategy_metrics` |
| Release history | User-visible block change | `docs/product/changelog.md` | Memex maintainers | Unreleased entry | Entry names the section and its budget rule |

## Boundaries

### Always do

- Pack direct hits first, exactly as before; expansions only use the remaining
  budget under the same 4,096-token bound.
- Visit level by level, alphabetical slug within a level, each page once,
  seeds excluded; same input gives the same bytes.
- Resolve a `[[slug]]` the two places `memex verify` accepts (the source
  page's own namespace, or a global page) and filter with the recall's own
  scope, project, and visibility clauses from `BM25Retriever`, so no page the
  caller could not recall is ever expanded and no project link ever reaches
  another project.
- Render title, file path, and description or a short snippet; never the body.
- Keep depth a keyword parameter (default 1); no configuration key.

### Ask first

- Change the injection block or task-recall context shape beyond appending
  the linked section.
- Add a public accessor on `BM25Retriever` for its visibility clauses (shared
  file; the cleaner home for the rule reuse).

### Never do

- Never traverse into another project or a hidden page.
- Never log or return page bodies, credentials, home paths, or usernames.
- Never add a dependency or a config key for this slice.

## Testing Strategy

- **Traversal (AC-0001, AC-0002, AC-0003): TDD unit tests** in
  `tests/unit/test_link_expansion.py` against a real isolated `Memex` store:
  level order and alphabetical tie-break, route and depth per entry, cycle
  safety, seed exclusion, determinism across two runs.
- **Budget (AC-0004): TDD unit tests** for the cut point, the omitted marker
  text, and the rendered size staying within the budget handed in.
- **Visibility (AC-0005, AC-0010): TDD unit tests** with archived,
  soft-forgotten, pending, other-project, and same-slug-other-project
  neighbours under both recall scopes; a project seed linking a global page
  under both scopes; a global seed on the session-start path.
- **Wiring (AC-0006, AC-0007): TDD unit tests** for `build_injection` and
  `with_linked_pages`: direct hits unchanged, linked section after them,
  marker when nothing fits, total within budget.
- **Benchmark (AC-0008): goal-based integration**
  `tests/integration/test_agent_workflow_eval.py` re-run before and after.

## Acceptance Criteria

- [x] **AC-0001.** `expand_links` returns neighbours level by level, alphabetical
      slug within a level, each page once, seeds excluded, with `depth` and a
      `(rel, slug)` route from the seed on every entry.
- [x] **AC-0002.** A cycle terminates and yields each page once at any depth.
- [x] **AC-0003.** Two runs over the same store return equal expansions.
- [x] **AC-0004.** When every entry fits the budget all are kept with no
      marker; otherwise entries stop at the first that does not fit once the
      marker is reserved, and the rendered lines plus
      `[memex] linked pages omitted (token budget): N` fit the budget handed
      in; `N` counts every reachable page not shown.
- [x] **AC-0005.** Archived, soft-forgotten, pending, and other-project
      neighbours are never expanded, including a same-slug page in another
      project.
- [x] **AC-0006.** `build_injection(depth=1)` starts with the byte-identical
      `depth=0` block minus its footer, then the linked section, then the
      footer; when links do not fit, every direct hit stays and the marker
      appears; the block stays within the budget.
- [x] **AC-0007.** `with_linked_pages(memex, request, result, selected)` keeps
      the sources and context prefix of `assemble_task_recall`; linked lines
      and the marker follow within `max_tokens`.
- [x] **AC-0008.** The committed benchmark is re-pinned to measured values and
      the baseline report table equals the benchmark output.
- [x] **AC-0009.** `Memex.recall_task` appends the linked section through
      `with_linked_pages`, so MCP and CLI task recall carry it;
      `assemble_task_recall` stays a pure packing function with no facade
      parameter.
- [x] **AC-0010.** A project page's link to a global page is expanded under
      global recall (session start) and not under project recall (task
      recall); a global page's link never resolves into a project; an
      other-project page is never expanded under either scope.
- [x] **AC-0011.** A neighbour with no description and a blank body renders
      as a two-line block; the body is read only up to the snippet margin.

## Benchmark: before → after

Measured with `uv run pytest tests/integration/test_agent_workflow_eval.py`
and a direct `run_benchmark()` run in the same tree. Tuple order:
(complete tasks, fact recall, calls, rendered tokens, inactive hits,
other-project hits).

| Strategy | Pinned on `main` | Measured before change | Measured after change (pinned) |
| --- | --- | --- | --- |
| current_injection | (5, 0.515625, 24, 15002, 0, 0) | (5, 0.515625, 24, 16322, 0, 0) | (5, 0.515625, 24, 16322, 0, 0) |
| broad_query | (17, 0.875, 24, 72180, 0, 0) | (17, 0.875, 24, 81684, 0, 0) | (17, 0.875, 24, 81684, 0, 0) |
| human_focused | (22, 0.96875, 72, 52593, 0, 0) | (22, 0.96875, 72, 59457, 0, 0) | (22, 0.96875, 72, 59457, 0, 0) |
| linked_summary | (11, 0.703125, 24, 4485, 0, 0) | (11, 0.703125, 24, 4749, 0, 0) | (11, 0.703125, 24, 4749, 0, 0) |

The test was already red on `main` (all four rendered-token counts had
drifted before this slice). Coverage of facts, complete tasks, and rendered
tokens did not move. Expansion adds no pages and no tokens on this fixture:
only two of its 123 cards carry `[[...]]` references, and all four point at
slugs no card has, so nothing resolves. An expansion-off (`depth=0`) versus
expansion-on run in one tree returned identical tuples for every strategy.
The review-time reading of 16,243 / 81,147 / 62,565 / 4,773 tokens (with
human_focused at 21/24) came from a retriever edit that was in the tree at
that moment and is no longer present; the pinned values are those the tree
measures at 2026-09-23 17:20 EDT.

## Assumptions

- A `[[slug]]` names a page in the source page's own scope and project or a
  global page, matching what `memex verify` accepts; when both exist, both
  are reachable and sort by slug then scope. It never names a page in another
  project.
- `BM25Retriever.neighbours` owns the neighbour query and applies recall's
  own visibility rule (with the recall's scope and project), so expansion
  reuses that rule without restating it and the application layer runs no
  SQL.
- The expansion section is dropped entirely when even its marker would push
  the rendered text over the budget; the direct hits are never trimmed to
  make room for it.
- The benchmark fixture has no resolvable links, so it cannot show the gain
  this mechanism is built for; a fixture with linked cards is future work.
