# Docstring Templates

Copy-paste starting points. Replace every placeholder with real contract
content; delete any element that carries no information beyond the signature.

## One-liner (single non-obvious facet)

```python
def read(self, slug: str) -> WikiNode | None:
    """Parse one wiki page; None when the slug does not exist."""
```

## Summary + details (2-3 facets)

```python
def read(self, slug: str) -> WikiNode | None:
    """Parse one wiki page; None when the slug does not exist.

    Pure - never mutates the file or bumps access counts. Raises
    WikiStoreError on a malformed page: hand-edits are untrusted input.
    """
```

## Public API (pyguide sections)

```python
def operation(self, param: str, *, option: int = 10) -> Result:
    """One imperative sentence stating what the method does.

    One short paragraph for the non-obvious model: ordering, filtering,
    sanitization, expiry semantics - whatever the caller cannot infer.

    Args:
        param: Constraint or unit the name cannot carry, e.g. "free-text
            terms; must contain one alphanumeric token".
        option: Bounds and default-behavior, e.g. "in [1, 100]; defaults
            to the configured bm25.default_top_k".

    Returns:
        Shape and semantics, e.g. "hits ranked 1-based, best first; empty
        is a normal result, not an error".

    Raises:
        ValueError: Caller-actionable failure and its trigger.
    """
```

## Doctest example (tricky behavior)

```python
def slugify(text: str) -> str:
    """Normalize free text to a kebab-case slug.

    >>> slugify("Hello, World!")
    'hello-world'
    >>> slugify("???")
    ''
    """
```

## Class carrying invariants (methods document only the delta)

```python
class IndexManager:
    """Owns the SQLite secondary index.

    The index is a rebuildable mirror of the wiki files: any row may be
    regenerated from a wiki scan, so no caller may treat it as durable
    state.
    """
```
