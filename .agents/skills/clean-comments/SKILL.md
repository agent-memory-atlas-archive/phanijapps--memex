---
name: clean-comments
description: Use when writing, fixing, editing, or reviewing Python comments and docstrings. Enforces high-information documentation—call-sufficient contracts, pyguide-style sections on public APIs, doctest examples—while removing metadata, redundancy, stale comments, and commented-out code.
when_to_use: |
  Also trigger on: commented-out code; TODO, FIXME, HACK, NOTE, or warning
  comments; author, ticket, date, version, or change-history metadata in
  comments; a docstring that no longer matches the implementation; comments
  that restate obvious code (`i += 1  # increment i`); undocumented public
  APIs; docstrings that restate names or type annotations; or asks like "is
  this comment useful" or "why is this block commented out".
---

# Clean Comments

Write comments and docstrings only when they add information the code cannot
express clearly by itself.

The goal is not fewer comments. The goal is higher information density:
contracts, rationale, constraints, invariants, side effects, surprises.

## Core Principle

Prefer this order — improve the code before adding a comment:

1. Clear names
2. Small, focused functions and classes
3. Type annotations
4. Constants instead of magic values
5. Assertions or validation for enforceable invariants
6. Docstrings for public contracts
7. Comments for non-obvious reasoning or constraints

Never delete a comment that records a design decision, external constraint,
security rule, concurrency assumption, or reason an obvious alternative is
wrong — rewrite it more clearly instead. Git preserves history; comments
preserve reasoning.

## Comment Rules (quick reference)

Full rules with examples: [references/comments.md](references/comments.md)

| Rule | One line |
| --- | --- |
| C1 No inappropriate info | No authors, dates, tickets, change history — that belongs to Git/issue trackers |
| C2 Delete obsolete comments | A stale comment is worse than none; update docs in the same edit as the code |
| C3 No redundant comments | Never restate what the code says; add semantics, not translation |
| C4 Write comments well | Brief, specific, adjacent to the code, focused on why |
| C5 No commented-out code | Delete it; Git preserves versions |
| C6 Intent, not mechanics | Explain why and constraints, not what |
| C7 Refactor before commenting | Rename, extract, constant, type, validate — comment only what remains |
| No TODO/FIXME/HACK labels | Explain the actual constraint instead; TODOs must name concrete unresolved work |
| No decorative sections or closers | `# ==== X ====` and `# end if` are noise; fix the structure |

## Docstring Rules (quick reference)

Full rules with examples: [references/docstrings.md](references/docstrings.md)
Templates to copy: [assets/docstring-templates.md](assets/docstring-templates.md)

| Rule | One line |
| --- | --- |
| Call-sufficiency test | A docstring must let a caller write the call without reading the body |
| Document contracts, not syntax | Never restate names, types, or obvious returns |
| Method documentation | pyguide-style sections (`Args`/`Returns`/`Raises`) on public APIs, with real contract content — never skeleton filler |
| Style ladder | One-liner → summary + details → sections; escalate only as facets grow |
| Examples beat prose | Runnable doctest examples for tricky behavior |
| Negative space | What it does NOT do (no I/O, no locking, no retry) is contract |
| Class invariants once | Class docstring carries invariants so methods don't repeat them |
| Sections only where owed | Internals stay terse; private helpers need nothing by default |

## Review at a Glance

Classify before changing — never delete first and reason afterward:

| Category | Action |
| --- | --- |
| `contract` / `rationale` / `constraint` / `invariant` | Keep or clarify |
| `redundant` / `commented_code` / `metadata` | Delete |
| `stale` | Update or delete |
| `unclear` | Rewrite if useful, otherwise delete |

Full procedure, editing and reviewing workflows, output behavior:
[references/reviewing.md](references/reviewing.md)

## Final Test

A comment or docstring survives review only if it answers a question the code
cannot answer on its own:

- Why? Under what constraint?
- What must remain true?
- What does the caller rely on — and what must the caller know to call this
  without reading the body?
- What surprising behavior or side effect exists?

If it answers none of these, improve the code or delete the comment.
