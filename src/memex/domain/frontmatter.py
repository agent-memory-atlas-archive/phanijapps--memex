"""Strict codec for the documented YAML front-matter subset.

Wiki pages carry front matter in exactly one shape (spec §6.1): quoted
strings, plain integers/floats, ``null``, and flow-style lists whose items are
quoted strings or inline mappings of quoted strings (OKF typed links).
PyYAML is deliberately not required; this parser validates strictly and raises
:class:`FrontMatterError` on anything outside the subset, because we own the
format and silent tolerance would corrupt the index.

The subset stays line-oriented on purpose: one key per line, collections
inline. A YAML block sequence would be valid YAML and unreadable here, so
typed links are written ``[{target: "slug", rel: "relates-to"}]`` — valid
YAML that an OKF parser reads and this codec can own.
"""

from __future__ import annotations

import re
from typing import Any

from memex.domain.errors import FrontMatterError

_KEY_VALUE = re.compile(r"^([a-z_]+):\s*(.*?)\s*$")
_FLOW_LIST = re.compile(r"^\[(.*)\]$")
_FLOW_MAP = re.compile(r"^\{(.*)\}$")
_MAP_KEY = re.compile(r"^[a-z_]+$")


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


def _split_items(inner: str, key: str) -> list[str]:
    """Split a flow collection on top-level commas, respecting quotes and braces."""
    items: list[str] = []
    current: list[str] = []
    depth = 0
    in_quotes = False
    escaped = False
    for char in inner:
        if in_quotes:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_quotes = False
            continue
        if char == '"':
            in_quotes = True
            current.append(char)
        elif char == "{":
            depth += 1
            current.append(char)
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise FrontMatterError(f"front matter field '{key}': unbalanced '}}'")
            current.append(char)
        elif char == "," and depth == 0:
            items.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if in_quotes:
        raise FrontMatterError(f"front matter field '{key}': unterminated quoted string")
    if depth:
        raise FrontMatterError(f"front matter field '{key}': unbalanced '{{'")
    items.append("".join(current).strip())
    if any(not item for item in items):
        raise FrontMatterError(f"front matter field '{key}': empty collection item")
    return items


def _parse_mapping(raw: str, key: str) -> dict[str, str]:
    """Parse one inline mapping item, e.g. ``{target: "a", rel: "b"}``."""
    match = _FLOW_MAP.match(raw)
    if match is None:
        raise FrontMatterError(f"front matter field '{key}': expected inline mapping, got {raw!r}")
    inner = match.group(1).strip()
    if not inner:
        raise FrontMatterError(f"front matter field '{key}': mapping item is empty")
    entry: dict[str, str] = {}
    for piece in _split_items(inner, key):
        name, separator, value = piece.partition(":")
        name = name.strip()
        value = value.strip()
        if not separator or not _MAP_KEY.match(name):
            raise FrontMatterError(f"front matter field '{key}': malformed mapping entry {piece!r}")
        if name in entry:
            raise FrontMatterError(f"front matter field '{key}': duplicate mapping key {name!r}")
        if not (value.startswith('"') and value.endswith('"') and len(value) >= 2):
            raise FrontMatterError(
                f"front matter field '{key}': mapping value for {name!r} must be quoted"
            )
        entry[name] = _unquote(value, key)
    return entry


def _parse_list(raw: str, key: str) -> list[str | dict[str, str]]:
    match = _FLOW_LIST.match(raw)
    if match is None:
        raise FrontMatterError(f"front matter field '{key}': expected flow list, got {raw!r}")
    inner = match.group(1).strip()
    if not inner:
        return []
    items: list[str | dict[str, str]] = []
    for piece in _split_items(inner, key):
        if piece.startswith("{"):
            items.append(_parse_mapping(piece, key))
        elif piece.startswith('"') and piece.endswith('"') and len(piece) >= 2:
            items.append(_unquote(piece, key))
        else:
            raise FrontMatterError(
                f"front matter field '{key}': list items must be quoted or inline mappings"
            )
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


def _render_item(item: Any, key: str) -> str:
    """Render one flow-list item: a quoted string or an inline mapping."""
    if isinstance(item, str):
        return _quote(item)
    if isinstance(item, dict):
        if not item:
            raise FrontMatterError(f"field '{key}': mapping items must not be empty")
        parts: list[str] = []
        for name, value in item.items():
            if not isinstance(name, str) or not _MAP_KEY.match(name):
                raise FrontMatterError(f"field '{key}': invalid mapping key {name!r}")
            if not isinstance(value, str):
                raise FrontMatterError(f"field '{key}': mapping values must be strings")
            parts.append(f"{name}: {_quote(value)}")
        return "{" + ", ".join(parts) + "}"
    raise FrontMatterError(f"field '{key}': unsupported list item {type(item).__name__}")


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
            items = ", ".join(_render_item(item, key) for item in value)
            lines.append(f"{key}: [{items}]")
        else:
            raise FrontMatterError(f"field '{key}': unsupported type {type(value).__name__}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)
