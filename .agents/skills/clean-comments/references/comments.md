# Comment Rules

Detailed rules for inline comments, loaded on demand.

## Comments vs Docstrings

Use comments and docstrings for different purposes.

### Comments

Comments explain implementation reasoning that cannot be expressed clearly in code.

Good comments answer questions such as:

- Why is this implementation necessary?
- Why is the obvious implementation incorrect?
- What external constraint forces this behavior?
- What invariant must be preserved?
- What compatibility issue is being handled?
- What performance or concurrency behavior matters?
- Why must this code execute in this particular order?

Example:

```python
# GitHub can redeliver the same webhook, so this operation must remain idempotent.
persist_event(event)
```

### Docstrings

Docstrings describe the contract, responsibility, or intended use of a Python object.

Good docstrings answer questions such as:

- What responsibility does this object have?
- What behavior does the caller rely on?
- What important conditions apply to arguments or results?
- What meaningful exceptions can occur?
- What side effects occur?
- What invariants or lifecycle rules matter?
- What behavior is intentionally guaranteed?

Example:

```python
def get_user(user_id: int) -> User:
    """Return the active user, raising UserNotFound for deleted accounts."""
```

Do not use a docstring to narrate the implementation.

---

## C1: No Inappropriate Information

Comments and docstrings are not storage for project metadata.

Do not place the following in Python comments or docstrings:

- Author names
- Modification dates
- Change history
- Version history
- Ticket numbers with no technical value
- Review status
- Ownership metadata
- Commit references that merely record history

Bad:

```python
# Author: Jane Smith
# Modified: 2026-09-10
# JIRA-4812
def calculate_total(...):
    ...
```

Use Git, issue tracking, CODEOWNERS, or project documentation for metadata.

A ticket reference may remain only when it is necessary to understand an
external constraint that cannot reasonably be described without it.

Prefer describing the constraint itself.

---

## C2: Delete Obsolete Comments

A stale comment is worse than no comment.

When code changes, inspect nearby comments and docstrings during the same edit.

Delete or update documentation when:

- Behavior changed
- Parameters changed
- Return behavior changed
- Exceptions changed
- An implementation workaround was removed
- A dependency or external constraint no longer applies
- The comment refers to code that no longer exists

Never leave a comment that describes old behavior "for context."

Git preserves history.

---

## C3: No Redundant Comments

Do not repeat what the code already says.

Bad:

```python
i += 1  # Increment i.

user.save()  # Save the user.

if user.is_active:
    # Check if user is active.
    send_email(user)
```

Better:

```python
i += 1  # Account for the one-based position shown in the UI.
```

A comment should add semantic information, not translate Python into English.

---

## C4: Write Comments Well

If a comment is worth keeping, make it precise.

A good comment should be:

- Brief
- Grammatically correct
- Specific
- Located next to the code it explains
- Focused on why, constraints, or guarantees
- Written so it remains meaningful after minor refactoring

Avoid:

- Rambling explanations
- Vague statements
- Speculation
- Humor that obscures intent
- Emotional comments
- Blame
- Historical storytelling
- Large prose blocks when a design document would be more appropriate

Bad:

```python
# This is kind of weird but for some reason doing it the normal way breaks
# stuff sometimes so we do this instead.
```

Better:

```python
# Keep these queries separate because PostgreSQL chooses a sequential scan
# when the predicates are combined.
```

---

## C5: Never Commit Commented-Out Code

Delete commented-out code.

Bad:

```python
# def old_calculate_tax(income):
#     return income * 0.15
```

Do not preserve old implementations, debugging code, or alternative approaches
as comments.

Git preserves previous versions.

Exceptions are rare. A disabled code fragment may remain only when the literal
code itself is required as documentation, such as an example inside a docstring
or documentation test.

---

## C6: Comment Intent, Not Mechanics

Prefer comments that explain intent, constraints, or tradeoffs.

Bad:

```python
# Sort the users by name.
users.sort(key=lambda user: user.name)
```

Good:

```python
# Preserve deterministic ordering because the generated file is committed.
users.sort(key=lambda user: user.name)
```

Good implementation comments commonly explain:

