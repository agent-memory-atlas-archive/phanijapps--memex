# Docstring Rules

Detailed rules for docstrings, loaded on demand.

## Docstring Rules

### D1: Document Contracts, Not Syntax

Do not mechanically repeat:

- Function names
- Parameter names
- Type annotations
- Return annotations
- Obvious field names
- Obvious exceptions
- Implementation steps

Bad:

```python
def get_user(user_id: int) -> User:
    """
    Get a user.

    Args:
        user_id: The user ID.

    Returns:
        A User.
    """
```

Better:

```python
def get_user(user_id: int) -> User:
    """Return the active user, raising UserNotFound for deleted accounts."""
```

Document information the signature cannot express.

---

## Modules

A module docstring is useful when the module has a non-obvious purpose, important
assumptions, public usage rules, or architectural responsibility.

Add a module docstring when it helps explain:

- The module's responsibility
- Important lifecycle behavior
- External constraints
- Public entry points
- Significant side effects
- Architectural boundaries

Do not add a module docstring that only restates the filename.

Bad:

```python
"""User utilities."""
```

Useful:

```python
"""Translate identity-provider claims into application authorization roles.

This module performs no network I/O. Callers must supply already-verified claims.
"""
```

Do not generate module docstrings solely to satisfy documentation coverage metrics.

---

## Classes

### Public Classes

Document the class when callers need to understand its responsibility, lifecycle,
invariants, or usage.

A useful class docstring may explain:

- Primary responsibility
- Important invariants
- Lifecycle
- Thread-safety or concurrency behavior
- Resource ownership
- Mutation behavior
- Usage constraints

Bad:

```python
class UserService:
    """Service for users."""
```

Better:

```python
class UserService:
    """Coordinate user persistence and identity-provider synchronization.

    Instances are stateless and may be reused across requests.
    """
```

Do not document every attribute when the type, name, and initialization already
make it obvious.

### Internal or Private Classes

Do not require docstrings by default.

Add one only when responsibility, invariants, lifecycle, or behavior are not
obvious from the code.

---

## Functions

### Public Functions

Document behavior callers need to know.

Include only relevant information such as:

- Non-obvious semantics
- Preconditions
- Return guarantees
- Significant exceptions
- Side effects
- Mutation
- Ordering guarantees
- Units
- Blocking or I/O behavior
- Security-sensitive behavior

Do not force verbose `Args`, `Returns`, or `Raises` sections when one sentence
communicates the contract better.

### Private Functions

Private helpers do not need docstrings merely because they exist.

Prefer:

- Clear names
- Narrow responsibilities
- Type annotations

Add a docstring only when the helper has behavior or constraints that remain
non-obvious.

---

## Methods

### Public Methods

Document behavior specific to the method.

Do not repeat the class responsibility.

Bad:

```python
class Cache:
    """Store cached values."""

    def get(self, key: str) -> bytes | None:
        """Get a value from the cache."""
```

Better:

```python
class Cache:
    """Store cached values."""

    def get(self, key: str) -> bytes | None:
        """Return the value without extending its expiration time."""
```

If the method is completely obvious from its name, signature, class context,
and behavior, a docstring may be unnecessary unless project conventions
explicitly require one.

---

## `__init__`

Do not repeat the class docstring in `__init__`.

Avoid:

```python
class Worker:
    """Process jobs from a queue."""

    def __init__(self, queue: Queue, retries: int):
        """Initialize a worker with a queue and retry count."""
```

The constructor should have its own docstring only when initialization has
important behavior not covered by the class documentation, such as:

- Acquiring resources
- Starting background work
- Validating invariants
- Registering callbacks
- Performing I/O
- Ownership or cleanup requirements

---

## Properties

Document a property when its semantic meaning, units, cost, mutability, or
constraints are not obvious.

Useful:

```python
@property
def age(self) -> int:
    """Age in completed UTC years."""
```

Unnecessary:

```python
@property
def name(self) -> str:
    """Return the name."""
```

---

## Abstract Methods

Abstract methods should document the contract implementations must satisfy.

Document relevant requirements such as:

- Input expectations
- Required side effects
- Return guarantees
- Error behavior
- Idempotency
- Ordering
- Ownership
- Whether implementations may block

