# Spec: Modern HTMX dashboard

- **Status:** Approved
- **Owner:** Memex maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** ADR-0001
- **Brief:** `docs/product/briefs/modern-htmx-dashboard.md`
- **Discovery:** `docs/product/intents/memex-viz.md`
- **Contract:** none — localhost read-only UI
- **Shape:** ui

## Objective

`memex viz` is a useful, local-first dashboard for developers who need to
orient in their memory store, inspect its health, search globally or within a
project, and open the supporting page or session without relying on CLI output.
It presents that workflow as a responsive application dashboard and remains a
read-only projection of the filesystem-backed store.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| User dashboard contract | Required | `docs/gitpages/guide.md` | maintainers | Updated launch and interaction guide | Docs build passes |
| Architecture | Required | `docs/architecture/overview.md` | maintainers | Visualization module ownership | Docs build passes |
| Repository entry point | Required | `README.md` | maintainers | Dashboard and scoped-memory quickstart | README review and tests pass |

## Boundaries

### Always do

- Keep the server localhost-only, read-only, zero-dependency, and usable by
  direct URLs when HTMX is unavailable.
- Use the existing locally served HTMX and locally served CSS only. Escape all
  memory and transcript-derived output at the rendering boundary.
- Preserve existing route behavior while adding project-aware browsing and
  modularize the dashboard by routing, layout, reusable components, fragments,
  style assets, and store queries.

### Ask first

- Add a Python or browser dependency, a build step, a remote asset, telemetry,
  or any dashboard write action.
- Change the dashboard's localhost binding or expose it over a network.

### Never do

- Adopt the referenced Django project, Tailwind, its assets, markup, or brand.
- Persist dashboard state, emit raw memory contents to logs, or expose
  path-like session identifiers through a route.
- Make project/global scope invisible in a result that carries project context.

## Testing Strategy

Route and component behavior use TDD through a seeded live
`ThreadingHTTPServer`. Goal-based checks prove the documented `viz` entry point
still starts the route surface, the package manifest has no added runtime
dependency, and dashboard GET requests leave an isolated `MEMEX_DATA_DIR`
unchanged. Route tests falsify traversal, raw project identity leakage, and
project/global selection. The responsive visual hierarchy, keyboard path, and
200%-zoom behavior use recorded visual/manual QA against the real `memex viz`
process.

## Acceptance Criteria

- [ ] AC-0001: The dashboard shell provides a persistent navigation rail,
  compact top bar, and responsive content area that presents overview, pages,
  sessions, tokens, and health views through direct URLs and HTMX swaps.
- [ ] AC-0002: The overview presents total memory pages from the page store,
  project namespace count from project page metadata, index health from index
  freshness, pending-page count, recent sessions from transcript metadata,
  memory-type distribution as page counts, and recent memory ordered by page
  update time; each unavailable source renders a specific degraded state and
  each empty source renders a specific empty state.
- [ ] AC-0003: Pages and search let a user select global results or one project
  namespace; selected scope is visible in the response and project-origin hits
  identify their display label without exposing a raw path or remote.
- [ ] AC-0004: Selecting a page or session opens an escaped, keyboard-closable
  detail panel while its direct page or session URL remains independently
  usable.
- [ ] AC-0005: The documented `memex.infrastructure.viz` entry point and all
  existing direct dashboard routes retain their read-only behavior while the
  redesigned shell and fragment routes provide the named dashboard states.
- [ ] AC-0006: The dashboard remains a localhost-only read-only projection,
  uses no remote asset or new runtime dependency, and rejects path-like session
  routes without reading outside the transcript namespace.
- [ ] AC-0007: The README and user guide show how to launch the dashboard,
  describe global/project memory layout and scoped recall, describe dated
  transcripts and confirmed clearing, and list the current MCP tool surface.
- [ ] AC-0008: At 320px width and at 200% zoom, primary navigation, search,
  scope controls, and the detail-panel close control remain visible and keyboard
  reachable; status does not rely on color alone.

## Follow-ons

- Maintainers: `docs/product/intents/memex-viz.md` — dashboard write actions
  require a separate accepted intent and security review.

## Assumptions

- Technical: current `viz.py` is an 813-line stdlib HTTP handler with route
  tests (source: `src/memex/infrastructure/viz.py`,
  `tests/unit/test_viz_routes.py`, reviewed 2026-09-19).
- Product: the supplied dashboard image defines bounded visual cues, while the
  App Generator Django HTMX project supplies interaction inspiration only
  (source: user request and reviewed repository, 2026-09-19).
- Process: this is the single slice confirmed by the Ready dashboard brief
  (source: user request, 2026-09-19).
