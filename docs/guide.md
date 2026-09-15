# Memex user guide

Everything you need to run memex for yourself, your agent, or your team.

- [Concepts](#concepts)
- [Getting started](#getting-started)
- [Operations](#operations)
- [Transcripts and provenance](#transcripts-and-provenance)
- [Harness integration](#harness-integration)
- [Deterministic checks (CI)](#deterministic-checks-ci)
- [Data portability](#data-portability)
- [Configuration reference](#configuration-reference)
- [Data safety](#data-safety)

## Concepts

**The wiki is the filesystem.** Every memory is a Markdown page under
`~/.memex/wiki/`, with YAML front matter and a Markdown body. Pages are
human-readable, git-able, and editable by hand in any editor. If you edit a
page externally, `memex rebuild-index` (or `memex watch`) picks it up.

```
~/.memex/
├── wiki/
│   ├── entities/        # people, tools, concepts
│   ├── preferences/     # "the user prefers ruff over flake8"
│   ├── procedures/      # rules and how-tos
│   ├── summaries/       # synthesized overviews
│   └── episodes/        # one per captured session
├── transcripts/         # raw session JSONL + metadata
├── mem.db               # disposable BM25 index (rebuildable)
├── memex.toml           # configuration
└── logs/                # operation audit trail (no memory contents)
```

**Node types.**

| Type | Holds | Example |
|---|---|---|
| `entity` | People, tools, concepts | "Ruff linter" |
| `preference` | Durable user preferences | "Prefer dark mode" |
| `procedure` | Rules, how-tos, constraints | "Never force-push main" |
| `summary` | Synthesized overviews | "Tooling decisions, Sept 2026" |
| `episode` | One captured session | "Session sess-abc123" |

**Links.** Reference other pages in any body with `[[slug]]` wiki-links
(`[[Ruff Linter]]` normalizes to `[[ruff-linter]]`). Links are indexed both
directions — backlinks answer "what mentions this?".

**The index is disposable.** `mem.db` mirrors the wiki for fast BM25 search
and freshness tracking. It is never the source of truth:

```bash
rm ~/.memex/mem.db
memex rebuild-index        # fully rebuilt from the wiki files
```

**Temporal validity.** Every node optionally carries `expires_at`,
`valid_from`, and `valid_to`. Expired or retired nodes are hidden from
recall by default (`--include-expired` / `include_expired=True` opts back in).

## Getting started

```bash
# install (from this repository)
uv tool install --path . memex

# store your first memory
memex write --type preference --title "Deploy on Fridays" \
    --body "The team deploys to production on Fridays only." --tags deploy

# recall it (and watch access statistics track usage)
memex recall "deploy"

# it's a plain file — read it, edit it, commit it
cat ~/.memex/wiki/preferences/deploy-on-fridays.md
```

Version-control your memory if you like:

```bash
cd ~/.memex/wiki && git init && git add -A && git commit -m "memory: initial"
```

## Operations

### write

```bash
memex write --type entity --title "Ruff linter" \
    --body "Fast Python linter written in Rust. See also [[python-3-12]]." \
    --tags tool,lint --importance 0.8 --links python-3-12
```

- Slugs derive from titles (`Ruff linter` → `ruff-linter`), collisions get
  `-2`, `-3` suffixes.
- Writing an existing slug **updates** it, preserving `id`, `created`, and
  access counters.
- `importance` ∈ [0, 1]; `[[slug]]` links in the body are indexed as edges.

### recall

```bash
memex recall "deploy" --top-k 5
memex recall "linting" --type preference --tag tooling
```

- BM25 over title, body, tags, and slug; results ranked best-first with
  `<mark>`-highlighted snippets.
- Filters: `--type`, `--tag` (AND semantics), `--top-k` (1–100),
  `--include-expired`.
- Every hit bumps its access counter — recall telemetry feeds
  [recency decay](#configuration-reference) and `verify` evidence.

### forget

```bash
memex forget deploy-on-fridays               # hard: file deleted, irreversible
memex forget deploy-on-fridays --mode soft   # valid_to=now; hidden from recall
memex forget deploy-on-fridays --mode decay --valid-to 2027-01-01T00:00:00Z
```

| Mode | Effect |
|---|---|
| `hard` | Deletes the page, its index row, and its links — irreversible |
| `soft` | Sets `valid_to`; page stays, hidden from recall by default |
| `decay` | Sets `expires_at`; naturally excluded once past |

### consolidate

The only LLM-calling operation, and only on explicit request. It reads recent
episode nodes and proposes durable entity/preference/procedure/summary nodes
(the prompt and rules live in the specification, §11).

```bash
memex consolidate --mode dry-run     # propose, write nothing
memex consolidate --max-episodes 10  # distill and write
```

Requires LLM credentials (`MEMEX_API_KEY` or `[llm]` in `memex.toml`). Works
with any OpenAI-compatible endpoint — OpenAI, Ollama, LM Studio, OpenRouter
— via one `openai`-SDK client pointed at the configured base URL.

### Maintenance

```bash
memex rebuild-index --force    # full re-index from the wiki files
memex watch                    # poll for hand-edited pages and re-index
memex info                     # counts, index state, last rebuild
```

## Transcripts and provenance

Store a session transcript and memex links it to an episode node — the
foundation for tracing any memory back to the conversation that produced it.

```bash
memex ingest-transcript --session-id sess-abc --turns-file turns.jsonl
```

`turns.jsonl` — one JSON object per turn:

```json
{"role": "user", "content": "I prefer ruff over flake8", "ts": "2026-09-15T10:00:00Z", "turn": 1}
{"role": "agent", "content": "Got it.", "ts": "2026-09-15T10:00:01Z", "turn": 2}
{"role": "tool", "tool_name": "bash", "result": "ruff installed", "ts": "2026-09-15T10:00:02Z", "turn": 3}
```

Ingestion writes `transcripts/sess-abc.jsonl` + `.meta.json`, creates
`wiki/episodes/sess-abc.md` with a `transcript_ref`, and indexes it. From
Python or MCP, `get_provenance(slug)` / `memex_provenance` reports how a
node traces back: **direct** (it has a transcript), **inferred** (an episode
links to it), or **none**.

Harness adapters capture transcripts automatically — see below.

## Harness integration

MCP tools alone depend on the model choosing to call them. Memex adds a
deterministic push layer and a verifiable proof layer:

```
L3  PROOF    memex verify (CI / pre-commit)   exit code fails the build
L2  PUSH     memex hook <event>               context injection + capture
L1  PULL     memex serve-mcp                  eight typed tools
```

### The hook contract

```
memex hook session-start [--query Q] [--top-k N]
    stdout: a memory context block (spec §5.4) or nothing; exit 0 either way
memex hook prompt [--prompt TEXT | stdin] [--top-k N]
    stdin: raw text, or a hook JSON payload with a "prompt" key
memex hook transcript --harness H [--path FILE]
    ingests a harness-native session file; idempotent; --path may instead
    arrive as transcript_path in stdin JSON
```

### Adapters

Install any of them with `memex install <name>` — the marketplace ships
inside the package, so no source checkout is needed (`memex install`
with no argument opens an interactive picker; installs are idempotent
and back up existing configs). `memex install custom` initializes
`~/.memex` only: directory tree plus a starter `memex.toml` with plain
LLM config, for harnesses memex doesn't know yet.

Installing `claude`, `codex`, or `pi` also provisions `memex.toml`
(absent one) with `[consolidation] provider = "<harness>"` — so
distillation rides the coding harness's own model, credentials, and
billing via its CLI print mode, with no separate API key.

**pi** — the reference adapter. A TypeScript extension injects repo-level
memories on the first turn and prompt-relevant memories on every turn, and
captures the session file on shutdown. Knobs: `MEMEX_BIN`, `MEMEX_TOP_K`,
`MEMEX_DISABLE`.

**Claude Code** — hooks in `settings.json`: SessionStart and
UserPromptSubmit inject context (hook stdout becomes context); SessionEnd
ingests the session transcript. MCP: `claude mcp add memex -- memex serve-mcp`.

**Codex** — no native injection point, so: an AGENTS.md memory contract
(recall at task start, write durable facts), MCP via `config.toml`, and a
`notify` wrapper that ingests each rollout on `agent-turn-complete`.

**GitHub Copilot (hosted)** — no hooks, no local stdio: the deterministic
layer carries it. The adapter installs a memory contract into
`.github/copilot-instructions.md` and a `memex verify` workflow on every PR.

### Automatic consolidation at session end

Capture and distillation can be one step. Any harness hook that ingests a
transcript can distill the fresh episode immediately — enabled per call with
`--consolidate`, or globally with `MEMEX_AUTO_CONSOLIDATE=1` (works for the
pi, Claude Code, and Codex adapters unchanged, since they all invoke the
same hook). Off by default: it spends tokens and needs credentials. Point
`[consolidation]` at a low-effort model — a local Ollama model, a
mini-tier endpoint, or a coding harness itself (`provider = "codex"`)
so distillation rides the same model your agent already uses. Failure never blocks the hook — a missing key
reports the reason, an unreachable model returns an empty consolidation
result.

```bash
memex hook transcript --harness pi --path <session.jsonl> --consolidate
```

### MCP tools

`memex serve-mcp` exposes eight tools with typed schemas (enums and bounds
in `inputSchema`, documented `{"error": ...}` result convention):

`memex_write`, `memex_recall`, `memex_consolidate`, `memex_forget`,
`memex_ingest_transcript`, `memex_provenance`, `memex_export`,
`memex_import`.

Schema violations are rejected by the server with a field-precise error;
domain rejections return sanitized error data. Tool descriptions are
call-time contracts authored in `memex.domain.operations` — the same
registry the CLI help uses.

## Deterministic checks (CI)

```bash
memex verify                                # health only
memex verify --since 2026-09-15T00:00:00Z --require-recall --require-write
```

Always checked: every wiki page parses; the index matches content hashes;
every link resolves. With `--since`, memex additionally reports recall
activity (access telemetry) and write activity (updated timestamps) since
the cutoff; `--require-*` turns missing evidence into exit code 1. The
Copilot adapter ships a ready-made workflow (`marketplace/copilot/
memex-verify.yml`).

## Data portability

```bash
memex backup --output memex-backup.tar.gz   # wiki + transcripts + mem.db snapshot
memex verify memex-backup.tar.gz 2>/dev/null || true   # (verification is built into restore)
memex restore --input memex-backup.tar.gz   # validates members, moves old data aside, rebuilds index
memex export --output nodes.json            # JSON node document
memex import --input nodes.json             # invalid entries skipped and reported
```

Archives are validated against path traversal and symlinks before
extraction; restores never delete your current data (moved to
`pre-restore-<timestamp>/`).

## Configuration reference

`~/.memex/memex.toml` — every section optional, defaults shown:

```toml
[app]
name = "memex"

[llm]
provider = "openai"        # openai | ollama | lmstudio | openrouter | custom
model = "gpt-4o"
# api_base = "http://localhost:11434/v1"   # per-provider default otherwise
# api_key — prefer the MEMEX_API_KEY env var
timeout = 60
max_tokens = 4096

[consolidation]
# Optional: distill episodes on a cheaper low-effort model.
# Every field falls back to [llm] when unset.
provider = "openai"        # openai | ollama | lmstudio | openrouter | custom
                           # ...or a coding harness: "claude" | "codex" | "pi"
model = "gpt-4o-mini"      # harness providers: passed as the CLI's --model

[bm25]
default_top_k = 10         # k1/b are reserved: SQLite FTS5 bm25() is not SQL-tunable

[recency_decay]
enabled = true
half_life_days = 30        # importance halves per N idle days (explicit apply only)

[index]
watch_poll_interval = 60   # 0 disables
auto_rebuild_on_startup = false

[wiki]
default_importance = 0.5
max_body_chars = 50000
slug_algo = "kebab"        # kebab | sha1

[logging]
level = "INFO"             # DEBUG | INFO | WARNING | ERROR
# file = "~/.memex/logs/memex.log"
```

Environment overrides (highest priority): `MEMEX_DATA_DIR`, `MEMEX_API_KEY`,
`MEMEX_LLM_PROVIDER`, `MEMEX_LLM_MODEL`, `MEMEX_LOG_LEVEL`, and for the
distillation model `MEMEX_CONSOLIDATE_PROVIDER`, `MEMEX_CONSOLIDATE_MODEL`,
`MEMEX_CONSOLIDATE_API_KEY`, `MEMEX_AUTO_CONSOLIDATE`.

## Data safety

- **Logs never contain memory contents.** The audit trail records
  operations, slugs, and counts — nothing else.
- **Stored memories and tool inputs are untrusted by design.** Front matter,
  transcripts, archives, and LLM output are validated at every boundary;
  consolidation output is schema-checked before any write.
- **MCP tool errors are sanitized** — no paths, memory text, or provider
  details cross the stdio boundary.
- **API keys** belong in `MEMEX_API_KEY`, not in `memex.toml`.
- **Nothing leaves the machine.** The only network call memex ever makes is
  the explicit `consolidate` operation, against the endpoint you configure.
