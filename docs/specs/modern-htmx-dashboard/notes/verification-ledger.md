# Modern HTMX dashboard verification ledger

This ledger records manual checks against the real local `memex viz` process.

| Date | Check | Result |
| --- | --- | --- |
| 2026-09-19 | Isolated live `memex viz` startup and local shell/style delivery | Pass — localhost shell and CSS responded on port 7197 |
| 2026-09-19 | `pyproject.toml` dependency diff and served HTML/CSS inspection for local-only assets | Pass — no dependency change; dashboard serves `/style.css` and vendored `/htmx.js` |
| 2026-09-19 | 320px responsive shell, 200%-zoom-equivalent reflow, keyboard detail close, and visible text status | Pass for the explorer slice; [dashboard explorer verification](../../dashboard-memory-explorer/notes/verification-ledger.md) records the isolated browser observations. |
