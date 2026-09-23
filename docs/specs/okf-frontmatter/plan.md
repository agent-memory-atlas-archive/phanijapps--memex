# Plan: OKF v0.2 page front matter

- **Spec:** [`spec.md`](spec.md)
- **Status:** Executing
- **Repository anchors:** `docs/gitpages/spec.md` §6.1 (page format);
  `src/memex/domain/frontmatter.py` (the codec that owns the subset);
  analogous shipped work — `docs/specs/agentic-frontmatter-search/` added the
  `description` field and OKF-style navigation through the same layers
  (`domain/models.py` → `infrastructure/wiki_store.py` →
  `infrastructure/index_manager.py` → adapters), with its tests in
  `tests/unit/test_frontmatter.py` and `tests/acceptance/test_wiki_store_acceptance.py`;
  `docs/specs/v1-guardrails/spec.md` added the `status`/provenance block the
  same way. Named uncertainty: OKF `resource` and Memex `transcript_ref`
  partially overlap; this plan keeps them separate (spec Boundaries, Ask first).

## Approach

Rename in one pass and keep exactly one vocabulary. The OKF field block is
emitted first in the reference implementation's order, the Memex extension
block follows, and the reader accepts precisely that set. `updated` becomes OKF
`timestamp` (rewritten on every write, as the OKF writer does), `valid_to`
becomes `valid_until`, and `expires_at` becomes `stale_after` — re-pointed to
its true OKF meaning: advisory, never a recall filter. OKF's `updated_at`
takes the meaning its type carries, moving only when the body changes, and
`created` stays a Memex extension because OKF has no creation field. Both
forget modes now end the validity window, `--soft` at once and `--decay` one
configured half-life out.

Typed links are the one genuinely new shape. They are stored as inline flow
mappings so the line-oriented codec keeps its one-key-per-line invariant, and
they unify with `parent`, `supersedes`, `implements`, `depends_on`, and body
`[[slug]]` references into a single `(source, target, rel)` graph.

No migration, no compatibility alias, no dual-key read. Existing stores are
deleted.

## Constraints

- The codec stays hand-written and strict; PyYAML is not a dependency.
- Front matter stays line-oriented: one key per line.
- `content_hash` remains body-only, so front-matter changes never churn it.
- SQLite stays disposable: the schema bump rebuilds from Markdown.
- No new dependency, no new top-level directory.

## Construction tests

| Behavior | Mode | Test |
| --- | --- | --- |
| Inline flow mapping round-trips through the codec | TDD | `tests/unit/test_frontmatter.py::test_typed_link_round_trip` |
| Malformed link entry is rejected with a field-named error | TDD | `tests/unit/test_frontmatter.py::test_link_entry_rejects_unknown_member` |
| Retired keys are unknown to the reader | TDD | `test_okf_frontmatter.py::TestPageShape::test_unknown_key_is_a_malformed_page` |
| Page key order is OKF-first | TDD | `TestPageShape::test_page_key_order` |
| `timestamp` every write, `updated_at` on body change, `created` once | TDD | `TestPageShape::test_timestamp_moves_every_write_and_created_never_does`, `TestReviewedCriteria::test_updated_at_moves_only_on_body_change` |
| Relation fields project into the link graph with their `rel` | TDD | `TestLinkGraph::test_relations_carry_their_rel` |
| One target, many relations, listed once | TDD | `TestReviewedCriteria::test_duplicate_target_appears_once_in_recall_and_backlinks` |
| Validity window hides; `stale_after` never does | TDD | `TestVisibility` (three tests), `TestReviewedCriteria::test_include_expired_returns_pages_outside_the_window` |
| Forget modes differ only in when validity ends | TDD | `TestForgetModes` (three tests) |
| Verify reports OKF graph and temporal defects, slugs only | TDD | `TestVerifyConformance` (three tests) |
| Export/import preserves every value under OKF names | TDD | `TestExternalConformance::test_export_carries_okf_names`, `::test_export_import_preserves_every_value` |
| An independent YAML reader agrees key-for-key | TDD | `TestExternalConformance::test_independent_yaml_parser_agrees` |
| The OKF reference linter accepts the store | Goal-based | `TestReviewedCriteria::test_store_passes_the_okf_reference_linter` (skips without the reference checkout) |
| CLI and MCP accept `target[:rel]` | Goal-based | `memex write --help`; `TestAdapterRelations` (two tests) |
| Real store is OKF-parseable | Manual QA | write, recall, and verify a page under an isolated `MEMEX_DATA_DIR`, record the bytes |

## Durable-output map

Per the spec's Durable Outputs table: ADR-0005, `docs/gitpages/spec.md` §6.1,
`docs/gitpages/guide.md`, `docs/architecture/overview.md`,
`docs/product/changelog.md`, `docs/knowledge/patterns.jsonl`.

## Design (LLD)

### Design decisions

- **Inline flow mappings, not block sequences.** The codec iterates
  `block.split("\n")`; a block sequence would break parsing outright. Inline
  flow is valid YAML and the OKF reference parser reads it.
