# Plan: Dashboard memory explorer

- **Spec:** [`spec.md`](spec.md)
- **Status:** Done
- **Repository anchors:** `src/memex/infrastructure/viz.py`,
  `src/memex/infrastructure/transcript_hook.py`, and
  `tests/unit/test_viz_routes.py`.

## Approach

Keep `VizHandler` as the compatible localhost HTTP seam. Put navigation and
shared presentation in `viz_components.py`, selection/pagination in
`viz_explorer.py`, grouping/replay in `viz_sessions.py`, and the visual system
in `dashboard.css`. Full `/view/` responses render the same fragments that
HTMX swaps, so ordinary links remain functional without JavaScript.

## Construction tests

The isolated live-server fixture in `tests/unit/test_viz_routes.py` exercises
selection boundaries, project and global scope, direct/fragment parity,
search, session grouping, replay, escaping, path validation, and read-only
requests. A browser walkthrough checks desktop, 320px, 200% zoom, keyboard
focus, and the reference palette. The full Python, lint, type, and docs gates
close the slice.

## Tasks

### T1: Extract shell and local visual system

**Depends on:** none. **Tests:** served CSS, shell, and direct-view route tests.
**Approach:** use adjacent local CSS and shared components; preserve vendored
HTMX and the existing server. **Done when:** direct URLs render content with
or without JavaScript and package artifacts include the CSS. **Durable:**
architecture ownership in `docs/architecture/overview.md`.

### T2: Add bounded memory exploration

**Depends on:** T1. **Tests:** 20-card boundaries, ordering, filters, pager
links, search scopes, malformed inputs, and read-only GET snapshot.
**Approach:** filter before stable sorting and pagination; carry every selected
type and scope through both direct and HTMX URLs. **Done when:** AC-0001 through
AC-0005 and AC-0012 pass. **Durable:** user guide.

### T3: Group sessions and render replay

**Depends on:** T1. **Tests:** date/project/harness grouping; roles, order,
timestamps, truncation, escaping, invalid IDs and malformed lines.
**Approach:** use existing transcript metadata and safe Markdown renderer.
**Done when:** AC-0006 through AC-0009 pass. **Durable:** user guide.

### T4: Align and verify the finished dashboard

**Depends on:** T1–T3. **Tests:** browser visual and accessibility walkthrough,
package build, full repository gates, and reviewer findings.
**Approach:** tune responsive CSS against the supplied reference, document
behavior, and keep the read-only/local-only boundary. **Done when:** AC-0010
through AC-0012 pass and the verification ledger records evidence.
**Durable:** README, guide, architecture note, verification ledger.

## Security review depth

Light, boundary-focused review covers escaped untrusted content, namespace and
transcript-path confinement, local-only assets, and read-only GET behavior.
