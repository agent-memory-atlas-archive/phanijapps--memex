# memex for Codex

Codex has no native context-injection hooks, so this adapter combines
what exists: an AGENTS.md memory contract (push-by-instruction), MCP
tools for model-initiated memory ops, and a `notify` wrapper that
captures every rollout transcript deterministically.

## Install

```bash
memex harness install codex --from /path/to/memex/marketplace
```

What it does:
1. Copies [`memex-codex-notify.py`](memex-codex-notify.py) to
   `~/.codex/` and wires `notify` in `~/.codex/config.toml` — on every
   `agent-turn-complete`, the rollout session file is ingested
   (`memex hook transcript --harness codex`), giving each Codex session
   an episode node with provenance.
2. Appends `config.toml`: `[mcp_servers.memex]` → `memex serve-mcp`.
3. Appends the [memory contract](AGENTS-snippet.md) to the project's
   `AGENTS.md`: recall at task start, write durable facts via `memex write`.

## Codex rollout notes

The rollout JSONL schema varies across Codex versions. The transcript
parser is tolerant (unknown entries are skipped, never fatal) and the
notify wrapper falls back to the newest `~/.codex/sessions/**/rollout-*.jsonl`
when the event carries no path. Verify against your Codex version after
installing: run one session, then `memex list-sessions` (via `memex
ingest-transcript` report or the export tool).

## Manual config

```toml
notify = ["~/.codex/memex-codex-notify.py"]

[mcp_servers.memex]
command = "memex"
args = ["serve-mcp"]
```

## Auto-consolidation

- `MEMEX_AUTO_CONSOLIDATE=1` — after the notify wrapper captures a rollout,
  distill the fresh episode immediately (cheap model via `[consolidation]`).
