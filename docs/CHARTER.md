# Charter

> The stable statement of why Memex exists, what belongs in the project, and
> which principles resolve design trade-offs. Current product behavior lives in
> [`product/`](product/); implementation structure lives in
> [`architecture/`](architecture/); accepted decisions live in [`adr/`](adr/).

## Mission

Memex gives AI coding agents durable, inspectable memory that remains under the
user's control and survives any individual agent session or harness.

## Scope

Memex provides:

- A local, single-user memory store made of human-readable Markdown pages.
- A disposable SQLite FTS5 index for BM25 retrieval, freshness checks, access
  statistics, and link adjacency.
- Typed Python, CLI, and MCP operations for writing, recalling, consolidating,
  retiring, importing, exporting, backing up, and restoring memories.
- Deterministic hooks that inject relevant context and capture transcripts for
  supported coding-agent harnesses.
- Provenance links from stored memories to their source sessions.
- Health checks, CI evidence, and a read-only local dashboard for inspecting the
  store.
- Optional LLM-assisted consolidation through an explicitly configured API or
  an installed coding harness.

Memex does not provide:

- A hosted memory service, cloud account, or always-running daemon.
- Multi-user synchronization, shared conflict resolution, or a relay server.
- Vector, embedding, cross-encoder, or graph-database retrieval.
- A general agent runtime or replacement for a coding harness.
- Automatic capture enabled by repository contents alone; installation and
  enablement require user action outside the cloned repository.
- A guarantee that model-generated memories are true; provenance, approval,
  and inspectable files make them reviewable instead.

## Principles

1. **Files are the durable truth.** A memory must remain readable and editable
   as Markdown even when the index, application, or harness is unavailable.
2. **Derived state is replaceable.** SQLite accelerates retrieval but never
   owns information that cannot be reconstructed from the files.
3. **The user controls activation and data.** Capture, injection, and
   consolidation are enabled deliberately, and memory contents stay local
   unless the user configures an LLM provider.
4. **One contract serves every adapter.** The Python API, CLI, MCP tools, and
   harness integrations share domain models and application services rather
   than implementing competing behavior.
5. **Deterministic checks guard probabilistic work.** Parsing, indexing,
   provenance, budgets, approvals, and CI checks are deterministic even when an
   LLM helps consolidate memories.
6. **Agent work must fail safely.** A broken recall, capture, or consolidation
   path reports diagnostics without blocking the coding-agent turn or exposing
   memory contents.
7. **Provenance is part of the memory.** A durable claim should retain enough
   source information to be reviewed, corrected, or retired later.

## Document ownership

- [`product/`](product/) records the current product direction and visible
  release history.
- [`architecture/`](architecture/) explains the implemented system and where
  changes belong.
- [`adr/`](adr/) preserves accepted architectural decisions and their
  trade-offs.
- [`specs/`](specs/) contains feature contracts and implementation plans.
- [`gitpages/`](gitpages/) is the published user documentation and detailed
  build specification.
- [`CONVENTIONS.md`](CONVENTIONS.md) defines how repository artifacts are
  authored and maintained.

## When to revise

Revise this charter when the mission, project boundary, or a principle truly
changes. Ordinary product changes belong in the roadmap or a feature spec;
architectural choices belong in an ADR; current implementation changes belong
in the architecture documentation.
