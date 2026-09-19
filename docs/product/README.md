# Product

This directory records the product as it exists and where it is headed. It is
the product-side counterpart to [`../architecture/`](../architecture/): product
docs describe user outcomes and priorities, while architecture docs describe
the implemented system.

## Current documents

- [`roadmap.md`](roadmap.md) — current, next, and later priorities. Direction,
  not a release commitment.
- [`changelog.md`](changelog.md) — user-visible changes by released or
  unreleased version.
- [`intents/`](intents/) — accepted outcomes that have not necessarily become
  feature specs.

Feature contracts and plans live in [`../specs/`](../specs/). User-facing
instructions live in [`../gitpages/`](../gitpages/). Add personas or a release
checklist here only when the project has a concrete decision or manual release
step for those documents to own.

## Boundaries

- Past architectural choices belong in [`../adr/`](../adr/).
- Proposed cross-cutting changes belong in `../rfc/` if the project introduces
  an RFC process for them.
- Mission, scope, and principles belong in
  [`../CHARTER.md`](../CHARTER.md).
- Current code ownership and runtime flows belong in
  [`../architecture/`](../architecture/).

Everything in this directory is living documentation. Update it in the same
change as the product state it describes; do not preserve stale roadmap or
changelog text as history.
