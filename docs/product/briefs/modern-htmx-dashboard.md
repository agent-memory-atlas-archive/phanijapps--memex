# Brief: Modern HTMX dashboard

- **Slug:** `modern-htmx-dashboard`
- **Status:** Ready
- **Received:** 2026-09-18
- **Owner:** Memex maintainers
- **Initiative:** `ini-001`

## Outcome

Memex has a useful, dashboard-first local interface for understanding and
navigating memory at a glance. It makes the primary questions answerable
without leaving the page: what memory exists, which project it belongs to,
whether the index is healthy, what sessions are recent, and where to inspect a
specific result. HTMX supplies the interactions; full-page navigation remains
usable without it.

## Scope

### In scope

- Revamp the existing dashboard's visual design and information hierarchy.
- Replace the monolithic visualization module with composable standard-library
  modules for HTTP routing, shell/layout, reusable visual components, page
  fragments, locally served CSS and HTMX assets, and read-only store queries.
- Use an application-dashboard structure: a persistent navigation rail,
  compact top bar, responsive metric cards, content panels, purposeful empty
  states, and a keyboard-friendly detail panel.
- Make the overview useful for Memex: memory-page and project counts, index
  health, pending pages, recent sessions, memory-type distribution, and an
  action-oriented recent-memory view.
- Support HTMX partial updates for navigation, search, filters, and detail
  inspection. Browser history and direct URLs must continue to work.
- Keep the interface read-only. It may link to CLI documentation but must not
  write, delete, consolidate, or clear memory.
- Update the README with the dashboard purpose, launch command, project memory
  layout, scoped recall, date-partitioned transcripts, and transcript clearing.

### Non-goals

- Do not adopt Django, Tailwind, a CSS framework, a client-side SPA framework,
  or a database/API server. The referenced Django HTMX dashboard is visual and
  interaction inspiration only.
- Do not turn the visualization server into an editing surface or change the
  shared memory contract.
- Do not redesign unrelated CLI, MCP, capture, or consolidation workflows.
- Do not require an internet connection, telemetry, user account, remote asset,
  or image asset for the dashboard to work.

## Constraints and delivery appetite

- Preserve `memex viz` as a localhost-only, zero-dependency standard-library
  server and preserve existing direct routes while introducing fragment routes.
- The HTML/CSS must be responsive from 320px wide, keyboard navigable, and
  usable at 200% zoom. Color alone cannot carry state.
- Reuse the existing locally served vendored HTMX and add only locally served
  dashboard CSS. Do not introduce a build step, remote asset, or new Python
  dependency.
- Treat stored page, transcript, and query content as untrusted: escape it at
  every rendered boundary and never include raw transcript contents in overview
  cards or search snippets beyond existing bounded rendering behavior.
- Deliver the visual system, component split, useful overview, scoped browsing,
  and README together as one maintainable dashboard slice.

## Assumptions and risks

- **Assumption:** Local developers use the dashboard primarily to orient,
  search, inspect provenance, and assess store health rather than to author
  memory. Evidence: current `viz.py` is read-only and exposes these surfaces.
- **Assumption:** The supplied reference establishes a light, layered
  application-dashboard aesthetic—soft surfaces, rounded cards, compact
  navigation rail, compact top bar, responsive metric-card grid, two-column
  content rhythm, and a restrained indigo/fuchsia accent. It does not govern
  brand, text, imagery, iconography, chart data, assets, or commercial design.
- **Assumption:** The App Generator reference confirms HTMX-compatible page and
  fragment interaction patterns only. It does not govern implementation,
  dependencies, markup, routes, or visual assets.
- **Risk:** Splitting an 800-line renderer can accidentally change route or
  fragment contracts. Route-level regression tests and direct browser checks
  must protect existing links and HTMX targets.
- **Risk:** A visually dense dashboard can become decorative rather than useful.
  Each overview panel must answer a concrete memory-management question and
  have a meaningful empty or degraded state.
- **Risk:** Rendering untrusted memory or transcript data in new components can
  create cross-site scripting or path disclosure defects. The existing escaping
  discipline and localhost containment remain mandatory.

## Delivery shape

One independently shippable slice: modular, read-only HTMX dashboard and the
README that explains it. Splitting visual language from the modularization or
from the scoped-memory views would produce a half-updated surface and leave
the single-file maintenance problem unsolved.

## Governance references

- ADR-0001: Markdown filesystem remains the primary store; the visualization
  is a projection only.

## Source provenance

- Direct user request and supplied reference image, 2026-09-19.
- `https://github.com/app-generator/django-htmx-soft-dashboard`, reviewed
  2026-09-19: Django/HTMX dashboard inspiration only; no code or dependency is
  adopted.
- Current `src/memex/infrastructure/viz.py`, reviewed 2026-09-19: 813-line
  read-only stdlib/HTMX visualization server is the modularization target.

## Ready gaps

Ready to review. The user has asked to finalize this brief and create the
dashboard spec. Readiness evidence is the supplied visual reference, the
reviewed HTMX dashboard reference, and the existing route surface.

## Spec map

| Spec |
| --- |
| [`modern-htmx-dashboard`](../../specs/modern-htmx-dashboard/spec.md) |
| [`dashboard-memory-explorer`](../../specs/dashboard-memory-explorer/spec.md) |