Example:

```python
class EventStore(ABC):
    @abstractmethod
    def append(self, event: Event) -> None:
        """Persist `event` exactly once for a given event ID."""
```

The implementation should not duplicate the abstract method's docstring unless
it changes or strengthens the contract.

---

## Overrides

Do not copy the parent docstring into an override.

If behavior is unchanged, rely on the inherited contract.

Add documentation only when the override:

- Changes behavior
- Adds constraints
- Changes side effects
- Strengthens guarantees
- Intentionally narrows inherited behavior

If inherited documentation becomes incorrect, that is a design problem that
must be resolved.

---

## Magic Methods

Do not add obvious docstrings to methods such as:

- `__str__`
- `__repr__`
- `__len__`
- `__iter__`
- `__eq__`

Add documentation only when semantics are surprising or materially different
from normal expectations.

Bad:

```python
def __len__(self) -> int:
    """Return the length."""
```

Potentially useful:

```python
def __len__(self) -> int:
    """Return the number of materialized records, excluding pending writes."""
```

---

## Dataclasses

Do not turn a dataclass docstring into a list of its fields.

Bad:

```python
@dataclass
class Job:
    """A job.

    id: The job ID.
    name: The job name.
    status: The job status.
    """
```

Document domain meaning or invariants instead:

```python
@dataclass
class Job:
    """A schedulable unit of work.

    A completed job is immutable and may not transition back to a running state.
    """
```

Field-level comments are appropriate only when names and types cannot communicate
important semantics, such as units, encoding, or domain restrictions.

---

## Enums

Do not explain obvious enum members.

Bad:

```python
class Status(Enum):
    ACTIVE = "active"  # Active status.
    INACTIVE = "inactive"  # Inactive status.
```

Document enum semantics when domain meaning is not evident, especially when
values have lifecycle, persistence, protocol, or compatibility implications.

---

## Exceptions

Do not document every exception visible in the implementation.

Document exceptions that are part of the caller-facing contract.

Bad:

```python
def parse(data: str) -> Item:
    """Parse data.

    Raises:
        ValueError: If `int()` raises ValueError.
    """
```

Useful:

```python
def parse(data: str) -> Item:
    """Parse an item, raising InvalidItem when the payload violates the schema."""
```

---

## Side Effects

Document significant side effects that callers would not reasonably infer from
the function name or type signature.

Examples:

- Network requests
- Disk writes
- Database transactions
- Mutating arguments
- Global state changes
- Process creation
- Locks
- Background tasks
- Cache invalidation
- External messages

Do not document obvious side effects already explicit in the API name.

---

## No Type Duplication

Do not repeat type information already expressed by annotations.

Bad:

```python
def load(path: str) -> bytes:
    """Load data.

    Args:
        path: A string containing the path.

    Returns:
        Bytes containing the data.
    """
```

Document semantic information instead:

```python
def load(path: str) -> bytes:
    """Load the file without decoding its contents."""
```

---

## No Fake Documentation Coverage

Do not generate meaningless docstrings simply to satisfy lint or documentation
metrics.

Bad:

```python
def close(self) -> None:
    """Close."""
```

If project policy requires documentation for every public symbol, write the
smallest meaningful contract.

If there is no meaningful information beyond the name and signature, prefer
improving the lint configuration rather than adding noise when project
constraints allow it.

---

## Preserve Valuable Existing Comments

Do not aggressively remove comments just because you understand the code.

Before deleting a comment, ask whether it records:

- A non-obvious design decision
- An external system constraint
- A compatibility requirement
- A security rule
- A concurrency assumption
- A protocol guarantee
- A performance tradeoff
- A domain invariant
- A reason an obvious alternative is incorrect

If so, preserve it or rewrite it more clearly.

---

---

## Method Documentation

Full rules for documenting methods, beyond "document contracts not syntax."

### The Call-Sufficiency Test

