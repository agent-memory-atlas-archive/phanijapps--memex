"""Kebab-case slug derivation for wiki page filenames."""

from __future__ import annotations

import hashlib
import re

MAX_SLUG_LENGTH = 64

_NON_ALNUM = re.compile(r"[^a-z0-9-]+")
_HYPHEN_RUNS = re.compile(r"-{2,}")


def slugify(text: str) -> str:
    """Convert free text to a kebab-case slug.

    Lowercase, non-alphanumerics become hyphens, runs collapse, edges trim,
    and the result truncates to 64 characters. Returns an empty string when
    nothing survives; callers decide the fallback.
    """
    slug = text.lower()
    slug = _NON_ALNUM.sub("-", slug)
    slug = _HYPHEN_RUNS.sub("-", slug)
    slug = slug.strip("-")
    return slug[:MAX_SLUG_LENGTH]


def sha1_slug(text: str, length: int = 12) -> str:
    """Derive a deterministic slug from the SHA-1 of ``text``.

    SHA-1 is fine here: slugs are identifiers, not a security boundary
    (``usedforsecurity=False`` marks the intent for auditors and linters).
    """
    digest = hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()
    return digest[:length]


def derive_slug(title: str, *, algo: str = "kebab") -> str:
    """Derive a slug from a title using the configured algorithm."""
    if algo == "sha1":
        return sha1_slug(title)
    return slugify(title)


def unique_slug(base: str, taken: set[str]) -> str:
    """Return ``base`` or ``base-2``, ``base-3``... until it is not taken."""
    if base not in taken:
        return base
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"
