# memex for GitHub Copilot

The hosted Copilot coding agent runs in an ephemeral environment: no
local stdio MCP, no lifecycle hooks. For Copilot, the **deterministic
layer carries the integration** — instructions plus a CI gate — while
memory ops stay human/maintainer driven.

## What ships

| File | Purpose |
|---|---|
| [`copilot-instructions-snippet.md`](copilot-instructions-snippet.md) | Memory contract appended to `.github/copilot-instructions.md`: surface known memories, flag durable facts for persistence |
| [`memex-verify.yml`](memex-verify.yml) | GitHub Action: `memex verify` on every PR — health (index freshness, broken links) and, when `MEMEX_DATA_DIR` is provisioned, recall/write evidence since PR creation |

## Install

```bash
memex install copilot  # from any directory; add --from only for a modified checkout
```

Copies the instructions snippet into `.github/copilot-instructions.md`
and the workflow into `.github/workflows/memex-verify.yml`.

## MCP (hosted)

Hosted Copilot supports remote MCP servers via
`.github/copilot/mcp.json` plus firewall rules. memex ships stdio-only
today; a remote HTTP MCP gateway is a future adapter. Self-hosted
Copilot (VS Code agent mode) can use stdio directly:

```json
{ "servers": { "memex": { "command": "memex", "args": ["serve-mcp"] } } }
```

## CI evidence notes

The verify job needs access to the shared `MEMEX_DATA_DIR` (self-hosted
runner or an artifact restore step) for `--require-recall/--require-write`
to find activity evidence; without it, health checks still run.