A method docstring must give enough information to write a call correctly
without reading the method body (the Google pyguide's own standard). Anything
that fails this test is under-documented; anything beyond it is narration.

The happy path is the signature. The contract lives at the boundaries:
None/empty behavior, failure modes, ordering, cost, idempotency, mutation,
thread-safety, and what the method deliberately does NOT do.

### pyguide Style Done Right

Google pyguide sections (`Args` / `Returns` / `Raises`) are the house format
for public APIs — rendered by Sphinx `napoleon`, enforced by `pydocstyle` /
`pydoclint`, uniform across a team. The style's bad reputation comes from
skeleton worship: filling sections with name-restating filler, which the
guide itself prohibits.

Sections carry only what the signature cannot express. Every line must be
behavior: constraints, units, defaults-behavior, side effects, semantics.

Bad (skeleton worship — prohibited):

```python
def retrieve(self, query: str, top_k: int = 10) -> RecallResult:
    """Retrieves results.

    Args:
        query: The query string.
        top_k: The top k.

    Returns:
        A RecallResult.
    """
```

Good (call-sufficient):

```python
def retrieve(self, query: str, *, top_k: int = 10,
             node_type: str | None = None,
             include_expired: bool = False) -> RecallResult:
    """Searches the memory index for nodes matching the query.

    The query is reduced to alphanumeric tokens joined by OR, so untrusted
    input never reaches the FTS5 MATCH parser. Hits are ordered by ascending
    BM25 score - lower is better, per SQLite FTS5. Nodes past ``expires_at``
    or ``valid_to`` are invisible unless the caller opts in.

    Args:
        query: Free-text terms; must contain one alphanumeric token.
        top_k: Maximum hits, in [1, 100]; defaults to bm25.default_top_k.
        node_type: Restrict hits to one type, e.g. "preference".
        include_expired: Also return soft-forgotten and decayed nodes.

    Returns:
        RecallResult with 1-based ranks, best first. Empty hits is a
        normal result, not an error.

    Raises:
        ValueError: Query has no searchable terms, or top_k outside
            [1, 100].
    """
```

Rules of thumb:

- Types live in annotations, never repeated in `Args` descriptions.
- A parameter gets an `Args` entry only when it carries behavior beyond its
  name and type: constraints, units, defaults-behavior, interactions.
- `Raises` lists only caller-actionable exceptions.
- Side effects are mandatory documentation, not garnish.

### The Style Ladder

Escalate form only as the contract grows facets:

| Contract complexity | Form |
| --- | --- |
| One facet, obvious from name + types | No docstring |
| One facet, non-obvious | One-liner |
| 2-3 facets | Summary line + short details paragraph |
| Public API: constrained params, multiple raises, side effects | pyguide sections, examples first |

Jumping straight to sections for a two-arg helper is the boilerplate smell;
staying at a one-liner for a multi-facet public API is an undocumented
contract.

### Examples Beat Prose

A runnable example is documentation that cannot silently rot — CI executes
it. Prefer doctest form for tricky behavior:

```python
def slugify(text: str) -> str:
    """Normalize free text to a kebab-case slug.

    >>> slugify("Hello, World!")
    'hello-world'
    >>> slugify("???")
    ''
    """
```

Doctests are optional per project policy; when used, run them with
`pytest --doctest-modules` or do not promise them.

### Negative Space Is Contract

The most professional sentence in a docstring is often about what the method
does NOT do: "no I/O", "does not extend expiration", "no locking - callers
own thread safety", "never retries". State it explicitly.

### Class Invariants Live Once

Put invariants and the shared model in the class (or module) docstring so
fifteen methods do not each re-explain it. Method docstrings cover only the
delta from the class contract.

### Public/Private Split

- Public API surface (facades, protocols, exported classes): pyguide
  sections with real content, linter-enforced.
- Internals and private helpers: terse one-liners or nothing, per the
  ladder. Do not pay the section tax where there is nothing to say.

## Wire-Facing Descriptions Live in a Registry

When a docstring would double as text published to an external consumer
(MCP tool descriptions, CLI help), split the audiences instead of
compromising the format:

- Source docstrings stay pyguide — they are maintainer documentation.
- The consumer-facing text lives in a dedicated registry (e.g.
  `tool_descriptions.py`) written for that audience: when to use,
  constraints, output shape, error contract.

Register from the registry so the two never share text, and pin both
with tests: registry keys match the tool set, and wire text stays
call-sufficient and self-contained — consumer hosts may not render
schemas, so constraints restated in wire text are deliberate redundancy,
not duplication to remove.
