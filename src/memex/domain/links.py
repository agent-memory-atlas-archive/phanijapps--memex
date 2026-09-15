"""Pure parsing of ``[[wiki-link]]`` references from Markdown bodies."""

from __future__ import annotations

import re

from memex.domain.slugs import slugify

_LINK = re.compile(r"\[\[([^\[\]]+)\]\]")


def parse_links(body: str) -> list[str]:
    """Extract unique, order-preserving link slugs from Markdown body text.

    ``[[Wiki Link]]`` and ``[[wiki-link]]`` normalize to the same kebab-case
    slug; everything is matched case-insensitively per spec §6.1.
    """
    seen: dict[str, None] = {}
    for match in _LINK.finditer(body):
        slug = slugify(match.group(1))
        if slug:
            seen.setdefault(slug, None)
    return list(seen)
