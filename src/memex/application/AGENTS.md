# Application guidance

Applies to `src/memex/application/`. Inherits the root `AGENTS.md`. Scope-specific deltas only.

- `memory.py` owns the `Memex` facade every adapter calls. Orchestration lives
  here; storage and I/O stay in `infrastructure/`.
- Swappable collaborators (anything LLM- or backend-shaped) go through a
  `Protocol` in `ports.py`. The fixed filesystem and index machinery is imported
  directly — follow that split rather than converting either side.
- Stored memory is untrusted evidence. Validate at this boundary; never log
  memory contents or tool inputs.
