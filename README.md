<div align="center">

<img src="docs/gitpages/assets/logo-wordmark.svg" width="260" alt="memex"/>

**A durable, local-first memory layer for AI coding agents.**

The filesystem is the memory · the index is disposable · every session is provable.

[![CI](https://github.com/phanijapps/memex/actions/workflows/ci.yml/badge.svg)](https://github.com/phanijapps/memex/actions/workflows/ci.yml)
[![Docs](https://github.com/phanijapps/memex/actions/workflows/docs.yml/badge.svg)](https://github.com/phanijapps/memex/actions/workflows/docs.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-0F766E.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-3776AB.svg)](pyproject.toml)
[![Docs site](https://img.shields.io/website?url=https%3A%2F%2Fphanijapps.github.io%2Fmemex%2F&label=docs)](https://phanijapps.github.io/memex/)

[Documentation](https://phanijapps.github.io/memex/) · [User guide](docs/gitpages/guide.md) · [Specification](docs/gitpages/spec.md) · [Harness adapters](marketplace/)

</div>

---

## Why

Agents that matter forget things that matter: your stack, your rules, your
decisions from last Tuesday. Vector databases and cloud memory services
solve this with infrastructure. Memex solves it with a **filesystem**:

- **The filesystem is the memory.** Every memory is a Markdown page under
  `~/.memex/docs/` — human-readable, git-able, editable by hand, portable
  forever. No blobs, no lock-in, no server.
- **The index is disposable.** SQLite FTS5 provides fast BM25 search, and it
  is never the source of truth: delete `mem.db`, run `memex rebuild-index`,
  everything comes back from the pages.
- **Every session is provable.** Captured transcripts link to episode nodes,
  so any memory traces back to the conversation that produced it.

## Agents forget to call tools — memex doesn't rely on them remembering

| Layer | Mechanism | Guarantee |
|---|---|---|
| **Pull** | 8 typed MCP tools (`memex serve-mcp`) | The model can read/write memory when it chooses |
| **Push** | Harness hooks (`memex hook …`) | Memories are injected into context **every turn**; transcripts are captured automatically |
| **Proof** | `memex verify` in CI | Health and memory-activity evidence — or the build fails |

One contract, every harness:

| Harness | Push | Pull | Transcript capture |
|---|---|---|---|
| [pi](marketplace/pi/) | per-turn injection (extension) | stdio MCP | session JSONL |
| [Claude Code](marketplace/claude/) | SessionStart / UserPromptSubmit / SessionEnd hooks | stdio MCP | transcript |
| [Codex](marketplace/codex/) | AGENTS.md contract + `notify` | stdio MCP | rollout |
| [GitHub Copilot](marketplace/copilot/) | CI carries it | remote (future) | `memex verify` workflow |

```bash
memex install              # interactive: pick a harness
memex install claude        # or codex, pi, copilot, custom
```

## Quickstart

```bash
# install (Python 3.12+)
uv tool install --path . memex

# store a memory — it's a plain Markdown page
memex write --type preference --title "Deploy on Fridays" \
    --body "The team deploys to production on Fridays only." --tags deploy

# recall it — BM25-ranked, snippet-highlighted
memex recall "deploy"

# read it, edit it by hand, commit it to git
cat ~/.memex/docs/preferences/deploy-on-fridays.md
```

<details>
<summary><strong>Python API</strong></summary>

```python
from memex import Memex, WriteInput

memex = Memex()
memex.write(WriteInput(type="entity", title="Ruff linter", body="Fast linter."))
result = memex.recall("linter", top_k=3)
provenance = memex.get_provenance(result.hits[0].slug)
memex.close()
```
</details>

<details>
<summary><strong>MCP tools</strong> (schemas carry enums and bounds; errors are sanitized `{"error": …}` data)</summary>

`memex_write` · `memex_recall` · `memex_consolidate` · `memex_forget` ·
`memex_ingest_transcript` · `memex_provenance` · `memex_export` ·
`memex_import`

```bash
claude mcp add memex -- memex serve-mcp
```
</details>

<details>
<summary><strong>Deterministic CI gate</strong></summary>

```bash
memex verify --since "$PR_CREATED" --require-recall --require-write
```

Always checks: every page parses, the index matches content hashes, every
`[[link]]` resolves. With `--since`, enforces recall/write activity evidence.
Exit 1 fails the build. Ready-made workflow: [marketplace/copilot/memex-verify.yml](marketplace/copilot/memex-verify.yml).
</details>

## Commands

| Command | Purpose |
|---|---|
| `write` / `recall` | Store and search memory nodes (BM25, filters, snippets, expiry semantics) |
| `forget` | `hard` delete, `soft` retire, `decay`, or `archive` a memory |
| `consolidate` | LLM distillation of episodes into durable nodes — any OpenAI-compatible endpoint, **or the coding harness itself** (`claude`/`codex`/`pi` as provider) |
| `ingest-transcript` | Store a session JSONL + create the linked episode node |
| `hook session-start \| prompt \| transcript` | Harness hook contract: context injection + transcript capture |
| `verify` | Deterministic health + activity gate for CI |
| `install` | Seamless harness setup: adapters, MCP wiring, `[consolidation]` provisioning, or custom init |
| `serve-mcp` | stdio MCP server (official SDK) |
| `rebuild-index` / `watch` | Rebuild `mem.db` from the pages; poll for hand edits |
| `backup` / `restore` / `export` / `import` | Hardened tar.gz archives; JSON node portability |

## Documentation

| | |
|---|---|
| 📖 [Documentation site](https://phanijapps.github.io/memex/) | Guide, specification, implementation notes |
| 🚀 [User guide](docs/gitpages/guide.md) | Concepts, every operation, harness integration, config reference |
| 📐 [Specification](docs/gitpages/spec.md) | Memory model, schemas, C4 diagrams, acceptance tests |
| 📝 [Implementation notes](docs/gitpages/implementation-notes.md) | Spec deviations and the reasoning |
| 🧩 [Harness adapters](marketplace/) | pi · Claude Code · Codex · GitHub Copilot |

## Contributing

```bash
uv sync --all-groups
uv run pytest && uv run ruff check . && uv run mypy src tests
```

Contributions welcome — see [AGENTS.md](AGENTS.md) for engineering
conventions and the guide for architecture context.

## License

[MIT](LICENSE) © Memex contributors

Memex stores memory as plain files on your machine and treats stored
memories and tool inputs as untrusted: logs never contain memory contents,
archives are validated before extraction, and tool errors are sanitized.
