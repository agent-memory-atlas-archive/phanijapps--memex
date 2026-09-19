# ADR-0002: Use a layered package and shared adapter contracts

- **Status:** Accepted
- **Date:** 2026-09-15

## Context

Memex exposes the same memory operations through a Python API, a CLI, MCP
tools, and coding-harness hooks. A flat package or adapter-specific
implementations would make behavior drift likely and would couple pure memory
rules to filesystem, database, SDK, and presentation concerns.

## Decision

Organize the package into three responsibility areas:

- `domain` owns validated models, value rules, front matter, slugs, links,
  scrubbing, and adapter-neutral operation datatypes.
- `application` owns orchestration, the public `Memex` facade, context
  injection, verification, and ports for external capabilities.
- `infrastructure` owns filesystem, SQLite, transcript formats, archives,
  configuration, SDKs, installers, and visualization.

Keep `cli.py` and `mcp_server.py` as adapters. They reuse the facade, domain
models, operation descriptions, and wire datatypes instead of defining
parallel behavior. `Memex` is the composition root and may assemble concrete
infrastructure services behind the public application API.

## Consequences

- Domain logic remains testable without filesystem, database, network, or SDK
  access.
- A behavior or schema change must be reflected once in shared services and
  then exposed consistently by each adapter.
- Adapter parity tests are part of the contract, not optional duplication.
- Infrastructure may depend on domain types and implement application ports;
  domain code may not depend on infrastructure.
- Harness-specific file parsing and installation stay at adapter or
  infrastructure boundaries before normalized data enters the shared contract.

## Alternatives considered

- **Flat module build order:** rejected because it describes construction order
  but not lasting ownership.
- **Separate services per adapter:** rejected because CLI and MCP behavior
  would diverge.
- **A dependency-free domain with duplicate wire types elsewhere:** rejected
  because the adapter-neutral operation datatypes belong in the shared domain
  contract.
