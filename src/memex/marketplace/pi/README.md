# memex for pi

Deterministic memory layer for the pi coding agent. Recall is **pushed**
into context on every turn (not left to model cooperation), and the pi
session file is captured as a memex transcript with full provenance on
shutdown.

## What it does

- **First turn** — injects repo-level memories (branch, last commit as
  query hints) via `memex hook session-start`, plus a scoped-write rule even
  when recall has no matches.
- **Every later turn** — injects memories relevant to your prompt via
  `memex hook prompt`.
- **Session shutdown / switch** — ingests `~/.pi/agent/sessions/...jsonl`
  via `memex hook transcript --harness pi`, creating the episode node and
  linking the raw transcript for provenance.

## Install

Requires the `memex` CLI on PATH (`uv tool install memex` or from this
repository: `uv sync --all-groups`).

```bash
# from this repository
pi install ./marketplace/pi
```

Or copy `extensions/memex.ts` to `~/.pi/agent/extensions/` manually.

## Configuration (environment)

| Variable | Default | Purpose |
|---|---|---|
| `MEMEX_BIN` | `memex` | CLI binary to invoke |
| `MEMEX_TOP_K` | `5` | Injection width (hits per turn) |
| `MEMEX_DISABLE` | unset | Set to `1` to disable the extension without uninstalling |
| `MEMEX_DATA_DIR` | `~/.memex` | Shared with all memex adapters |

## Behavior notes

- Failures are silent by design: a missing or slow memex never blocks
  or pollutes a pi session.
- Transcript capture is idempotent (session ids derive from the session
  file name; re-capture on session switch overwrites, never duplicates).
- The MCP server (`memex serve-mcp`) composes with this extension:
  hooks push context in; MCP tools let the model write/consolidate.

## Auto-consolidation

- `MEMEX_AUTO_CONSOLIDATE=1` — distill the captured session via the
  `--consolidate` hook path (see the guide's [consolidation] config).
