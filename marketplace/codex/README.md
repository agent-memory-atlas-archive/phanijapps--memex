# memex for Codex

Codex has no native context-injection hooks, so this adapter combines
what exists: an AGENTS.md memory contract (push-by-instruction), MCP
tools for model-initiated memory ops, and a `notify` wrapper that
captures every rollout transcript deterministically.

## Install

```bash
memex install codex    # from any directory; add --from only for a modified checkout
```

What it does:
1. Copies [`memex-codex-notify.py`](memex-codex-notify.py) to
   `~/.codex/` and pins `notify` to line 3 of `~/.codex/config.toml`
   (the TOML root table — appending after table headers would silently
   disable it).

### Capture events

| Event | Channel | Behavior |
|---|---|---|
| `agent-turn-complete` | `notify` (wired by install, line 3) | synchronous capture of the rollout (session-addressed via the payload's `session_id`/`transcript_path`) |
| `PostCompact` | lifecycle hooks | same synchronous capture; dispatched on `hook_event_name` |
| `SessionEnd` | lifecycle hooks | **fast handoff** — Codex allows 1–3s of teardown, so memex is spawned detached and the hook returns immediately |

**Event delivery, honestly:** Codex 0.154 has a full lifecycle-hooks
system (`PostCompact`, `SessionEnd`, ...) whose stdin JSON carries
`session_id` + `transcript_path`, and this wrapper speaks that schema
(it dispatches on `hook_event_name` and logs every event it receives,
including unrecognized ones, in `~/.memex/logs/codex-capture.log`).
Registering hooks is gated behind Codex's plugin / TUI trust flow —
plain `config.toml` entries are not sufficient. Until you enable the
wrapper as a Codex hook (via `/hooks` in the TUI or a memex Codex
plugin), compaction coverage is already complete without `PostCompact`:
rollout files are append-only, so the next `agent-turn-complete`
capture re-reads pre-compaction turns too, and the merge logic keeps
earlier turns even if Codex starts a fresh rollout. `SessionEnd` adds
the no-further-turn case; the recovery command below covers it in the
meantime.

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
installing: run one session, then check `memex status` for capture activity
or `memex export` for the episode node.

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
