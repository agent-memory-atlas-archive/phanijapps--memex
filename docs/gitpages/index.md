<p align="center"><img src="assets/logo-wordmark.svg" width="240" alt="memex"/></p>

# Memex

A durable, local-first memory layer for AI coding agents.

The memory store **is** the filesystem: every memory is a human-readable Markdown
page under `~/.memex/docs/`, git-able and editable by hand. SQLite FTS5 is
a disposable BM25 index — delete it and it rebuilds from the pages. No
server, no cloud, no embeddings.

```bash
memex write --type preference --title "Deploy on Fridays" \
    --body "The team deploys to production on Fridays only."
memex recall "deploy"
```

## Why three layers

Agents forget to call tools. Memex does not rely on them remembering:

- **Pull** — eight typed MCP tools (`memex serve-mcp`) for model-initiated
  memory operations, with enums and bounds enforced in the tool schemas.
- **Push** — harness hooks (`memex hook session-start | prompt | transcript`)
  inject relevant memories into context on every turn and capture session
  transcripts automatically. Deterministic, no model cooperation required.
- **Proof** — `memex verify` turns memory practice into a CI gate: health
  checks always, recall/write evidence on demand, exit 1 fails the build.

## One contract, every harness

| Harness | Push | Pull | Capture |
|---|---|---|---|
| pi | extension: per-turn injection | stdio MCP | session JSONL |
| Claude Code | SessionStart / UserPromptSubmit / SessionEnd hooks | stdio MCP | transcript |
| Codex | AGENTS.md contract + notify | stdio MCP | rollout |
| Copilot | CI carries it | remote (future) | verify workflow |

Install any adapter with `memex install <name>` (the marketplace ships inside
the package).

## Provenance by construction

Every captured session becomes an episode node linked to its raw JSONL
transcript. Any memory can be traced back to the conversation that produced
it — `direct` when the node came from a transcript, `inferred` when an
episode references it.

## Next

- [User guide](guide.md) — concepts, every operation, harness integration,
  configuration reference
- [Specification](spec.md) — the build-ready spec: memory model, schemas,
  C4 diagrams
- [Implementation notes](implementation-notes.md) — spec deviations and why
