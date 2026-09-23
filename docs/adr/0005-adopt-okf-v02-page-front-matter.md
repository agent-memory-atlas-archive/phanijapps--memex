# ADR-0005: Adopt OKF v0.2 as the page front-matter contract

- **Status:** Accepted
- **Date:** 2026-09-23
- **Deciders:** phanijapps
- **Spec:** [`../specs/okf-frontmatter/spec.md`](../specs/okf-frontmatter/spec.md)

## Context

Memex pages carried a front-matter vocabulary of their own. It overlapped the
Open Knowledge Format (OKF) v0.2 — the format the generated `index.md`
navigation already declared at the memory root — without matching it. Four
fields named the same concept under different names (`created`/`timestamp`,
`updated`/`updated_at`, `valid_to`/`valid_until`, `expires_at`/`stale_after`),
and `links` collided outright: OKF defines typed relation objects, Memex used
a flat list of slugs.

A store that declares `okf_version: "0.2"` at its root while its pages speak a
different dialect is not an OKF bundle. Either the declaration goes, or the
pages conform.

## Decision

Pages conform. Front matter carries the OKF v0.2 field set first, in the order
the OKF reference implementation writes it, followed by the Memex fields OKF
has no equivalent for. Where the two formats named one concept, the OKF name
is now the only name — on disk, in the domain model, in the SQLite index, and
on every adapter. No alias is kept for a retired name.

Three consequences follow from taking OKF's semantics and not just its
spelling:

- `timestamp` is refreshed on every write and `updated_at` moves only when the
  body changes, because that is what the reference writer does. Memex's own
  creation instant has no OKF counterpart, so it stays as the extension field
  `created`.
- `stale_after` is advisory. Validity — and therefore recall visibility — is
  the `valid_from`/`valid_until` window alone. `forget --soft` and
  `forget --decay` both end that window, differing only in when.
- Relations are one graph. Typed `links`, the four OKF relation fields, and
  body `[[slug]]` references all project into `wiki_links` as
  `(source, target, rel)` rows, so one validator covers them all.

Memex extension fields are conformant: the OKF reference parser routes unknown
keys into an `extra` map and preserves them verbatim on write.

## Alternatives considered

**Keep both vocabularies, translating at the codec.** Smallest diff, but the
files a person reads and the code they debug would speak different languages
forever. Rejected.

**Adopt only the field names, keeping Memex semantics.** Would have mapped
`created` onto `timestamp`, putting an immutable value in the field OKF
rewrites on every edit — an OKF tool editing a page would destroy the creation
date. Rejected as worse than not conforming at all.

**Give `links` to OKF and move Memex's slug list to a new key.** Considered and
chosen in part: `links` is OKF's, and Memex's flat list is retired rather than
renamed, because the four relation fields plus typed links already express
everything the flat list did.

**Store bundle-relative concept IDs as relation targets.** OKF concept IDs are
paths (`global/entities/foo`); Memex relations name bare slugs. Slugs were
kept: they are Memex's link identity everywhere else, including body
references, and the reference linter accepts the store as-is.

## Consequences

Breaking, with no migration path. A store written before this change cannot be
read after it, and the accepted remedy is to delete the store. The SQLite
schema moves to version 6 and rebuilds itself from Markdown.

CLI flags change (`--valid-until` replaces `--valid-to`, `--expires-at` is
gone, `--link target[:rel]` replaces `--links`), the MCP write tool gains
relation arguments, and export JSON follows the page keys. Recall hits carry
`timestamp` and `updated_at` in place of `updated`.

`memex verify` gains five OKF conformance checks, and the store passes the OKF
reference linter with no errors and no warnings.

PyYAML becomes a test-only dependency (MIT). The runtime keeps its
hand-written codec and remains free of a YAML dependency; the test suite uses
an independent YAML implementation to prove the codec emits what any OKF
reader parses.
