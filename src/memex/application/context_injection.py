"""Context injection: recall results rendered for the agent prompt (spec §5.4)."""

from __future__ import annotations

from memex.application.memory import Memex
from memex.domain.models import RecallResult

_MEMORY_HEADER = "=== memex MEMORY ==="
_MEMORY_FOOTER = "=== END memex MEMORY ==="
DEFAULT_INJECTION_TOP_K = 5


def format_context_block(result: RecallResult) -> str:
    """Render recall hits in the spec's context-window injection format."""
    lines = [_MEMORY_HEADER, f'[Search: "{result.query}"]']
    for hit in result.hits:
        lines.append("---")
        lines.append(
            f"{hit.rank}. {hit.title} ({hit.node_type}) | "
            f"importance: {hit.importance} | updated: {hit.updated}"
        )
        lines.append(f"   File: {hit.file_path}")
        lines.append(f"   {hit.snippet}")
        lines.append(f"   Tags: {', '.join(hit.tags)}")
        lines.append(f"   Links: {', '.join(hit.links)}")
    lines.append("---")
    lines.append(_MEMORY_FOOTER)
    return "\n".join(lines)


def build_injection(memex: Memex, query: str, *, top_k: int = DEFAULT_INJECTION_TOP_K) -> str:
    """Recall and render; empty string when nothing relevant is stored."""
    result = memex.recall(query, top_k=top_k)
    if not result.hits:
        return ""
    return format_context_block(result)
