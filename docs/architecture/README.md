# Architecture

This directory describes the system that is implemented now. Read
[`overview.md`](overview.md) before changing a cross-cutting flow or deciding
which package owns new behavior.

The detailed, build-time contract remains in
[`../gitpages/spec.md`](../gitpages/spec.md). Shipped differences from that
contract are recorded in
[`../gitpages/implementation-notes.md`](../gitpages/implementation-notes.md).
Accepted structural choices and their trade-offs are preserved in
[`../adr/`](../adr/).

Update this directory with changes to package boundaries, state ownership,
adapter composition, or major runtime flows. Feature behavior belongs in a
spec, user instructions belong in `docs/gitpages/`, and historical rationale
belongs in an ADR.
