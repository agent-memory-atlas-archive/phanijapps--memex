"""Harness transcript parsers: session files -> TurnStreamEntry lists."""

from pathlib import Path

import pytest

from memex.domain.models import TurnStreamEntry
from memex.infrastructure.harness_transcripts import (
    normalize_ts,
    parse_claude_transcript,
    parse_codex_rollout,
    parse_pi_session,
    parse_transcript,
    suggest_session_id,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_pi_session_parses_roles_and_tools() -> None:
    turns = parse_pi_session(FIXTURES / "pi_session.jsonl").turns

    assert [turn.role for turn in turns] == ["user", "agent", "tool", "tool"]
    assert turns[0].content == "I prefer ruff for linting"
    assert turns[1].content == "Got it, ruff it is."
    assert turns[2].tool_name == "bash"
    assert turns[2].result == "ruff installed"
    assert turns[3].tool_name == "bash"
    assert turns[3].query == "uv run ruff check ."
    # The assistant entry containing only thinking + toolCall blocks produces
    # no conversational text and is skipped, so turns number 1..4.
    assert [turn.turn for turn in turns] == [1, 2, 3, 4]
    assert turns[0].ts == "2026-09-15T10:00:01Z"  # unix ms normalized


def test_claude_transcript_parses_tool_use_and_results() -> None:
    turns = parse_claude_transcript(FIXTURES / "claude_transcript.jsonl").turns

    assert [turn.role for turn in turns] == ["user", "agent", "tool", "tool"]
    assert turns[0].content == "Remember the deploy uses blue-green"
    assert turns[2].tool_name == "Bash"
    assert "kubectl get pods" in (turns[2].query or "")
    assert turns[3].result == "NAME READY\npod/a 1/1"
    assert turns[0].ts == "2026-09-15T10:00:00Z"  # ms truncated


def test_codex_rollout_parses_messages_and_skips_unknown() -> None:
    parsed = parse_codex_rollout(FIXTURES / "codex_rollout.jsonl")
    turns = parsed.turns
    assert parsed.header is not None  # fixture carries session_meta

    assert [turn.role for turn in turns] == ["user", "agent", "tool"]
    assert turns[0].content == "use postgres for the cache"
    assert turns[1].content == "Switching the cache driver to postgres."
    assert turns[2].tool_name == "shell"
    assert "ls" in (turns[2].query or "")


def test_empty_and_garbage_files_yield_no_turns(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    garbage = tmp_path / "garbage.jsonl"
    garbage.write_text("{\nnot json\n[]\n", encoding="utf-8")

    assert parse_pi_session(empty).turns == []
    assert parse_claude_transcript(garbage).turns == []
    assert parse_codex_rollout(empty).turns == []


def test_normalize_ts_variants() -> None:
    assert normalize_ts(1760000001000) == "2025-10-09T08:53:21Z"
    assert normalize_ts("2026-09-15T10:00:00.123Z") == "2026-09-15T10:00:00Z"
    assert normalize_ts("2026-09-15T12:00:00+02:00") == "2026-09-15T10:00:00Z"
    assert normalize_ts("garbage") == ""
    assert normalize_ts(None) == ""
    assert normalize_ts(True) == ""


def test_suggest_session_id_charset() -> None:
    weird = Path("/sessions/2026-09-15 10;00 session file!!.jsonl")
    session_id = suggest_session_id("claude", weird)
    assert all(ch.isalnum() or ch in "._-" for ch in session_id)
    assert session_id.startswith("claude-")
    assert len(session_id) <= 80


def test_parse_transcript_dispatch_and_unknown_harness(tmp_path: Path) -> None:
    parsed = parse_transcript("pi", FIXTURES / "pi_session.jsonl")
    assert parsed.turns and isinstance(parsed.turns[0], TurnStreamEntry)

    with pytest.raises(ValueError, match="unknown harness"):
        parse_transcript("vscode", tmp_path / "x.jsonl")
