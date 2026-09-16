# Intent: memex viz — on-demand HTMX dashboard

- **Status:** Accepted

## Outcome

`memex viz` starts an on-demand local web server that renders the memory
store's state as an interactive dashboard: memory pages browsable and
searchable, sessions visualized with turn counts and token consumption over
time, and store health (index freshness, pending approvals, zero-yield
streak) visible at a glance. The server stops when the process stops — no
daemon, no background service, no cloud.

## Boundary

- Python stdlib HTTP server (`http.server`) — zero new dependencies.
- HTMX from a vendored single file — no build step, no npm, no React.
- Reads existing surfaces only: `~/.memex/docs/`, `~/.memex/transcripts/*.meta.json`,
  `~/.memex/logs/runs.jsonl`, `~/.memex/mem.db`. No new storage, no writes.
- Binds `localhost` only; no auth surface (single-user, local-first).
- No editing from the UI in this slice — read-only visualization.

## Owner

phanijapps

## Unresolved questions

- Tailwind via CDN or vendored minimal CSS? (Vendored keeps it fully offline.)
- Should the dashboard poll for live updates (HTMX `hx-trigger="every 5s"`)
  or refresh on page load only?
- Chart rendering: pure SVG generated server-side vs. a lightweight chart
  library (Chart.js vendored)?
- Should `memex viz` auto-open the browser tab?

## Projection

Spec via `new-spec` when ready. Natural fit for the existing layered
architecture: `infrastructure/` for the HTTP handler and data reading,
thin `cli.py` subcommand (`viz`), no domain-layer changes.

## Source

Chat input — user request 2026-09-16. Authority transferred by this write.

## Level

feature

## Opportunity

The memory store is invisible to its owner. `memex status` prints JSON,
`memex recall` returns text, and the only way to browse pages is `ls` or
a file editor. A lightweight dashboard makes the store's health, growth,
and session patterns visible without opening SQLite or reading JSONL by
hand — the same local-first, zero-dependency ethos as the rest of memex.
