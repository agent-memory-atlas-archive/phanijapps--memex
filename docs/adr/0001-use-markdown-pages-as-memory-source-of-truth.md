# ADR-0001: Use Markdown pages as the memory source of truth

- **Status:** Accepted
- **Date:** 2026-09-15

## Context

Agent memory must survive process exits, remain inspectable without Memex, and
be portable across coding harnesses. A database-only store would make the
database format and application runtime prerequisites for reading or correcting
memory. Search metadata and access statistics still need efficient queries.

## Decision

Store every durable memory as a Markdown page under the user's Memex data
directory. Treat those pages as authoritative.

Use SQLite FTS5 as a secondary index for BM25 search, freshness metadata,
access statistics, and link adjacency. The index may be deleted or replaced and
must be reconstructable from the pages. A schema version that can be recovered
entirely from page content is handled by rebuilding rather than migrating the
index in place.

## Consequences

- Users can read, edit, copy, diff, and version memories with ordinary file
  tools.
- Every operation that changes searchable content must keep the page, index,
  and link graph coherent.
- Hand edits require freshness detection and index rebuilding.
- SQLite-only metadata must remain non-authoritative or be explicitly accepted
  as disposable.
- Memory-page schema changes require backward-compatible parsing or a page
  migration; an index rebuild cannot recover information absent from the page.

## Alternatives considered

- **SQLite as the primary store:** rejected because it makes an opaque database
  the only durable representation.
- **A graph database:** rejected because page links and a derived adjacency
  table satisfy the current single-user use case.
- **A hosted or vector database:** rejected because it adds service, account,
  synchronization, and portability requirements outside the local-first
  boundary.
