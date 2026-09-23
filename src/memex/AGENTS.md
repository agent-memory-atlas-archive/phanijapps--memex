# Package guidance

Applies to `src/memex/`. Inherits the root `AGENTS.md`. Scope-specific deltas only.

- `cli.py` and `mcp_server.py` are adapters over the same `Memex` service and the
  same domain datatypes. A new capability lands in `application/`; both adapters
  expose it, or neither does. `domain/operations.py` is the shared operation surface.
- `__init__.py` is the documented public API. Adding, renaming, or removing an
  `__all__` entry is a compatibility decision — version intentional breakage, and
  keep `__version__` in step.
