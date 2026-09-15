# memex for Claude Code

Push-layer integration: Claude Code hooks guarantee memory recall in
context and capture every session transcript — no model cooperation
required. Composes with the MCP server for model-initiated writes.

## What the hooks do

| Hook | Command | Effect |
|---|---|---|
| `SessionStart` | `memex hook session-start` | stdout is added to context: repo-level memories (branch, last commit as query hints) |
| `UserPromptSubmit` | `memex hook prompt` | reads the hook JSON from stdin, recalls on `prompt`, stdout added to context |
| `SessionEnd` | `memex hook transcript --harness claude` | reads `transcript_path` from the hook JSON, ingests the session → episode node + provenance |

All three are silent on empty results and never block on failure.

## Install

Automatic (merges into `~/.claude/settings.json`, backs up first):

```bash
memex harness install claude --from /path/to/memex/marketplace
```

Manual: merge [`settings-hooks.json`](settings-hooks.json) into
`~/.claude/settings` (user) or `.claude/settings.json` (project).

MCP (model-initiated writes/consolidation):

```bash
claude mcp add memex -- memex serve-mcp
```

## Uninstall

Remove the `memex hook ...` entries from `settings.json`; a pre-install
backup is kept as `settings.json.memex-bak`.

## Auto-consolidation

- `MEMEX_AUTO_CONSOLIDATE=1` — after SessionEnd capture, distill the fresh
  episode immediately (dedicated cheap model via `[consolidation]` in
  `memex.toml`).