- External API quirks
- Protocol requirements
- Data normalization
- Numerical precision
- Security constraints
- Concurrency assumptions
- Retry semantics
- Idempotency
- Performance tradeoffs
- Compatibility behavior
- Ordering guarantees
- Domain rules that are not obvious from names

---

## C7: Refactor Before Commenting

When code needs an explanatory comment, first ask whether the intent can be
expressed structurally.

Try, in order:

1. Rename variables, functions, classes, or parameters
2. Extract a function or class
3. Replace a magic value with a named constant
4. Add or improve type annotations
5. Represent state explicitly
6. Add validation or assertions for enforceable invariants
7. Simplify control flow
8. Add a comment only if important reasoning is still not evident

Bad:

```python
# Check whether this user can edit the project.
if user.role == "admin" or user.id == project.owner_id:
    ...
```

Better:

```python
if can_edit_project(user, project):
    ...
```

A comment may still be needed if the policy includes a non-obvious external rule.

---

## Comments for Algorithms

Do not narrate each algorithmic step.

Bad:

```python
# Loop through nodes.
for node in nodes:
    # Add the node's distance.
    total += node.distance
```

Use comments to explain non-obvious algorithmic choices:

```python
# Dijkstra is faster here than A* because this graph has no admissible
# heuristic for cross-region edges.
```

For complex algorithms, prefer a short explanation of:

- The invariant
- The reason for the algorithm choice
- The non-obvious optimization
- Any important complexity tradeoff

Do not reproduce textbook descriptions inside source files.

---

## Workarounds and Compatibility Comments

Workaround comments should explain:

1. The external condition
2. Why the workaround exists
3. When possible, the condition under which it can be removed

Bad:

```python
# HACK
time.sleep(1)
```

Better:

```python
# The vendor API may return 404 for up to one second after creation.
# Retry here until read-after-write consistency is guaranteed by the API.
time.sleep(1)
```

Do not include dates or ticket IDs unless they materially help identify the
external constraint.

---

## TODO and FIXME

TODO and FIXME comments are allowed only when they represent concrete, unresolved
technical work.

Good:

```python
# TODO: Replace the in-memory lock when workers move to multiple processes.
```

Bad:

```python
# TODO: Fix this later.
```

Bad:

```python
# FIXME JIRA-1234 Bob 2025-04-01
```

A useful TODO should explain what remains unresolved and, when necessary, the
condition that makes the work relevant.

Do not use TODO comments as:

- Backlogs
- Sprint planning
- Ownership tracking
- Historical records
- Ticket mirrors

Prefer the issue tracker for project management.

---

## NOTE Comments

Use `NOTE` sparingly.

A normal explanatory comment is usually better.

Prefer:

```python
# This must run before validation because validation reads the normalized value.
normalize(payload)
validate(payload)
```

Instead of:

```python
# NOTE: This must run before validation.
```

A label adds little value unless project conventions specifically use it.

---

## HACK Comments

Do not use `HACK` as a substitute for explanation.

If a workaround is necessary, explain the actual constraint.

Bad:

```python
# HACK
value = value[:-1]
```

Better:

```python
# The upstream parser includes the delimiter in the token span.
value = value[:-1]
```

---

## Warning Comments

Warnings are appropriate when misuse could cause behavior that is difficult to
infer or dangerous to change.

Examples include:

- Security boundaries
- Ordering dependencies
- Concurrency requirements
- Persistence compatibility
- Protocol compatibility
- Data migration constraints

Keep warnings factual and specific.

Bad:

```python
# DO NOT TOUCH THIS!!!
```

Better:

```python
# Preserve field order. Existing signatures are computed over this serialized form.
```

---

## No Decorative Section Comments

Avoid visual separators that compensate for oversized modules.

Bad:

```python
# =========================
# Utility Functions
# =========================
```

Prefer:

- Smaller modules
- Classes
- Functions
- Clear names

Use section comments only when the file structure genuinely benefits and
refactoring is not practical.

---

## No Closing Comments

Do not write comments such as:

```python
# end if
# end loop
# end class
```

If nesting is difficult to follow, simplify the code.

---
