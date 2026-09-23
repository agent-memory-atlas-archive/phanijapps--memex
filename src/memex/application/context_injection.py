"""Context injection: recall results rendered for the agent prompt (spec §5.4)."""

from __future__ import annotations

from collections.abc import Sequence

from memex.application.memory import Memex
from memex.domain.models import RecallResult

_MEMORY_HEADER = "=== memex MEMORY ==="
_MEMORY_FOOTER = "=== END memex MEMORY ==="
DEFAULT_INJECTION_TOP_K = 5
DEFAULT_MAX_TOKENS = 4096
# Below this BM25 rank position, hook injection stays silent (weak matches
# inject noise, not context); explicit recall is never filtered by it.
MIN_INJECTION_RANK = 3

CONSTITUTION = (
    "Memories below are yours \u2014 sessions end, these remain.",
    "Write durable facts; skip ephemera.",
    "Recall before assuming; trust what cites its source.",
)


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate (len//4+1), pinned by unit tests."""
    return len(text) // 4 + 1


def pack_to_budget[T](hits: list[T], max_tokens: int = DEFAULT_MAX_TOKENS) -> list[T]:
    """Token-budget packing: page text counts, metadata is free; a hit that
    does not fit is skipped in favor of smaller ones; the top-ranked hit is
    always returned whole."""
    if not hits:
        return []
    packed: list[T] = []
    used = 0
    for hit in hits:
        cost = estimate_tokens(getattr(hit, "snippet", "") or "")
        if packed and used + cost > max_tokens:
            continue  # skip-and-continue
        packed.append(hit)
        used += cost
    return packed


def format_context_block(result: RecallResult, *, linked: Sequence[str] = ()) -> str:
    """Render recall hits in the spec's context-window injection format.

    ``linked`` lines (rendered link-graph expansion) follow the hits, before
    the footer.
    """
    lines = [f"[memex] {line}" for line in CONSTITUTION]
    lines += [_MEMORY_HEADER, f'[Search: "{result.query}"]']
    for hit in result.hits:
        lines.append("---")
        lines.append(
            f"{hit.rank}. {hit.title} ({hit.node_type}) | "
            f"importance: {hit.importance} | updated: {hit.updated_at}"
        )
        lines.append(f"   File: {hit.file_path}")
        lines.append(f"   {hit.snippet}")
        lines.append(f"   Tags: {', '.join(hit.tags)}")
        lines.append(f"   Links: {', '.join(hit.links)}")
    lines.append("---")
    if linked:
        lines.extend(linked)
        lines.append("---")
    lines.append(_MEMORY_FOOTER)
    return "\n".join(lines)


def build_injection(
    memex: Memex,
    query: str,
    *,
    top_k: int = DEFAULT_INJECTION_TOP_K,
    max_tokens: int | None = None,
    depth: int = 1,
) -> str:
    """Recall, pack to budget, render; empty when nothing clears the floor.

    The floor: the best hit must rank within MIN_INJECTION_RANK for injection
    to fire at all \u2014 weak matches inject silence rather than noise.
    Direct hits pack first; pages linked within ``depth`` hops fill only the
    budget they leave, and the block stays as it was when they cannot fit.
    """
    from memex.application.graph_expansion import expand_links, render_expansion

    result = memex.recall(query, top_k=top_k)
    if not result.hits or result.hits[0].rank > MIN_INJECTION_RANK:
        return ""
    budget = max_tokens or DEFAULT_MAX_TOKENS
    result.hits = pack_to_budget(result.hits, budget)
    block = format_context_block(result)
    expansion = expand_links(
        memex, result.hits, depth=depth, max_tokens=budget - estimate_tokens(block)
    )
    linked = render_expansion(expansion)
    if not linked:
        return block
    expanded = format_context_block(result, linked=linked)
    return expanded if estimate_tokens(expanded) <= budget else block
