# Plan: memex viz — on-demand HTMX dashboard

- **Spec:** [`spec.md`](spec.md)
- **Status:** Approved
- **Repository anchors:** `src/memex/infrastructure/viz.py` (existing,
  broken HTMX subset); real HTMX 2.0.4 downloaded to `/tmp/htmx.min.js`

## Approach

Replace the broken 2 KB custom HTMX subset with the real 50 KB vendored
library, fix the shell page to use standard HTMX attributes, and add route
unit tests. The real HTMX handles `hx-trigger="load"`, `keyup delay:300ms`,
`every 5s`, and click-based fragment swaps correctly out of the box.

## Tasks

### T1: Vendor real HTMX + fix shell
- **Spec map:** Obj all; AC-0007
- **Mode:** TDD
- **Tests:** `tests/unit/test_viz_routes.py` — shell serves HTMX >10 KB
  containing the `htmx` identifier.
- **Approach:** Embed the real HTMX source as a module constant; serve
  at `/htmx.js`; fix the shell's attribute usage to standard HTMX.
- **Depends on:** none

### T2: Fix all fragment routes
- **Spec map:** Obj 1-6; AC-0001 through AC-0006
- **Mode:** TDD
- **Tests:** route unit tests hitting each endpoint against a seeded
  store, asserting fragment content (stat cards, filtered pages, search
  results, health, sessions, tokens SVG).
- **Approach:** Clean up fragment HTML to use standard `hx-get`,
  `hx-trigger`, `hx-target`, `hx-swap` attributes that real HTMX
  processes; ensure the type-filter links and search input wire to the
  correct targets.
- **Depends on:** T1

## Changelog

- 2026-09-16: drafted after live dashboard rendered empty — root cause:
  custom HTMX subset missing `load` trigger and click param handling.
