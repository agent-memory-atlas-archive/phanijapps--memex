# Memex contributor guide

## Mission

Memex is a durable, team-ready memory layer for AI coding agents. Its public API
must remain agent-neutral: Codex is the first integration, while Claude Code,
Pimono, and future clients are first-class design constraints.

## Guidelines
Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.


> **These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## Engineering principles

- Target Python 3.12+ and manage dependencies, environments, commands, and
  publishing with `uv`.
- Share services and datatypes across adapters: the CLI, MCP, and any
  future API must use the same domain services and datatypes — no
  per-adapter duplicates. Keep orchestration in `application`, and I/O,
  SDKs, persistence, and agent integrations in `infrastructure`.
- Prefer small typed objects, explicit protocols, immutable value objects, and
  keyword-only public arguments. Avoid `dict[str, Any]` at boundaries when a
  model can express the contract.
- Make invalid states difficult to represent; validate untrusted data at every
  boundary and return actionable, non-sensitive errors.
- Prefer the standard library for ordinary local functionality. Use maintained,
  standards-compliant libraries for protocols such as MCP instead of writing
  protocol transports or JSON-RPC framing in this project. Every dependency
  needs a clear purpose, supported-version review, and license check.
- Never log memory contents, credentials, tokens, or other sensitive data by
  default. Treat stored memories and tool inputs as untrusted.
- Preserve backwards compatibility for documented public APIs. Version and
  document intentional breakage.
- Prefer names, types, and small functions that explain themselves. Comments
  should state a non-obvious reason, external constraint, security boundary, or
  intentional trade-off; they must be concise, accurate, and current. Do not
  narrate code, store author/date/ticket metadata, or commit commented-out code.
  Document public contracts, side effects, and errors with useful docstrings.
- Use skills when building code.

## Quality gates

Before proposing a change, run the relevant checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
```

Add focused tests for every behavior change, including failure paths and
security-relevant input validation. Keep tests deterministic and offline.

## Working agreement

- Read `docs/` and existing architecture decisions before implementation.
- Do not introduce project-specific skills, hooks, or sub-agents until a task
  has a repeatable workflow that warrants the maintenance cost.
- Dependency resolution for an explicitly requested implementation is allowed.
  Do not call user-configured services, publish packages, or modify CI secrets
  without explicit user approval.
- Keep commits focused. Do not discard or rewrite another contributor's work.
- Update documentation alongside public behavior, configuration, or security
  changes.
