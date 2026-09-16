# memex viz — Dashboard Design Brief

**Source:** research subagent (Hindsight docs + Letta staging + training knowledge)
**Purpose:** adversarial review cycle — 5 rounds to convergence
**Status:** round 0 baseline

---

## The 10 Rules

| # | Rule | Bad | Good |
|---|------|-----|------|
| 1 | **Five-second test** — top strip answers "is everything okay, and if not, where?" | 12 equal cards, user computes health themselves | `● healthy · 142 pages · 0 pending · index fresh` |
| 2 | **Numbers need states** — bare counts force memorizing healthy ranges | `Stale rows: 3` | `Index: stale (3 rows) → run memex verify` |
| 3 | **Dashboards monitor, reports detail** — one screen, glanced at | 20 memory cards + sessions + tokens stacked on one page | Overview = status + 4 KPIs; "Memories" is its own view |
| 4 | **Context (deltas/sparks)** — numbers without comparison are decoration. Only where history data exists (tokens per session from meta.json). Page-count/pending/archived have no time series — show snapshot only, not fake sparks | `12,431 tokens` | `12,431 tokens ↑23% this week ▁▂▄▇` (token KPI only) |
| 5 | **Color = state + category only** | Every card title in teal | Neutral ink for 90%; teal/amber/red only for OK/warn/error + active filter |
| 6 | **One visual language** | Inline `style=` fragments everywhere | Every stat/badge/axis from one class/token set |
| 7 | **Click-through to evidence** | `<a href="#">` on search-hit titles and type-filter links; page-card titles have no anchor at all | Title → `/page/<id>` → provenance link to transcript |
| 8 | **Design empty/loading/error states (including 404: plain-text "not found" injected by HTMX swap has no styling or recovery)** | `except: return "No results"` (broken index looks like empty store) | "Search failed: index locked (run memex verify)" vs "No memories match 'x'" |
| 9 | **Tabular/mono data typography** | Proportional digits jittering on refresh | `font-variant-numeric: tabular-nums` or mono stack for IDs/dates/counts |
| 10 | **Never move things under the user; note: /health calls scan_all()+hash_body per node every 5s — consider caching or interval backoff for large stores** | Full-page re-render every 5s | Poll only the 3-line health strip (viz.py already correct) |

## Current State Audit

### P0 — Correctness (fix before anything else)

**Test obligation:** every P0 fix ships with a regression test — XSS probe (`<svg/onload=…>` in tags → assert escaped), malformed meta.json (string tokens → assert /tokens survives), chart at 76 sessions (assert no clipping). No fix lands unverified.

| Issue | Severity | Detail |
|---|---|---|
| XSS gap | 🔴 | Tags, session IDs, dates interpolated unescaped — a hostile tag like `<svg/onload=alert(1)>` in a memory page executes in the dashboard (tag normalization replaces spaces but preserves slashes and angle brackets) |
| Chart overflow | 🔴 | `bar_w = max(600//len, 8)` — 76+ sessions silently exceed the 600px viewBox (76×8=608; newest bar starts outside viewBox, hidden) |
| Zero-token lie | 🟡 | `max(int(h), 2)` renders zero-token sessions as 2px bars |
| Malformed meta.json kills /tokens | 🟡 | A string `total_tokens` value raises unhandled TypeError; one bad file permanently breaks the token panel |
| Error-as-empty | 🟡 | Search exceptions render "No results" — indistinguishable from empty store |
| Teal decoration | 🟡 | `h2` and `.stat` use `color:var(--teal)` — color for decoration, violating Rule 5 |
| Shell hygiene | 🟡 | Missing `<meta charset>`, `<meta viewport>`, `lang="en"`; h1 says "memex" (title tag already correct) |

### P1 — Structure (the big win)

| Change | Rationale |
|---|---|
| Nav + swapped pane (Overview / Memories / Sessions / Tokens / Search) | Rule 3: dashboard ≠ report; one screen per view |
| Merge stats grid + health card → single status bar | Current duplication: same 4 numbers appear twice |
| Search in header as primary action | Search IS the app for a memory tool |
| Memory titles → `/page/<id>` real links | Rule 7: click-through to evidence |
| `hx-push-url` on nav + filters | Real URLs, back-button works |
| Dark mode via `prefers-color-scheme` | Both staged references default dark |

### P2 — Polish

| Change |
|---|
| Sparklines for token KPI only (data exists in meta.json); page/pending/archived remain snapshot values |
| Mono/tabular numerals for IDs, dates, counts |
| Relative time ("2h ago") for session timestamps |
| `hx-indicator` spinner on search/filter |
| `aria-current` on active type filter; derive filter list from data |
| Microcopy tooltip for "zero-yield streak" |
| Y-axis + gridlines + date labels on token chart |
| Bucket token chart by day beyond ~40 sessions |
| Fallback `.badge` style for unknown statuses |

## HTMX Patterns

**Use:** fragment routes + `hx-push-url`; scoped polling (already correct); debounced search with `changed`; filters as real links with query params. HTMX is **full 2.0.4 (~55 KB)** — hx-push-url, hx-indicator, hx-trigger changed/delay/every all present and verified.

**Avoid:** shell → overview → fragments waterfall (render server-side in one request); dead `href="#"` links; HTMX for hover/mousemove (CSS/SVG handles those).

**Progressive enhancement floor:** with JS off, `curl localhost:7171/pages?type=entity` returns the same fragment a browser swaps in.

## Anti-Patterns to Eliminate

1. Wall of numbers (6 equal sections, stats/health duplication)
2. Dashboard/report conflation (browsing 20 cards on the monitoring page)
3. Dead UI (`href="#"` everywhere, no active filter state)
4. Lying pixels (2px bars for zero, chart overflowing viewBox)
5. Unexplained jargon ("zero-yield streak" as top-level KPI)
6. Error-as-empty (search exceptions → "No results")
7. Color-only state (health by border-left color alone)
