"""Tests for stdin transcript-path extraction and hook dispatch edge cases."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from memex.cli import _transcript_path_from_stdin


class _FakeStdin:
    def __init__(self, payload: str, *, tty: bool = False) -> None:
        self._stream = io.StringIO(payload)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty

    def read(self) -> str:
        return self._stream.read()


def test_stdin_transcript_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = json.dumps({"transcript_path": str(tmp_path / "s.jsonl")})
    monkeypatch.setattr(sys, "stdin", _FakeStdin(payload))
    assert _transcript_path_from_stdin() == tmp_path / "s.jsonl"


def test_stdin_session_transcript_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = json.dumps({"session_transcript": str(tmp_path / "a.jsonl")})
    monkeypatch.setattr(sys, "stdin", _FakeStdin(payload))
    assert _transcript_path_from_stdin() == tmp_path / "a.jsonl"


def test_stdin_rollout_path_dashed_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = json.dumps({"rollout-path": str(tmp_path / "r.jsonl")})
    monkeypatch.setattr(sys, "stdin", _FakeStdin(payload))
    assert _transcript_path_from_stdin() == tmp_path / "r.jsonl"


def test_stdin_tty_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin("", tty=True))
    assert _transcript_path_from_stdin() is None


def test_stdin_empty_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin(""))
    assert _transcript_path_from_stdin() is None


def test_stdin_invalid_json_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin("not json at all"))
    assert _transcript_path_from_stdin() is None


def test_stdin_non_dict_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin('["transcript_path", "/tmp/x"]'))
    assert _transcript_path_from_stdin() is None


def test_stdin_no_matching_key_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin('{"other": "value"}'))
    assert _transcript_path_from_stdin() is None


def test_stdin_non_string_value_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin('{"transcript_path": 123}'))
    assert _transcript_path_from_stdin() is None
