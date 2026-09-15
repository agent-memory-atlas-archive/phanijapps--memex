"""Parsers from harness-native session files to transcript turns.

Each parser is tolerant: conversational messages map to TurnStreamEntry,
unrecognized lines are skipped, and unparseable timestamps become ""
(TurnStreamEntry's "unknown" marker). Codex's rollout shape is the least
stable across versions; unknown entry types never raise.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from memex.domain.models import TurnStreamEntry

HARNESSES: tuple[str, ...] = ("pi", "claude", "codex")

_SESSION_ID_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def normalize_ts(value: object) -> str:
    """Best-effort ISO8601-UTC normalization; "" when unknown."""
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(float(value) / 1000, tz=UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OSError, OverflowError):
        pass
    return ""


def suggest_session_id(harness: str, path: Path) -> str:
    """Derive a charset-safe session id from the session file name."""
    raw = f"{harness}-{path.stem}"
    cleaned = _SESSION_ID_CHARS.sub("-", raw).strip("-.")
    return cleaned[:80] or f"{harness}-session"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def _blocks_text(content: object) -> str:
    """Join text from a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(part for part in parts if isinstance(part, str))
    return ""


def _opt_str(turn: dict[str, object], key: str) -> str | None:
    value = turn.get(key)
    return value if isinstance(value, str) and value else None


def _finalize(turns: list[dict[str, object]]) -> list[TurnStreamEntry]:
    entries: list[TurnStreamEntry] = []
    for number, turn in enumerate(turns, start=1):
        content = str(turn.get("content") or "")
        if not content.strip():
            continue
        entries.append(
            TurnStreamEntry(
                role=str(turn["role"]),
                content=content,
                turn=number,
                ts=str(turn.get("ts") or ""),
                tool_name=_opt_str(turn, "tool_name"),
                result=_opt_str(turn, "result"),
                query=_opt_str(turn, "query"),
            )
        )
    return entries


def parse_pi_session(path: Path) -> list[TurnStreamEntry]:
    """Parse a pi session JSONL (format v3) into turns.

    Message order follows file order, which is append order along the
    active branch. user/assistant text becomes conversation; toolResult
    and bashExecution become tool turns.
    """
    turns: list[dict[str, object]] = []
    for entry in _read_jsonl(path):
        if entry.get("type") != "message":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        ts = normalize_ts(message.get("timestamp"))
        if role == "user":
            turns.append(
                {"role": "user", "content": _blocks_text(message.get("content")), "ts": ts}
            )
        elif role == "assistant":
            turns.append(
                {"role": "agent", "content": _blocks_text(message.get("content")), "ts": ts}
            )
        elif role == "toolResult":
            turns.append(
                {
                    "role": "tool",
                    "content": str(message.get("toolName") or "tool"),
                    "tool_name": str(message.get("toolName") or "tool"),
                    "result": _blocks_text(message.get("content")),
                    "ts": ts,
                }
            )
        elif role == "bashExecution":
            command = str(message.get("command") or "")
            turns.append(
                {
                    "role": "tool",
                    "content": command,
                    "tool_name": "bash",
                    "result": str(message.get("output") or ""),
                    "query": command,
                    "ts": ts,
                }
            )
    return _finalize(turns)


def parse_claude_transcript(path: Path) -> list[TurnStreamEntry]:
    """Parse a Claude Code transcript JSONL into turns.

    Assistant tool_use blocks become tool turns; user tool_result blocks
    become tool results. Non-conversational lines are skipped.
    """
    turns: list[dict[str, object]] = []
    for entry in _read_jsonl(path):
        entry_type = entry.get("type")
        if entry_type not in ("user", "assistant"):
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        ts = normalize_ts(entry.get("timestamp") or message.get("timestamp"))
        content = message.get("content")
        if entry_type == "assistant":
            blocks = content if isinstance(content, list) else []
            text = _blocks_text(blocks)
            if text.strip():
                turns.append({"role": "agent", "content": text, "ts": ts})
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                turns.append(
                    {
                        "role": "tool",
                        "content": str(block.get("name") or "tool"),
                        "tool_name": str(block.get("name") or "tool"),
                        "query": json.dumps(block.get("input", {}), default=str),
                        "ts": ts,
                    }
                )
        else:
            blocks = content if isinstance(content, list) else []
            text = _blocks_text(content)
            if text.strip():
                turns.append({"role": "user", "content": text, "ts": ts})
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                turns.append(
                    {
                        "role": "tool",
                        "content": "tool_result",
                        "result": _blocks_text(block.get("content")),
                        "ts": ts,
                    }
                )
    return _finalize(turns)


def parse_codex_rollout(path: Path) -> list[TurnStreamEntry]:
    """Parse a Codex rollout JSONL into turns (tolerant best effort).

    Maps response_item message payloads (input_text/output_text) to
    user/agent turns and function_call payloads to tool turns. The
    rollout schema evolves between Codex versions; unknown payloads are
    skipped, never raised.
    """
    turns: list[dict[str, object]] = []
    for entry in _read_jsonl(path):
        payload: dict[str, Any] = (
            entry["payload"] if isinstance(entry.get("payload"), dict) else entry
        )
        if payload.get("type") != "message":
            continue
        ts = normalize_ts(entry.get("timestamp") or payload.get("timestamp"))
        role = payload.get("role")
        content = payload.get("content")
        texts: list[str] = []
        if isinstance(content, list):
            texts = [
                str(block.get("text", ""))
                for block in content
                if isinstance(block, dict)
                and block.get("type") in ("input_text", "output_text", "text")
            ]
        elif isinstance(content, str):
            texts = [content]
        text = "\n".join(part for part in texts if part)
        if not text.strip():
            continue
        if role == "user":
            turns.append({"role": "user", "content": text, "ts": ts})
        elif role in ("assistant", "agent"):
            turns.append({"role": "agent", "content": text, "ts": ts})
    return _finalize(turns)


PARSERS: dict[str, Callable[[Path], list[TurnStreamEntry]]] = {
    "pi": parse_pi_session,
    "claude": parse_claude_transcript,
    "codex": parse_codex_rollout,
}


def parse_transcript(harness: str, path: Path) -> list[TurnStreamEntry]:
    try:
        parser = PARSERS[harness]
    except KeyError:
        raise ValueError(f"unknown harness {harness!r}; expected one of {HARNESSES}") from None
    return parser(path)
