# Spec: memex viz — on-demand HTMX dashboard

- **Status:** Approved
- **Owner:** phanijapps
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`docs/product/intents/memex-viz.md`](../../product/intents/memex-viz.md) (accepted)
- **Brief:** none
- **Discovery:** none
- **Contract:** none
- **Shape:** service (HTTP handler + data reading + HTML fragments)

## Objective

`memex viz` starts an on-demand localhost web server that renders the memory
store as an interactive dashboard with working navigation, search, and
charts. Every interactive element on the page performs its labeled action:

1. **Memory browser** — type-filter links (entity, preference, procedure,
   summary, episode) load the filtered page grid when clicked.
2. **Search** — typing in the search box debounces 300ms and renders BM25
   results with highlighted snippets below the input.
3. **Health panel** — auto-refreshes every 5 seconds without page reload.
4. **Sessions table** — renders session list with turn counts and timestamps.
5. **Token chart** — server-rendered SVG bar chart of token consumption
   per session, with tooltips.
6. **Stats cards** — page count, pending, archived, zero-yield streak
   visible on load.

## Boundaries

### Always do
- Use the **real vendored HTMX** (~50 KB minified) — not a custom subset.
- Zero new pip dependencies: stdlib `http.server` + vendored JS.
- Read-only: no writes to `~/.memex/` from the dashboard.
- Bind `localhost` only.

### Ask first
- Adding any pip dependency.
- Adding write operations (approve/forget from the UI).

### Never do
- No React, no npm, no build step.
- No daemon — server lifecycle is the process lifecycle.
- No network calls from the server (all data is local).

## Testing Strategy

- **Server routes (all ACs)** — TDD: unit tests hitting each route via
  `http.client` against a seeded store, asserting HTML fragment content.
- **HTMX wiring** — goal-based: the shell page references `/htmx.js` and
  every fragment uses standard HTMX attributes (`hx-get`, `hx-trigger`,
  `hx-target`, `hx-swap`) that the real library handles.

## Acceptance Criteria

- [ ] **AC-0001.** `curl localhost:PORT/` returns a shell page that loads
      `/htmx.js` and `/style.css`, and the overview fragment renders stat
      cards with the correct page count from the seeded store. (Test:
      route unit)
- [ ] **AC-0002.** `curl localhost:PORT/pages?type=entity` returns only
      entity-type page cards; `?type=preference` returns only preference
      cards. (Test: route unit)
- [ ] **AC-0003.** `curl localhost:PORT/search?q=<term>` returns BM25
      results with the matching page title in the fragment. (Test: route
      unit)
- [ ] **AC-0004.** `curl localhost:PORT/health` returns a fragment with
      index stale count, pending count, and zero-yield streak. (Test:
      route unit)
- [ ] **AC-0005.** `curl localhost:PORT/sessions` returns a table with at
      least one session row when a transcript exists. (Test: route unit)
- [ ] **AC-0006.** `curl localhost:PORT/tokens` returns an SVG with at
      least one `<rect>` bar when a session has token usage. (Test: route
      unit)
- [ ] **AC-0007.** The shell page's `<script src="htmx.js">` serves the
      real HTMX library (size > 10 KB, contains `htmx` identifier).
      (Test: route unit)

## Assumptions

- Technical: real HTMX 2.x vendored from unpkg (verified 50,917 bytes).
- Technical: stdlib http.server with ThreadingHTTPServer.
- Product: user-confirmed design calls — vendored CSS, 5s health refresh,
  SVG charts, auto-open browser (intent accepted 2026-09-16).

## Follow-ons

- Write operations from the UI (approve pending, forget) — separate intent.
