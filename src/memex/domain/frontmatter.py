"""Strict codec for the documented YAML front-matter subset.

Wiki pages carry front matter in exactly one shape (spec §6.1): quoted
strings, plain integers/floats, ``null``, and flow-style lists of quoted
strings. PyYAML is deliberately not required; this parser validates strictly
and raises :class:`FrontMatterError` on anything outside the subset, because
we own the format and silent tolerance would corrupt the index.
"""

from __future__ import annotations

import re
from typing import Any

from memex.domain.errors import FrontMatterError

_KEY_VALUE = re.compile(r"^([a-z_]+):\s*(.*?)\s*$")
_FLOW_LIST = re.compile(r"^\[(.*)\]$")


def _parse_scalar(raw: str, key: str) -> Any:
    if raw == "null":
        return None
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return _unquote(raw, key)
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    raise FrontMatterError(f"front matter field '{key}': unsupported value {raw!r}")


def _unquote(raw: str, key: str) -> str:
    inner = raw[1:-1]
    out: list[str] = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\":
            if i + 1 >= len(inner):
                raise FrontMatterError(f"front matter field '{key}': dangling escape")
            nxt = inner[i + 1]
            if nxt not in ('"', "\\"):
                raise FrontMatterError(f"front matter field '{key}': unknown escape \\{nxt}")
            out.append(nxt)
            i += 2
        elif ch == '"':
            raise FrontMatterError(f"front matter field '{key}': unescaped quote")
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _parse_list(raw: str, key: str) -> list[str]:
    match = _FLOW_LIST.match(raw)
    if match is None:
        raise FrontMatterError(f"front matter field '{key}': expected flow list, got {raw!r}")
    inner = match.group(1).strip()
    if not inner:
        return []
    items: list[str] = []
    for piece in inner.split(","):
        piece = piece.strip()
        if not (piece.startswith('"') and piece.endswith('"') and len(piece) >= 2):
            raise FrontMatterError(f"front matter field '{key}': list items must be quoted")
        items.append(_unquote(piece, key))
    return items


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Split a wiki page into (front matter dict, Markdown body).

    Raises :class:`FrontMatterError` when delimiters are missing, lines are
    malformed, or a key is outside the documented set.
    """
    if not text.startswith("---\n"):
        raise FrontMatterError("front matter delimiter '---' not found at start of file")
    end = text.find("\n---", 4)
    if end == -1:
        raise FrontMatterError("closing '---' delimiter not found")
    block = text[4:end]
    body = text[end + 4 :].lstrip("\n")

    data: dict[str, Any] = {}
    for line in block.split("\n"):
        if not line.strip():
            continue
        match = _KEY_VALUE.match(line)
        if match is None:
            raise FrontMatterError(f"malformed front matter line: {line!r}")
        key, raw = match.groups()
        if key in data:
            raise FrontMatterError(f"duplicate front matter key: {key!r}")
        if raw.startswith("["):
            data[key] = _parse_list(raw, key)
        else:
            data[key] = _parse_scalar(raw, key)
    return data, body


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def serialize_front_matter(data: dict[str, Any], body: str) -> str:
    """Render a wiki page from an ordered mapping and Markdown body."""
    lines = ["---"]
    for key, value in data.items():
        if value is None:
            lines.append(f"{key}: null")
        elif isinstance(value, bool):
            raise FrontMatterError(f"field '{key}': booleans are not part of the format")
        elif isinstance(value, int | float):
            lines.append(f"{key}: {value}")
        elif isinstance(value, str):
            lines.append(f"{key}: {_quote(value)}")
        elif isinstance(value, list):
            items = ", ".join(_quote(item) for item in value)
            lines.append(f"{key}: [{items}]")
        else:
            raise FrontMatterError(f"field '{key}': unsupported type {type(value).__name__}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)