- **One graph table.** Adding `rel` to `wiki_links` lets typed links, the four
  relation fields, and body references share one projection and one validator.
- **`stale_after` is advisory.** Adopting the OKF name without its meaning
  would mislead every OKF reader. Validity exclusion belongs to
  `valid_from`/`valid_until`.
- **`id` is kept.** OKF derives concept ids from the path; Memex needs a
  rename-stable primary key, and OKF preserves unknown keys.

### Data & schema

Page front matter, in emission order:

```
okf_version type title description resource tags timestamp valid_from
valid_until stale_after updated_at parent supersedes implements depends_on
links | id importance access_count last_access content_hash status occurred_at
source harness confidence scope project_id project_label session_id
transcript_ref
```

SQLite `SCHEMA_VERSION` → `6`. `wiki_index` columns `created`→`timestamp`,
`updated`→`updated_at`, `valid_to`→`valid_until`, `expires_at`→`stale_after`.
`wiki_links` gains `rel TEXT NOT NULL` inside the primary key.

### Interfaces & contracts

- CLI: `--links` (CSV) → repeatable `--link target[:rel]`; `--valid-to` →
  `--valid-until`; `--expires-at` removed; `forget --valid-to` →
  `--valid-until`; new `--parent`, `--supersedes`, `--implements`,
  `--depends-on`, `--stale-after`.
- MCP `memex_write`: `links` accepts `"slug"` or `"slug:rel"` strings.
- Export JSON keys follow the page keys.

### Failure, edge cases & resilience

A rejected link entry, an unparseable page, and a failed navigation refresh all
keep their current behavior: the error names the field, the page write is
atomic, and a navigation failure never fails an authoritative write.

### Quality attributes (NFRs)

Coverage gate 90%, `mypy --strict` clean, `ruff` clean, `mkdocs --strict`
clean.

## Tasks

### T1: Codec — inline flow mappings

`src/memex/domain/frontmatter.py`. Parse and serialize `[{k: "v"}, …]`.
Tests: the two codec rows above.

### T2: Domain — OKF field set

`src/memex/domain/models.py`, `src/memex/domain/links.py`. `SemanticLink`
dataclass, renamed fields, relation fields, validation.

### T3: Store — OKF-first page

`src/memex/infrastructure/wiki_store.py`. Key order, both dict mappers.

### T4: Index and graph

`src/memex/infrastructure/index_manager.py`,
`src/memex/infrastructure/link_manager.py`,
`src/memex/infrastructure/bm25_retriever.py`. Schema 6, `rel` column, single
visibility rule.

### T5: Application

`src/memex/application/memory.py`, `verify.py`, `decay.py`, `task_recall.py`,
`context_injection.py`. Forget collapse, OKF verify checks.

### T6: Adapters

`src/memex/cli.py`, `src/memex/mcp_server.py`,
`src/memex/infrastructure/import_export.py`, `consolidator.py`, `viz*.py`,
`transcript_hook.py`.

### T7: Docs and ADR

Per the durable-output map.

## Rollout

Big bang, no flag, no migration. Reversible only by `git revert` plus restoring
a store backup. The developer store was archived to
`~/memex-backup-2026-09-23.tar.gz` and cleared before T1.

## Risks

- **Wide rename touches 18 of 68 test files, plus four `eval/` modules.**
  Mitigated by running the suite after each task rather than at the end.
- **Typed links change a public output shape** (recall hits, export). Accepted:
  the spec makes it contract.
- **An OKF field could be misread from the reference implementation.** Mitigated
  by AC-0027 (an independent YAML reader must agree key-for-key) and AC-0028
  (the OKF reference linter must accept the store). The review caught exactly
  this class of error in `timestamp`.

## Changelog

- 2026-09-23: Drafted and approved; store cleared; execution started.
- 2026-09-23: Spec/plan review returned findings. Three changed the design
  before implementation:
  - OKF `timestamp` is the *mutation* instant, not creation
    (`okf-wiki/src/concepts/writer.ts:186` rewrites it on every edit). The
    original `created`→`timestamp` mapping would have let an OKF tool destroy
    the creation date. `created` stayed a Memex extension, `timestamp` became
    the every-write instant, and `updated_at` moves only when the body's
    content hash changes.
  - `forget --soft` and `forget --decay` would have become the same
    operation. `--decay` now ends the validity window one configured
    half-life out, so the two modes are distinguishable.
  - Fourteen acceptance criteria were not checkable as written (conjunctions,
    missing reference points, an unsatisfiable byte-equality claim). The set
    was rewritten as thirty single-predicate criteria.
- 2026-09-23: Dropped the front-matter merge of body `[[slug]]` references.
  Front matter now holds declared relations only; body references are
  `mentions` edges in the graph, matching OKF's model.
- 2026-09-23: `eval/` fixture writers no longer hand-build front matter; they
  call the store's own `node_front_matter`, removing three stale copies.
