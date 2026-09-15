# Reviewing and Workflow

Procedures for reviewing, editing, and output behavior.

## Review Procedure

When reviewing Python comments or docstrings, classify each one before changing it.

Use these categories:

- `contract`: Caller-facing behavior or guarantees
- `rationale`: Why the implementation exists
- `constraint`: External or internal limitation that shapes the code
- `invariant`: Condition that must remain true
- `redundant`: Restates the code
- `stale`: No longer matches the code
- `metadata`: Author, date, ticket, history, or ownership information
- `commented_code`: Disabled implementation
- `unclear`: Potentially useful but poorly written or ambiguous

Then take the appropriate action:

| Category | Action |
| --- | --- |
| contract | Keep or clarify |
| rationale | Keep or clarify |
| constraint | Keep or clarify |
| invariant | Keep or clarify |
| redundant | Delete |
| stale | Update or delete |
| metadata | Delete or move to the appropriate system |
| commented_code | Delete |
| unclear | Rewrite if useful, otherwise delete |

Never delete first and reason afterward.

---

## Writing New Documentation

Before adding a comment, ask:

1. Can naming express this?
2. Can structure express this?
3. Can types express this?
4. Can a constant express this?
5. Can validation or an assertion enforce this?
6. Is the information already documented elsewhere nearby?
7. Will this comment explain why, a constraint, or an invariant?
8. Is the information likely to remain true if implementation details change?

Before adding a docstring, ask:

1. Is this object public or externally consumed?
2. Is its responsibility obvious?
3. Is its contract fully expressed by name and types?
4. Are there important side effects?
5. Are there non-obvious exceptions?
6. Are there lifecycle or ownership rules?
7. Are there invariants callers must understand?
8. Am I documenting behavior instead of implementation?

If the documentation adds no information, do not add it.

---

## Editing Existing Code

When modifying Python code:

1. Inspect nearby comments and docstrings.
2. Verify they still describe the current behavior.
3. Remove obsolete or redundant documentation.
4. Preserve rationale, constraints, and invariants that still apply.
5. Update public contracts when behavior changes.
6. Delete commented-out code.
7. Do not add commentary merely to explain the edit itself.

A code change and its documentation change should happen together.

---

## Reviewing Existing Code

When asked to clean comments or docstrings:

1. Read the implementation before judging the documentation.
2. Classify each comment or docstring.
3. Delete metadata, stale comments, redundant narration, and commented-out code.
4. Rewrite unclear but valuable rationale.
5. Add missing documentation only where the contract, invariant, side effect,
  or external constraint is not otherwise clear.
6. Prefer refactoring over explanatory comments when structure is the real problem.
7. Preserve project-specific docstring style unless the user asks to change it.
8. Do not rewrite unrelated code solely to satisfy this skill.

---

## Output Behavior

When applying this skill:

- Make the code change directly when editing is requested.
- Do not add comments explaining obvious edits.
- Do not report every removed comment unless the user asks for a review summary.
- Preserve the existing docstring convention, such as Google, NumPy, Sphinx, or
  concise PEP 257 style, unless there is a reason to change it.
- Prefer concise docstrings over boilerplate sections.
- Do not change runtime behavior unless refactoring is necessary to replace a
  redundant comment with clearer code.
- If a comment appears to encode important but uncertain domain knowledge, do
  not silently delete it. Preserve it or flag it for review.

---

## Final Test

A comment or docstring should survive review only if it answers at least one
important question that the code cannot answer clearly on its own:

- Why?
- Under what constraint?
- What must remain true?
- What does the caller rely on?
- What surprising behavior occurs?
- What important side effect exists?
- What would a competent maintainer otherwise misunderstand?

If it answers none of these, improve the code or delete the comment.
