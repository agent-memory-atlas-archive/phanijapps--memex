# ADR-0004: Require user-scope enablement

- **Status:** Accepted
- **Date:** 2026-09-16

## Context

Hooks can capture transcripts and inject stored context into coding-agent
sessions. If a cloned repository could enable those behaviors through its own
files, opening untrusted code could silently change what is recorded or sent to
an LLM. Harness configuration is user-owned state and may contain unrelated
settings that an installer must preserve.

## Decision

Repository contents must not enable Memex capture, injection, or consolidation.
Enablement requires an explicit user action and is stored in user-owned harness
configuration or the user-selected Memex data directory.

Installers merge supported configuration conservatively, preserve unrelated
settings, and create backups before changing existing user files. Tests and
development commands use an isolated `MEMEX_DATA_DIR`; they never use the
developer's live store.

## Consequences

- Cloning or entering a repository cannot activate memory collection.
- Harness adapters must distinguish repository instructions from user-owned
  enablement state.
- Installation is an explicit trust-boundary operation and must remain
  idempotent and recoverable.
- CI and local tests need isolated homes or data directories.
- Repository-scoped metadata may help attribute a session, but it cannot grant
  capture authority.

## Alternatives considered

- **Repository-carried activation:** rejected because untrusted project content
  could opt a user into capture or injection.
- **Implicit activation when Memex is installed:** rejected because installation
  alone does not express consent for every harness or repository.
- **One global unqualified hook:** rejected because it weakens attribution and
  makes selective disablement harder.
