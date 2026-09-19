# Dashboard memory explorer verification ledger

| Date | Check | Result |
| --- | --- | --- |
| 2026-09-19 | Isolated live dashboard at 1280px and 320px | Pass: five compact KPI cards, persistent 320px navigation, search form including submit button, visible scope/type controls, pager, and memory cards; no clipping observed in screenshots. |
| 2026-09-19 | 200%-zoom-equivalent layout: Chromium DevTools emulated 390 CSS px at 2x pixel scale (780 physical px), forcing the same responsive reflow as 200% browser zoom on a 780px window | Pass: memories and replay had no horizontal overflow; navigation, pagination, session heading, all three role labels, and focused panel close button remained present; close control right edge was 360 CSS px within the 390px viewport. |
| 2026-09-19 | Isolated launcher environment | Pass: `MEMEX_DATA_DIR` dashboard displayed only three temporary pages; regression test covers env selection. |
| 2026-09-19 | Wheel payload | Pass: `uv build --wheel`; wheel includes `dashboard.css`, `viz_components.py`, `viz_explorer.py`, and `viz_sessions.py`. |
| 2026-09-19 | Repository gates | Pass: 611 tests, 1 skipped, 90.24% coverage; Ruff lint and format, mypy, strict MkDocs build, and wheel build. |
| 2026-09-19 | Replay at 1280px and 320px, using only an isolated three-turn fixture | Pass: User, AI assistant, and Tool cards have separate labeled accents, timestamps, readable text, and no 320px clipping. |
| 2026-09-19 | Interactive detail keyboard path in headless Chromium | Pass: opening a memory focused the panel close button; Escape closed the panel and restored focus to the invoking link. |
| 2026-09-19 | Read-only and light security review | Pass: missing-session GET leaves directories unchanged; malformed sidecars are isolated; token values are bounded; adversarial, quality, and light security reviewers all reported clean. |
