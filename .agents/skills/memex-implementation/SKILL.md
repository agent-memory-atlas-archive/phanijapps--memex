---
name: memex-implementation
description: Implement or review Memex features when translating product specifications into the Memex Python package and CLI.
---

# Memex implementation

Memex is the product, distribution, package namespace, CLI name, configuration
prefix, and local data directory. A source specification may retain an earlier
working title; translate its behavior into `memex`, do not expose that working
title as a public API.

Keep the filesystem Markdown wiki as the source of truth. SQLite is a
rebuildable local search index only. Use the standard library for required
features, validate all filesystem and archive inputs, and keep public APIs
typed and keyword-only where optional arguments are involved.

Before completing a feature, add or update behavior-focused tests and run Ruff,
strict mypy, and pytest. Avoid project skills, hooks, and agents unless they
address a repeated workflow or the user explicitly requests them.
