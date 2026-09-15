# Implementation notes — deviations from docs/spec.md

The spec (v1.0.0) was implemented as written except for the items below.
Each deviation is either a spec-internal defect fix or a decision ratified
during plan review (2026-09-15): "zero required dependencies" is not a hard
rule, and the OpenAI SDK is the single LLM client.

## Fixed spec defects

1. **FTS5 DDL could not index bodies (spec §6.2).** The external-content
   `wiki_fts` table mirrors `wiki_index`, which had no `body` column, and the
   sync triggers inserted `''` for body. `wiki_index` now carries a `body`
   mirror column and the ai/ad/au triggers sync real body text.
2. **Snippet column off-by-one (spec §7 Utility 3).** With FTS columns
   `(slug, title, body, tags)`, column 1 is the title. Body snippets use
   column 2; the title is the fallback. Because FTS5 `snippet()` returns text
   even for columns without a match, the body-vs-title decision detects the
   `<mark>` tags rather than emptiness.
3. **`bm25.k1`/`b` are not SQL-tunable.** SQLite FTS5 `bm25()` uses
   compile-time defaults. The config fields are parsed and stored but
   documented as reserved; ranking uses the built-in `bm25()`.
4. **Transcript filename contradiction.** §12.2 showed dated filenames
   (`2026-09-15-sess-x.jsonl`); the normative contracts (§7 Utility 7, §9.5)
   use `{session_id}.jsonl`. The contracts win.
5. **`read()` was specified to mutate files.** Incrementing `access_count`
   in front matter on every read would rewrite each page and churn git
   history. Reads are side-effect free; access counting lives in the index
   and is applied by recall.

## Ratified decisions

- **Dependencies.** `mcp>=2,<3` (already declared in pyproject) and
  `openai>=1.60` are required. Core memory operations (write/recall/forget/
  transcripts/backup) import neither at runtime.
- **One LLM client.** `OpenAICompatClient` (official `openai` SDK) serves
  OpenAI, Ollama, LM Studio, OpenRouter, and any compatible endpoint via
  `llm.provider` → default `api_base` mapping plus `llm.api_base` override.
  The spec's `OllamaClient`/`LMStudioClient` (hand-rolled `http.client`) and
  `AnthropicClient` (non-compatible API) were dropped.
- **MCP SDK v2.** `mcp` 2.x renamed `FastMCP` to `MCPServer`; the server uses
  `mcp.server.mcpserver.MCPServer` with `add_tool`.
- **Layered layout.** Modules follow AGENTS.md layering instead of the spec's
  flat build order: `memex/domain` (pure models, slugs, front matter, links),
  `memex/application` (facade, decay, ports), `memex/infrastructure`
  (filesystem, SQLite, LLM, config, backup), plus `cli.py` / `mcp_server.py`
  adapters. Spec module names are preserved.
- **YAML front matter.** Stdlib has no YAML parser. `memex.domain.frontmatter`
  implements a strict codec for the documented subset; PyYAML is not needed.
- **Extractor is single-match per turn.** The spec said "each matching cue
  phrase generates a WriteInput" (noisy: one turn could emit preference,
  rule, and fact nodes). The extractor emits the first matching category
  (preference > procedure > fact); complex extraction belongs to
  consolidation.
- **`WriteResult` (spec §14 File 1) is not defined by any schema and §9.1
  returns a `WikiNode`; it is not exported.**

## Behavioral notes

- Change detection hashes body text on read: a hand-edited page keeps a stale
  front-matter `content_hash`, so the watcher and `rebuild_index` compare a
  freshly computed hash against the index row and refresh the front matter
  when it differs.
- `IndexManager.rebuild_from_wiki` (spec §7 Utility 2) lives on the facade as
  `Memex.rebuild_index()`, which composes store scan, index upsert, link
  sync, stale-row removal, and metadata bookkeeping.
- Consolidation failures return a partial report (§9.3) with the LLM error
  logged; tool errors over MCP are sanitized to generic messages.
- Restore validates archive members (no absolute paths, `..`, links, or
  unexpected entries), moves current data to `pre-restore-{timestamp}/`
  instead of deleting, and snapshots `mem.db` via the SQLite backup API so
  WAL-mode databases archive consistently.

## Architecture update (post-build)

- **Shared operation contracts.** Operation descriptions and wire
  datatypes live in `memex.domain.operations` and are consumed by every
  adapter — the CLI (subcommand help), the MCP server (tool
  descriptions and schemas), and any future API. AGENTS.md's
  dependency-free-domain rule was replaced by this reuse mandate; parity
  tests pin the wire datatypes to their domain-model twins.

## Harness hooks (post-build)

- The `memex hook` command family is the stable adapter contract:
  `session-start` and `prompt` emit the spec §5.4 context block on
  stdout (empty output when nothing is stored), `transcript` ingests
  harness-native session files (pi sessions, Claude transcripts, Codex
  rollouts) with idempotent, filename-derived session ids. The
  marketplace/ directory ships per-harness adapters over this contract;
  pi is the reference implementation.

- `memex verify` (L3) always checks health (parseable wiki, index
  freshness against content hashes, link integrity) and optionally
  enforces recall/write activity evidence since an ISO cutoff — the
  exit code is CI-able. `memex harness install` ships the marketplace
  adapters idempotently (pi copy; claude/codex config merge with
  backups; copilot instructions + verify workflow).

- **First-class hook-driven consolidation (spec §2.2 deviation, opt-in).**
  The spec excluded auto-summarization because tool-calling LLMs are not
  universally available. Consolidation remains off by default and
  LLM-free until explicitly enabled — via `memex hook transcript
  --consolidate` or `MEMEX_AUTO_CONSOLIDATE=1` — and a dedicated
  low-effort model can be configured under `[consolidation]`, inheriting
  `[llm]` credentials. Failures degrade to partial reports and never
  block the hook.

- **Harness-as-LLM-provider + seamless install.** `claude`, `codex`,
  and `pi` are valid `[consolidation]` providers: consolidation runs
  through the harness CLI's print mode (its model, credentials,
  billing) instead of a configured HTTP endpoint. `memex install`
  replaces `harness install` as the primary command, resolves the
  marketplace from the bundled package copy, provisions `[consolidation]`
  for harness installs, and `custom` initializes `~/.memex` only.
  `--data-dir` now locates `memex.toml` too, making redirected runs
  self-contained.

- **Transcript session headers.** The first line of a transcript JSONL
  is now a `memex_session_header`. The Codex parser is built against
  real rollout data (`session_meta`, `turn_context`,
  `token_usage_record` with `turn_token_usage`/`thread_token_usage`):
  totals take the latest records — cumulative values are never summed —
  per-turn usage attaches to the agent turn it billed, resumed sessions
  (re-emitted `session_meta`) refresh cwd/git and set `resumed`, and
  model changes collect into ordered `models`/`reasoning_efforts` lists.
  Readers skip headers; turn-only transcripts stay readable.
