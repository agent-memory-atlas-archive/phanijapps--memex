# Spec: OKF v0.2 page front matter

- **Status:** Implementing
- **Owner:** phanijapps
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** ADR-0001
- **Brief:** none
- **Discovery:** none
- **Contract:** the page front-matter format (`docs/gitpages/spec.md` §6.1)
- **Shape:** data

> **Spec contract:** this document defines what "done" means. The implementing
> PR must match this spec, or update it. Verification must be derivable from it.

## Objective

A Memex page is a conformant Open Knowledge Format (OKF) v0.2 concept. Every
page declares `okf_version: "0.2"` and carries the OKF field set first, in the
order the OKF reference implementation writes it, followed by the Memex fields
that OKF has no equivalent for. An OKF tool reading `~/.memex/docs/` sees a
valid bundle; a person reading a page sees one vocabulary rather than two.
Where OKF and Memex previously named the same concept differently, the OKF name
is the only name — on disk, in the domain model, in the index, and on every
adapter.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Decision rationale | Applicable — adopting an external format as the page contract is a durable architectural commitment | `docs/adr/0005-adopt-okf-v02-page-front-matter.md` | author | ADR exists, states the alternatives and the accepted breakage | ADR is referenced from the spec header |
| Current product truth | Applicable — the front-matter table is user-visible contract | `docs/gitpages/spec.md` §6.1, `docs/gitpages/guide.md` | author | Field table matches the shipped key set and order | `mkdocs build --strict` passes |
| Current architecture | Applicable — link graph and index schema change | `docs/architecture/overview.md` | author | Page-format and link-graph paragraphs describe typed relations | Section names the `rel` dimension |
| Release history | Applicable — breaking format change | `docs/product/changelog.md` | author | Unreleased entry states the break and the required store reset | Entry names the deleted fields |
| Interface compatibility | Applicable — CLI flags, MCP schema, and export JSON keys change | `docs/gitpages/guide.md`, MCP tool docstrings | author | Renamed flags documented; no legacy alias documented | Guide shows `--valid-until`, typed `--link` |
| Reusable learning | Applicable — OKF conformance is now checkable | `docs/knowledge/patterns.jsonl` | author | Pattern entry for external-format adoption | Entry lints clean |

## Boundaries

### Always do

- Write the OKF field block first, in OKF reference order, then the Memex
  extension block.
- Keep the front-matter codec line-oriented: one key per line, inline flow
  collections only.
- Validate every untrusted front-matter value at the store boundary, including
  each member of a typed link entry.
- Treat the page on disk as the source of truth; SQLite stays disposable and
  rebuildable.

### Ask first

- Adding any front-matter key that is neither an OKF v0.2 field nor an existing
  Memex field.
- Changing body link syntax away from `[[slug]]`.
- Merging `transcript_ref` into OKF `resource`. `resource` ships with a
  `--resource` flag and an otherwise empty producer set.

### Never do

- Emit a front-matter key the reader does not accept, or accept one the writer
  does not emit.
- Keep a legacy alias for a renamed field: this format has one name per concept.
- Log memory contents, credential-shaped strings, or absolute paths from any
  new validation or diagnostic path.
- Let a page-format error leave a partially written page on disk.

## Testing Strategy

- **Front-matter codec** (parse and serialize inline flow mappings, reject
  everything outside the subset): TDD. The invariant is compressible and pure.
- **Domain validation** (typed link shape, temporal ordering, OKF field
  constraints): TDD.
- **Store round-trip** (write → read → identical node, key order on disk): TDD,
  exercised as an acceptance test across the real filesystem.
- **Index and link graph** (schema v6, `rel` column, relation fields projected
  into `wiki_links`): TDD at integration surface.
- **Adapters** (CLI flags, MCP schema, export JSON): goal-based checks —
  `--help` output, a JSON round-trip, and `mypy` prove the wiring.
- **OKF conformance**: goal-based — a generated store passes the OKF
  reference linter's ERROR-level rules, reimplemented in `memex verify`.
