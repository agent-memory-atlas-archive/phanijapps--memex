# Plan: Modern HTMX dashboard

- **Spec:** [`spec.md`](spec.md)
- **Status:** Approved
- **Repository anchors:** `src/memex/infrastructure/viz.py`,
  `tests/unit/test_viz_routes.py`, `README.md`, and
  `docs/product/briefs/modern-htmx-dashboard.md`.

## Approach

Extract the existing renderer into a small visualization package while keeping
`viz.py` as the public CLI/import seam. Establish a reusable soft-dashboard
shell and HTML component vocabulary first, then route read-only fragments
through a store-query layer that understands the project namespace. Finish with
the documentation and a live browser smoke check against an isolated store.

## Constraints

- Markdown remains the source of truth and dashboard requests never mutate it.
- Keep stdlib HTTP serving and the existing vendored HTMX; CSS is served locally.
- Preserve the existing route surface and escaping/path-validation controls.

## Construction tests

**Integration tests:** a seeded live server covers shell, direct routes, HTMX
fragments, project/global result selection, empty states, detail routes,
traversal rejection, project-label privacy, and no store mutation from GET
requests.

**Manual verification:** run `memex viz` with an isolated data directory and
verify the 320px, keyboard, and 200%-zoom interactions in a browser.

## Durable-output map

| Durable output | Tasks | Implementation evidence | Closeout evidence |
| --- | --- | --- | --- |
| User dashboard contract | T4 | Guide examples | Strict docs build |
| Architecture | T1 | Module ownership documented | Strict docs build |
| Repository entry point | T4 | README commands | README review |

## Design (LLD)

### Component / module decomposition

`viz.py` owns the public server entry point. The visualization package owns the
HTTP handler/router, page shell, reusable cards/badges/panels, page fragments,
read-only query adaptation, and CSS. Fragments return server-rendered HTML and
compose the same reusable components as full-page views.

Traces to: AC-0001, AC-0002, AC-0004, AC-0005.

### State & control flow

The shell serves direct links. With HTMX, navigation and filter/search controls
swap the main region while preserving a route URL. Scope is explicit in query
parameters; global covers all namespaces and project selects one opaque ID.
Details load into a focus-managed panel, whose close control restores the shell
without mutating store state.

Traces to: AC-0001, AC-0003, AC-0004.

### Behavior & rules

Store queries use existing `Memex`/index services. Every page-derived value is
escaped before interpolation. Session identifiers use the established transcript
validation rule. Empty, unavailable, and malformed data receive a bounded
message rather than a stack trace or source path.

Traces to: AC-0002, AC-0003, AC-0006.

### Quality attributes (NFRs)

The visual system uses a light surface palette, visible text labels/icons beside
status colors, a single responsive breakpoint strategy, focus styles, and CSS
that keeps the primary controls present at the required viewport and zoom.

Traces to: AC-0008.

## Tasks

### T1: Preserve the public dashboard seam while extracting render ownership

**Depends on:** none

**Tests:**
- **Mode:** TDD — `tests/unit/test_viz_routes.py` exercises the public entry
  point and direct routes through a live localhost server.
- Extend route/import tests to prove `memex.infrastructure.viz.serve` still
  starts the same localhost server and existing direct routes remain read-only.
  Covers AC-0005.

**Approach:**
- Move routing, HTML composition, and locally served assets into explicit
  visualization modules with no new runtime dependency.
- Keep `viz.py` as a thin compatible facade.

**Done when:** dashboard route tests pass through the original import surface.

### T2: Deliver the useful responsive dashboard shell and overview

**Depends on:** T1

**Tests:**
- **Mode:** TDD plus visual/manual QA — `tests/unit/test_viz_routes.py` covers
  total pages, project count, index health, pending pages, sessions, type
  distribution, recent memory, and all empty/degraded states; the live browser
  checklist records the responsive hierarchy in
  `docs/specs/modern-htmx-dashboard/notes/verification-ledger.md`.
- Add seeded-server assertions for orientation metrics, project count, type
  distribution, recent-memory cards, and each empty/degraded state. Covers
  AC-0001 and AC-0002.
- Add a visual/manual checklist for responsive shell and visible status labels.

**Approach:**
- Build the soft dashboard shell from reusable navigation, metric, card, and
  panel components.
- Add read-only queries necessary for project and overview information.

**Done when:** overview route tests prove all oriented states and the manual
check records the required responsive hierarchy.

### T3: Make scoped exploration and details composable HTMX flows

**Depends on:** T1, T2

**Tests:**
- **Mode:** TDD — `tests/unit/test_viz_routes.py` exercises scoped selection,
  escaped details, and traversal refusal through the live server.
- **Mode:** Goal-based — `docs/specs/modern-htmx-dashboard/notes/verification-ledger.md`
  records the `pyproject.toml` dependency diff and a served-HTML/CSS inspection
  proving that dashboard assets are local and no remote URL is introduced.
- Add route tests for global/project page and search selection, visible project
  labels, direct detail URLs, escaped output, and path-like session refusal.
  Covers AC-0003, AC-0004, and AC-0006.
- Assert fragment controls use standard HTMX targets and history-friendly URLs.

**Approach:**
- Add explicit scope controls and query adaptation to reusable fragments.
- Compose page/session detail panels from the shared shell while keeping direct
  route responses usable without HTMX.

**Done when:** seeded route tests prove scoped browsing and safe details.

### T4: Publish the dashboard and memory-layout contract

**Depends on:** T2, T3

**Tests:**
- **Mode:** Goal-based plus visual/manual QA — strict documentation build and
  the recorded isolated `memex viz` browser smoke in
  `docs/specs/modern-htmx-dashboard/notes/verification-ledger.md` are the
  verification artifacts.
- Run README link/reference checks available in the repository and strict docs
  build. Covers AC-0007.
- Launch the built dashboard against an isolated store and record the manual
  320px, keyboard, and 200%-zoom smoke result. Covers AC-0008.

**Approach:**
- Update README, guide, and architecture ownership text to match the shipped
  dashboard and scoped-memory behavior.

**Done when:** documentation gates pass and the recorded live smoke is clean.

## Rollout

The dashboard ships as a compatible replacement for the existing local command.
No data migration, deployment change, remote service, or feature flag applies;
rollback is restoring the prior visualization modules from version control.

## Risks

- Module extraction can change fragment IDs or route responses; preserve them
  with server-level regression tests.
- Scoped results can reveal labels incorrectly; only display labels already
  stored in safe project metadata.

## Changelog

- 2026-09-19: Initial modular dashboard plan from the Ready delivery brief.
