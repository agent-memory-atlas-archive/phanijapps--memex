# Architecture overview

Memex is an installable Python package and CLI. It has no required service
process: commands and coding-agent hooks open a local store, perform one
operation, and exit. The optional `memex viz` server exists only for the life of
that command.

## System boundaries

```text
coding-agent harnesses ─┐
CLI (`memex`) ──────────┼─> application facade ─> Markdown pages
MCP stdio server ───────┘          │               SQLite FTS5 index
                                   │               transcript JSONL
                                   └─> optional LLM provider (consolidate only)
```

The filesystem under `MEMEX_DATA_DIR` or `~/.memex/` is the durable boundary.
Markdown pages are the source of truth. SQLite, run logs, transcript metadata,
and rendered dashboard responses are derived or supporting state.

## Code ownership

| Area | Responsibility | Start here |
| --- | --- | --- |
| `src/memex/domain/` | Validated models, front matter, slugs, links, scrubbing, and adapter-neutral operation datatypes. No filesystem, database, network, or SDK calls. | `models.py`, `operations.py` |
| `src/memex/application/` | The public `Memex` facade, orchestration, context packing, verification, decay, and the LLM port. | `memory.py`, `ports.py` |
| `src/memex/infrastructure/` | Markdown persistence, SQLite/FTS5, transcript parsing, archive safety, LLM clients, configuration, installers, and visualization. | `wiki_store.py`, `index_manager.py`, `config.py` |
| `src/memex/cli.py` | Argument parsing and JSON/text presentation for the shared services. | `_build_parser()`, `_run()` |
| `src/memex/mcp_server.py` | Typed stdio MCP tools over the same facade and domain datatypes. | `build_server()` |
| `marketplace/` | Thin harness-specific installation assets over the stable `memex hook` contract. | Per-harness `README.md` |
| `eval/` | Offline corpus generation, retrieval metrics, and scale experiments. It is development tooling, not package runtime. | `run.py`, `runner.py` |

`Memex` is both the public Python API and the composition root: it constructs
the filesystem store, index, retriever, link manager, transcript hook, archive
service, and import/export service. Infrastructure may implement application
ports and use domain types. Adapters should call the facade or shared
application services instead of reimplementing operations.

The CLI has two deliberate infrastructure-facing seams: harness installation
and harness-native transcript parsing. They adapt external files and processes
before handing normalized data to the shared application contract.

## Runtime flows

### Write

1. An adapter creates a validated `WriteInput`.
2. The facade rejects reserved provenance fields, scrubs secret-shaped text,
   and asks `WikiStore` to atomically write the Markdown page.
3. `IndexManager` mirrors the page into SQLite and `LinkManager` refreshes its
   outgoing links.

The page write justifies every index mutation. A failed or deleted index can be
rebuilt from the pages.

### Recall and injection

1. `BM25Retriever` reduces untrusted query text to safe alphanumeric tokens,
   removes only known semantic scaffolding phrases, and searches active,
   non-expired pages by default.
2. Returned hits update access statistics in SQLite; reads do not rewrite
   Markdown pages.
3. Hook injection applies a relevance floor, packs hits to a token budget, and
   emits a bounded context block. Explicit recall can still return weak hits.

Production recall uses the `semantic-and-fallback-fts5` ranker. It caps the
safe-token query at 64 tokens and 1,024 UTF-8 bytes, then first runs a strict
`AND` FTS5 query over the safe tokens with column weights
`slug=1, title=1, body=2, tags=1`, then broadens to an `OR` query only when the
strict query returns zero rows. Snippets are capped at 12 tokens. Filters are
applied before each limit, returned slugs are unique, links and access
statistics are loaded once after ranking, and ascending slug is the final
tie-break. The ranker is local SQLite FTS5 only: no embeddings, network service,
runtime `rgapi`, subprocess search, or new required dependency is on the recall
path.

### Retrieval evaluation security controls

Retrieval evaluation uses independent offline workloads and treats every source
as untrusted. Salesforce coverage is represented by concise, independently
authored offline Salesforce facts with official URLs as provenance; tests and
evaluations never scrape or fetch Salesforce pages. Gutenberg coverage comes
from a maintainer-supplied local Project Gutenberg catalog import, not from
HTML crawling or book text.

Fixture output is confined to the resolved repository fixture directory before
replacement. The Gutenberg importer accepts only a regular `.csv.gz` catalog,
enforces compressed and expanded parser limits, validates the allowlisted schema
and UTF-8 JSONL output, and stops before replacement on gzip, CSV, schema,
size, row, field, path, or serialization errors. Ordinary tests and evaluation
run with no network access; socket and HTTP sentinels prove that path.
Integrity failures fail closed rather than producing promotion evidence.
Retained reports are redacted: they keep categories, metrics, workload
manifests, ranker metadata, and non-identifying environment fields, but exclude
memory contents, credentials, raw non-generated queries, absolute or
user-specific paths, hostnames, usernames, device names, profile paths, stack
traces, and exception strings.

### Transcript capture

Harness adapters call `memex hook transcript` with the harness-native session
file. The parser normalizes turns and a session header, `TranscriptHook` writes
JSONL plus metadata, and an episode page links back to the transcript. Repeated
Codex captures merge by stable session identity so compaction and shutdown
events remain idempotent.

### Consolidation

Consolidation is the only operation that needs an LLM. `WikiConsolidator`
selects episode pages, calls the configured application `LLMClient` port, and
validates each returned node before using the normal write/index/link path.
Remote OpenAI-compatible providers and local harness CLI providers implement
the same port. Failures return a partial report and do not block the harness
hook.

### Verification and maintenance

`memex verify` checks page parsing, index freshness, links, and optional
recall/write activity evidence. `rebuild-index` reconstructs derived SQLite
state. Backup and restore validate archive paths and links; restore preserves
the previous store in a timestamped directory before replacement.

## Durable state

```text
~/.memex/                         # overridden by MEMEX_DATA_DIR
├── memex.toml                    # user-owned configuration
├── docs/<type>/<slug>.md         # authoritative memory pages
├── mem.db                        # disposable SQLite/FTS5 index
├── transcripts/<session>.jsonl   # captured turns
├── transcripts/<session>.meta.json
└── logs/                         # diagnostics and operation evidence
```

Repository content cannot enable capture or injection. Installation modifies
user-owned harness configuration only after an explicit command, and tests use
an isolated `MEMEX_DATA_DIR` rather than the developer's real store.

## Invariants

- Markdown pages remain sufficient to rebuild the searchable memory store.
- Domain modules perform no I/O.
- CLI and MCP behavior share services and wire datatypes.
- Stored memories, transcript data, archive members, and tool inputs are
  untrusted at every boundary.
- Logs contain identifiers and categories, never memory contents, credentials,
  or raw tool inputs.
- LLM use is explicit or opt-in; ordinary write, recall, capture, backup, and
  verification remain LLM-free.
- Hook failures degrade safely and do not block the coding-agent turn.

## Change guidance

- Change a page field in the domain model, strict front-matter codec,
  persistence mapping, index schema, import/export path, and adapter schemas
  together.
- Change a shared operation in the facade first, then keep CLI and MCP adapters
  thin and parity-tested.
- Change harness behavior behind the `memex hook` contract unless the shared
  contract itself must change.
- Treat a persistent schema change as rebuildable when all information exists
  in Markdown; otherwise provide an explicit migration and backward-compatibility
  plan.

The normal gates are `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy src tests`, `uv run pytest`, and `uv run mkdocs build --strict`.