- **Real invocation**: visual / manual QA — write, recall, and inspect a page
  through the installed CLI against an isolated `MEMEX_DATA_DIR`, with the
  observed page content recorded.

## Acceptance Criteria

- [x] **AC-0001.** Every page written by any surface begins with
      `okf_version: "0.2"`, followed by the fifteen OKF v0.2 fields in the
      order the OKF reference writer emits them (`type`, `title`,
      `description`, `resource`, `tags`, `timestamp`, `valid_from`,
      `valid_until`, `stale_after`, `updated_at`, `parent`, `supersedes`,
      `implements`, `depends_on`, `links`), followed by the Memex extension
      fields.
- [x] **AC-0002.** The front-matter reader accepts exactly the keys the writer
      emits. An unknown key is a malformed page reported through the existing
      malformed-page path, and the keys `updated`, `valid_to`, and
      `expires_at` are unknown.
- [x] **AC-0003.** A page whose `okf_version` is absent or is not `"0.2"` is a
      malformed page.
- [x] **AC-0004.** `timestamp` is rewritten on every page write, matching the
      OKF reference writer. `updated_at` changes only when the body's content
      hash changes. `created` is set once and preserved across every later
      write.
- [x] **AC-0005.** A typed link is stored as an inline flow mapping on one line
      with `target` and `rel` string members and an optional `label`.
- [x] **AC-0006.** A link entry missing `target`, carrying a member other than
      `target`/`rel`/`label`, or carrying a non-string member value is
      rejected at the boundary.
- [x] **AC-0007.** A rejected link entry's error message names the offending
      field and contains no page body, title, or description.
- [x] **AC-0008.** `parent` is a single slug or null; `supersedes`,
      `implements`, and `depends_on` are lists of slugs. Each is lowercased,
      stripped, and deduplicated exactly as `tags` are.
- [x] **AC-0009.** The link graph holds one row per `(scope, project_id,
      source_slug, target_slug, rel)`. Front-matter links contribute their
      declared `rel`, body `[[slug]]` references contribute `mentions`, and
      `parent`, `supersedes`, `implements`, and `depends_on` contribute a `rel`
      named after the field.
- [x] **AC-0010.** A body `[[slug]]` reference is not copied into front matter:
      a page whose only references are in its body stores `links: []`.
- [x] **AC-0011.** A target reached by more than one relation appears once in
      every reader-facing link list — recall hits, `get_outgoing`, backlinks,
      and the link graph.
- [x] **AC-0012.** With `include_expired` false, recall excludes a page whose
      `valid_until` is at or before the query instant.
- [x] **AC-0013.** With `include_expired` false, recall excludes a page whose
      `valid_from` is after the query instant.
- [x] **AC-0014.** `include_expired=True` (CLI `--include-expired`) disables
      both validity exclusions and returns the page.
- [x] **AC-0015.** `stale_after` never excludes a page from recall, at any
      value, with `include_expired` false.
- [x] **AC-0016.** `forget --soft` sets `valid_until` to the supplied
      timestamp or, absent one, the current instant.
- [x] **AC-0017.** `forget --decay` sets `valid_until` to the supplied
      timestamp or, absent one, the current instant plus
      `recency_decay.half_life_days`, so a decayed page stays recallable until
      then.
- [x] **AC-0018.** Neither forget mode writes `stale_after`.
- [x] **AC-0019.** `memex verify` reports, as five distinct named checks: a
      `parent` that resolves to no page, a cycle in the `parent` chain, a
      relation target that resolves to no page, a page whose `valid_from` is
      later than its `valid_until`, and a page whose `stale_after` falls
      outside its validity window when both bounds are set. The pre-existing
      `links-resolve` check continues to report broken targets from the graph;
      a broken relation target is reported by both.
- [x] **AC-0020.** Each OKF check's detail states a count and at most three
      page slugs, and contains no page body, title, description,
      credential-shaped string, absolute path, or username.
- [x] **AC-0021.** `memex write --link <target>` records `rel` `relates-to`,
      and `--link <target>:<rel>` records the given `rel`. The MCP
      `memex_write` tool accepts the same two string forms.
