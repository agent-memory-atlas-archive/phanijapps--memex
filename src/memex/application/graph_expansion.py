"""Link-graph expansion: neighbours of recall hits, packed after the hits.

OKF's ``read_concept(depth)``: search returns a cheap hit list; expansion
walks the typed link graph from those hits, level by level, alphabetical
within a level, and renders each neighbour as a short block (title, path,
description or snippet) under a token budget with a trailing omitted count.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from memex.application.context_injection import estimate_tokens
from memex.application.memory import Memex
from memex.domain.models import RecallHit

DEFAULT_EXPANSION_DEPTH = 1
_SNIPPET_CHARS = 200

_Identity = tuple[str, str | None, str]
_Hops = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ExpansionEntry:
    """One neighbour reached from a seed hit; ``hops`` is the (rel, slug) route."""

    slug: str
    scope: str
    project_id: str | None
    seed: str
    hops: _Hops
    block: str
    tokens: int

    @property
    def depth(self) -> int:
        return len(self.hops)


@dataclass(frozen=True, slots=True)
class Expansion:
    """Entries that fit the budget, and how many reachable pages did not."""

    entries: list[ExpansionEntry]
    omitted: int


def omitted_marker(count: int) -> str:
    return f"[memex] linked pages omitted (token budget): {count}"


def render_expansion(expansion: Expansion) -> list[str]:
    """Block lines in BFS order, then the omitted marker when anything was cut."""
    lines = [line for entry in expansion.entries for line in entry.block.splitlines()]
    if expansion.omitted:
        lines.append(omitted_marker(expansion.omitted))
    return lines


def expand_links(
    memex: Memex,
    seeds: Sequence[RecallHit],
    *,
    depth: int = DEFAULT_EXPANSION_DEPTH,
    max_tokens: int,
    scope: str = "global",
    project_id: str | None = None,
) -> Expansion:
    """Neighbours of ``seeds`` within ``depth`` hops, each page once, seeds excluded.

    Order is deterministic: level by level, alphabetical slug within a level;
    the first discovery of a page fixes its route. ``scope`` and ``project_id``
    are the recall's own, so only pages that recall would return are
    reachable. ``max_tokens`` bounds the rendered blocks plus the omitted
    marker.
    """
    if depth < 0:
        raise ValueError("depth must be zero or more")
    visited = {_identity(seed.scope, seed.project_id, seed.slug) for seed in seeds}
    frontier: list[tuple[str, _Identity, _Hops]] = [
        (seed.slug, _identity(seed.scope, seed.project_id, seed.slug), ()) for seed in seeds
    ]
    candidates: list[ExpansionEntry] = []
    for _level in range(depth):
        discovered: dict[_Identity, ExpansionEntry] = {}
        for seed, source, hops in frontier:
            for row in memex.retriever.neighbours(
                *source, scope=scope, project_id=project_id, body_chars=_SNIPPET_CHARS * 5
            ):
                found = _identity(str(row["scope"]), str(row["project_id"]), str(row["slug"]))
                if found in visited or found in discovered:
                    continue
                discovered[found] = _entry(row, seed, (*hops, (str(row["rel"]), found[2])))
        level = sorted(
            discovered.values(), key=lambda entry: (entry.slug, entry.scope, entry.project_id or "")
        )
        if not level:
            break
        visited.update(discovered)
        candidates.extend(level)
        frontier = [
            (entry.seed, _identity(entry.scope, entry.project_id, entry.slug), entry.hops)
            for entry in level
        ]
    return _pack(candidates, max_tokens)


def _identity(scope: str, project_id: str | None, slug: str) -> _Identity:
    return scope, project_id or None, slug


def _entry(row: sqlite3.Row, seed: str, hops: _Hops) -> ExpansionEntry:
    summary = _one_line(str(row["description"] or "") or str(row["body"]))[:_SNIPPET_CHARS]
    route = seed + "".join(f" -{rel}-> {slug}" for rel, slug in hops)
    lines = [
        f"+ {_one_line(str(row['title']))} ({row['node_type']})"
        f" | depth: {len(hops)} | via: {route}",
        f"   File: {_one_line(str(row['file_path']))}",
    ]
    if summary:
        lines.append(f"   {summary}")
    block = "\n".join(lines)
    return ExpansionEntry(
        slug=str(row["slug"]),
        scope=str(row["scope"]),
        project_id=str(row["project_id"]) or None,
        seed=seed,
        hops=hops,
        block=block,
        tokens=estimate_tokens(block),
    )


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _pack(candidates: list[ExpansionEntry], max_tokens: int) -> Expansion:
    # Per-entry estimates sum to at least the estimate of the joined text, so a
    # fitting total needs no marker; otherwise reserve the marker up front so a
    # cut never pushes the section over budget.
    if sum(entry.tokens for entry in candidates) <= max_tokens:
        return Expansion(entries=list(candidates), omitted=0)
    budget = max_tokens - estimate_tokens(omitted_marker(len(candidates)))
    kept: list[ExpansionEntry] = []
    used = 0
    for entry in candidates:
        if used + entry.tokens > budget:
            break
        kept.append(entry)
        used += entry.tokens
    return Expansion(entries=kept, omitted=len(candidates) - len(kept))
