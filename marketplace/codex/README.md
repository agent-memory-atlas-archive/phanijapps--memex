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
   `~/.codex/` and pins `notify` to line 3 of `~/.codex/config.toml`
   (the TOML root table — appending after table headers would silently
   disable it).

### Capture events

| Event | Behavior |
|---|---|
| `agent-turn-complete` | synchronous capture of the rollout (session-addressed via the payload's `session_id`/`transcript_path`) |
| `PostCompact` | same synchronous capture; the merge logic preserves pre-compaction turns already captured and appends later ones |
| `SessionEnd` | **fast handoff** — Codex allows 1–3s of teardown, so memex is spawned detached and the hook returns immediately; capture completes moments later |

Repeated checkpoints of one session are idempotent: one episode node, no
duplicate turns. Failures are nonblocking for Codex and always leave a
diagnostic JSON line in `~/.memex/logs/codex-capture.log` (event,
session id, category — never transcript text or tool arguments).

### Recovery after a crash

Hooks can miss sessions (crash, kill, timeout). Recover manually:

```bash
memex hook transcript --harness codex --path ~/.codex/sessions/<date>/rollout-*.jsonl
```

The session id and header totals are re-extracted from the rollout, so a
late capture is identical to a live one.
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
