"""Tests for prompt-from-stdin parsing, turn loading, and status/info dispatch."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from memex.cli import _load_turns, _prompt_from_stdin


class _FakeStdin:
    def __init__(self, payload: str, *, tty: bool = False) -> None:
        self._stream = io.StringIO(payload)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty

    def read(self) -> str:
        return self._stream.read()


def test_prompt_from_stdin_json_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin('{"prompt": "fix the bug"}'))
    assert _prompt_from_stdin() == "fix the bug"


def test_prompt_from_stdin_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin("", tty=True))
    assert _prompt_from_stdin() == ""


def test_prompt_from_stdin_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin(""))
    assert _prompt_from_stdin() == ""


def test_prompt_from_stdin_raw_text_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin("not json, just a prompt"))
    assert _prompt_from_stdin() == "not json, just a prompt"


def test_prompt_from_stdin_non_string_prompt_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin('{"prompt": 123}'))
    assert _prompt_from_stdin() == '{"prompt": 123}'


def test_prompt_from_stdin_non_dict_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _FakeStdin("[1, 2]"))
    assert _prompt_from_stdin() == "[1, 2]"


class TestLoadTurns:
    def test_valid_turns(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            json.dumps({"role": "user", "content": "hi", "turn": 1})
            + "\n"
            + json.dumps({"role": "agent", "content": "hello", "turn": 2}),
            encoding="utf-8",
        )
        turns = _load_turns(path)
        assert len(turns) == 2

    def test_skips_session_headers_and_blank_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            "\n"
            + json.dumps({"session_meta": {"id": "s1"}})
            + "\n"
            + json.dumps({"role": "user", "content": "hi", "turn": 1}),
            encoding="utf-8",
        )
        turns = _load_turns(path)
        assert len(turns) == 1

    def test_invalid_json_raises_with_line_number(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            '{"role": "user", "content": "hi", "turn": 1}\nnot json\n', encoding="utf-8"
        )
        with pytest.raises(ValueError, match=r"t.jsonl:2"):
            _load_turns(path)

    def test_invalid_turn_raises_with_line_number(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text('{"role": "bogus-role", "content": "x"}\n', encoding="utf-8")
        with pytest.raises(ValueError, match=r"t.jsonl:1"):
            _load_turns(path)


class TestStatusInfoDispatch:
    def test_status(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from memex.cli import main

        monkeypatch.setenv("MEMEX_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("sys.argv", ["memex", "status"])
        assert main() == 0

    def test_info(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from memex.cli import main

        monkeypatch.setenv("MEMEX_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("sys.argv", ["memex", "info"])
        assert main() == 0


class TestDispatchSmoke:
    def test_serve_mcp(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from memex import cli

        called = []
        monkeypatch.setattr("memex.mcp_server.run_server", lambda: called.append(1))
        monkeypatch.setenv("MEMEX_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("sys.argv", ["memex", "serve-mcp"])
        assert cli.main() == 0
        assert called == [1]

    def test_viz(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from memex import cli

        called = []
        monkeypatch.setattr(
            "memex.infrastructure.viz.serve",
            lambda **kw: called.append(kw),
        )
        monkeypatch.setenv("MEMEX_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("sys.argv", ["memex", "viz", "--port", "0"])
        assert cli.main() == 0
        assert called == [{"data_dir": None, "port": 0}]

    def test_backup(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from memex import cli

        out = tmp_path / "backup.zip"
        monkeypatch.setenv("MEMEX_DATA_DIR", str(tmp_path / "store"))
        monkeypatch.setattr("sys.argv", ["memex", "backup", "--output", str(out)])
        assert cli.main() == 0
        assert out.exists()

    def test_approve_unknown_slug_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from memex import cli

        monkeypatch.setenv("MEMEX_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("sys.argv", ["memex", "approve", "ghost"])
        assert cli.main() != 0

    def test_install_missing_marketplace(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from memex import cli

        monkeypatch.setattr(
            "sys.argv",
            ["memex", "install", "codex", "--from", str(tmp_path / "nope")],
        )
        assert cli.main() == 1
        assert "memex:" in capsys.readouterr().err


class TestWatchCommand:
    def test_watch_starts_and_stops(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        import time as time_mod

        from memex import cli
        from memex.infrastructure import watcher as watcher_mod

        started = []
        stopped = []
        monkeypatch.setenv("MEMEX_DATA_DIR", str(tmp_path))
        monkeypatch.setattr(
            watcher_mod.IndexWatcher, "start_polling", lambda self: started.append(1)
        )
        monkeypatch.setattr(
            watcher_mod.IndexWatcher, "stop_polling", lambda self: stopped.append(1)
        )

        def fake_sleep(seconds: float) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(time_mod, "sleep", fake_sleep)
        monkeypatch.setattr("sys.argv", ["memex", "watch", "--poll-interval", "1"])
        assert cli.main() == 0
        assert started == [1]
        assert stopped == [1]
