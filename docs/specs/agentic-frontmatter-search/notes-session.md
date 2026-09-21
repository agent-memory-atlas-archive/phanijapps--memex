# Session notes — agentic-frontmatter-search (run 28e23fb6)

## Resolve-vs-surface disposition record (opened at PLAN)

1. "Direct memory pages under node-type headings" (AC-0016) — RESOLVED: an
   index lists pages whose file's parent directory is the index's own
   directory, grouped under a node-type heading (type-dir indexes list their
   pages; non-type dirs list child indexes only). Memex pages only ever live
   in type dirs, and OKF v0.2 §8 lists a directory's own concepts.
2. Description BM25 weight — RESOLVED: 1.0 ("neutral", matching slug/title/
   tags), giving the explicit vector (1.0, 1.0, 1.0, 2.0, 1.0) so existing
   column contributions are unchanged.
3. Root index heading wording — RESOLVED: implementation freedom, kept
   minimal and deterministic.
4. AC-0011 guidance surface — RESOLVED: marketplace snippets + repo AGENTS.md.
5. Structural vs legacy reserved file — RESOLVED: reserved name + no page
   front matter = structural (skip silently); reserved name + valid page
   front matter = legacy memory (kept); reserved name + broken front matter
   = malformed page error (reported like any other).

Nothing irreducible so far; no surface needed.

## Anchor-test sweep (pre-EXECUTE)

- tests/unit/test_bm25_retriever.py — pins production_ranker_metadata
  column_weights (add description key additively).
- tests/integration + acceptance eval suites — pin winners; must stay green
  with empty descriptions and the pinned weight vector.
- tests/unit/test_docs_retrieval_controls.py — pins architecture topics;
  docs edits must not remove them.
- tests/unit/test_wiki_store.py, test_frontmatter.py — round-trip based;
  additive field is safe.

## TDD stub deviation note

The approved plan describes tests semantically per task but carries no
literal stub code blocks. Implementers write the red tests per task before
production code (TDD intent preserved); plan text unchanged (locked).

## Disposition record (closed at DECIDE)

All REVIEW findings resolved in-loop; no surface stops occurred.

- R1 adversarial (9 sustained): all fixed (commit 3c373af watch wiring +
  shared on_page_written hook + post-scrub byte check + chain-scoped
  refresh; e17aaba nits incl. navigation_defects field + import scrub).
- R2 adversarial (6 sustained): all fixed (3d464b6 reserved-slug import
  rejection, scan-error translation, undecodable-reserved policy, tmp
  uniqueness, guide wording, docstring fields).
- R3 adversarial (1 nit): completed the R2 import containment at the write
  step (5d4dbb5).
- R4 specialists (7 sustained: 1 security + 6 quality): all fixed
  (793d7f1 symlink-guard in classification, downgrade notes, vocabulary
  dedupe, bounded partial log, tmp sweep, test de-privatization).
- R5 quality (3 sustained): all fixed (4c9d587 verified degradation wording
  replacing the incorrect "recall raises" claim, removed-excluded defect
  filter + caplog pin, dead test scaffolding).
- Final cleans: adversarial r4, security r5, quality r6 — all adjudicated
  clean; artifacts under .context/reviews/28e23fb6-*/.

Named skips: experience-reviewer (pack absent), frontend-reviewer (no
HTML/CSS/JS primary output). Learnings: durable lessons are encoded in
shipped artifacts (domain/reserved.py classification, downgrade notes,
bounded-log pins) — no separate knowledge entry needed.
