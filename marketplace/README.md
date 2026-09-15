# memex marketplace — harness adapters

Memex integrates with coding agents through a three-layer model. MCP
tools (pull) and skills alone are not enough: recall must be **pushed**
deterministically (hooks), and memory practice must be **verifiable**
(CI checks). Every adapter below binds to the same CLI contract —
`memex hook session-start | prompt | transcript` — and the same shared
operation registry (`memex.domain.operations`).

```
L3  DETERMINISTIC   memex verify (CI / pre-commit)   enforced, no LLM
L2  PUSH            memex hook <event>               guaranteed, model-blind
L1  PULL            memex serve-mcp                  model-invoked tools
L0  TRUTH           ~/.memex/wiki + mem.db           rebuildable index
```

## Adapter catalog

| Adapter | Status | Push (hooks) | Pull (MCP) | Transcript capture |
|---|---|---|---|---|
| [`pi/`](pi/) | **ready** | TS extension: per-turn recall injection via `before_agent_start` | stdio server | `session_shutdown` → session JSONL |
| [`claude/`](claude/) | **ready** | `settings.json` hooks: SessionStart / UserPromptSubmit stdout → context | `claude mcp add` | SessionEnd hook → transcript_path via stdin JSON |
| [`codex/`](codex/) | **ready** | AGENTS.md contract (no native injection point) | `config.toml [mcp_servers]` | `notify` wrapper → rollout JSONL |
| [`copilot/`](copilot/) | **ready** | none (hosted) — CI carries the load | remote-only `mcp.json` (future HTTP gateway) | none — `memex verify` workflow instead |

## The CLI contract (stability guarantee)

```
memex hook session-start [--query Q] [--top-k N]   # stdout: §5.4 context block or nothing
memex hook prompt [--prompt T | stdin] [--top-k N] # stdout: context block or nothing
memex hook transcript --harness H --path FILE      # ingest + episode + provenance
```

Adapters may rely on: stdout format, exit code 0 on empty results,
idempotent transcript capture, and silence on failure. Anything else is
internal.

## Install

```bash
memex harness install <pi|claude|codex|copilot> --from ./marketplace
```

Idempotent; existing configs are backed up (`*.memex-bak`) before any
merge. The L3 gate runs anywhere: `memex verify [--since ISO]
[--require-recall] [--require-write]` — exit 1 fails CI.