- [x] **AC-0022.** `memex merge <target> <source>` adds `source` to the
      target page's `supersedes` list and sets the source page's status to
      `superseded`.
- [x] **AC-0023.** A consolidation link emitted as a bare slug is stored with
      `rel` `relates-to`; one emitted as `"slug:rel"` keeps that `rel`.
- [x] **AC-0024.** A recall hit carries `created`, `timestamp`, and
      `updated_at`, and carries no field named `updated`. The CLI and MCP
      recall surfaces serialize the same field set.
- [x] **AC-0025.** Export emits every front-matter value under its OKF key
      name, and emits no key named `updated`, `valid_to`, or `expires_at`.
- [x] **AC-0026.** An export imported into an empty store reproduces
      `created`, `valid_from`, `valid_until`, `stale_after`, `parent`,
      `supersedes`, `implements`, `depends_on`, and `links` with the values
      the source page held. `timestamp` and `updated_at` are write instants
      and move, because an import is a write.
- [x] **AC-0027.** For a page written by this version, an independent YAML
      implementation parses the front matter into the same key order and the
      same values as the Memex codec, typed links included. Generated
      `index.md` and `log.md` files are structural, not concepts, and are out
      of scope for this criterion.
- [x] **AC-0028.** A store of described pages written by this version passes
      the OKF reference linter (`okf-lint`) with zero errors and zero
      warnings. A page written without a `description` draws OKF's
      recommended-field warning and no error.
- [x] **AC-0029.** The SQLite schema declares version 6, and a store carrying
      an earlier schema rebuilds from Markdown without modifying a page file.
- [x] **AC-0030.** The specification, user guide, architecture overview,
      implementation notes, and changelog state the shipped key set, the
      retired names, and the required store reset, and `mkdocs build --strict`
      passes.

## Follow-ons

- author: `docs/backlog/003-okf-body-links.md` — convert body `[[slug]]`
  references to OKF Markdown links so external OKF tooling can traverse the
  Memex graph.
- author: `docs/backlog/004-okf-bundle-import.md` — accept foreign OKF bundles
  by relaxing the reader to full YAML while keeping the writer's strict subset.

## Assumptions

- Technical: OKF v0.2's authoritative field set, order, and semantics are taken
  from the reference implementation at `~/code/okf-wiki` — `src/concepts/parser.ts`,
  `src/concepts/writer.ts` (`buildFrontmatter` field order), `src/graph/migrate.ts`
  (per-concept `okf_version` stamping), and the conformance rules in
  `bootstrap/skills/okf-lint/SKILL.md` (source: probe 2026-09-23).
- Technical: OKF parsers route unknown front-matter keys into an `extra` map and
  preserve them verbatim on write, so Memex extension fields are conformant
  (source: `~/code/okf-wiki/src/concepts/parser.ts` `...rest` handling).
- Technical: `forget --soft` and `forget --decay` already perform the same
  mutation against different fields, so collapsing them onto `valid_until` loses
  no behavior (source: `src/memex/application/memory.py:377`).
- Process: no migration path is provided and existing stores are deleted; the
  developer store was backed up to `~/memex-backup-2026-09-23.tar.gz` and
  cleared before implementation (source: user confirmation 2026-09-23).
- Product: OKF names win every overlap, Memex fields are retained only where
  they carry behavior OKF has no field for, and no legacy alias is kept
  (source: user confirmation 2026-09-23).
- Technical: OKF `timestamp` is the mutation instant, not the creation
  instant — `updateConceptFile` overwrites it on every edit
  (`~/code/okf-wiki/src/concepts/writer.ts:186`). An earlier draft of this
  spec mapped `created` onto `timestamp`; that was corrected in review before
  implementation, and `created` stayed a Memex extension field
  (source: probe 2026-09-23).
- Technical: the OKF reference writer appends `okf_version` after `links`
  because it is not in its known-key set; Memex writes it first. A page
  round-tripped through an OKF writer returns with `okf_version` last, which
  remains a valid page (source: `~/code/okf-wiki/src/concepts/writer.ts:88`).
