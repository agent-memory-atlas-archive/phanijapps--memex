"""Secret scrubbing at the write boundary: typed markers replace matched
credential patterns before anything is stored. Log calls record categories
only, never matched text."""

from __future__ import annotations

import re

# Anchored patterns: kind -> regex. Anchors keep ordinary prose (hashes,
# base64-looking fragments) untouched.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}")),
    ("openai_legacy_key", re.compile(r"sk-[A-Za-z0-9]{20,}(?![A-Za-z0-9_-])")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("gitlab_token", re.compile(r"glpat-[A-Za-z0-9_-]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("aws_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")),
    ("db_url", re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s\"']+")),
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    ),
)


def scrub(text: str) -> tuple[str, list[str]]:
    """Redact credential patterns; returns (clean_text, matched_kinds)."""
    kinds: list[str] = []
    clean = text
    for kind, pattern in _PATTERNS:
        if pattern.search(clean):
            kinds.append(kind)
            clean = pattern.sub(f"[REDACTED:{kind}]", clean)
    return clean, kinds
