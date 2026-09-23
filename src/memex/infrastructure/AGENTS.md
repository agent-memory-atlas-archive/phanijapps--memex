# Infrastructure guidance

Applies to `src/memex/infrastructure/`. Inherits the root `AGENTS.md`. Scope-specific deltas only.

- All I/O lives here: filesystem, SQLite, harness hooks, LLM clients, viz.
  Twenty-plus modules already cover these — read the docstrings and extend the
  owning module rather than adding a parallel one.
- Markdown under `~/.memex/docs/` is the source of truth; the SQLite index is
  disposable and must stay rebuildable from those files.
- This layer writes to the developer's real `~/.memex`. Exercise it only with an
  isolated `MEMEX_DATA_DIR=/tmp/...`.
- Never log memory contents, credentials, or tool inputs.
