"""Codex capture end-to-end: parser (tools + compaction), merge, wrapper."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from memex import cli
from memex.infrastructure.harness_transcripts import parse_codex_rollout, read_transcript_turns

FIXTURES = Path(__file__).parent.parent / "fixtures"
WRAPPER = Path(__file__).parent.parent.parent / "marketplace/codex/memex-codex-notify.py"


class TestParserToolsAndCompaction:
    def test_tools_parse_with_paired_outputs(self) -> None:
        parsed = parse_codex_rollout(FIXTURES / "codex_rollout_compacted.jsonl")
        turns = parsed.turns
        roles = [turn.role for turn in turns]

        assert roles == ["user", "tool", "tool", "agent", "agent", "user", "tool", "tool", "agent"]
        shell_call = turns[1]
        assert shell_call.tool_name == "shell" and "ls" in (shell_call.query or "")
        shell_out = turns[2]
        assert shell_out.tool_name == "shell" and shell_out.result == "file_a file_b"
        patch = turns[6]
        assert patch.tool_name == "apply_patch" and "patch body" in (patch.query or "")
        assert turns[7].result == '{"output":"done"}'

    def test_compaction_preserves_both_sides_and_skips_replacement(self) -> None:
        parsed = parse_codex_rollout(FIXTURES / "codex_rollout_compacted.jsonl")
        contents = [turn.content for turn in parsed.turns]

        assert "first user turn" in contents  # before compaction
        assert "post-compaction user" in contents  # after compaction
        assert "summary replacement" not in contents  # replacement history skipped
        assert "assistant before compaction" in contents
        assert "assistant after compaction" in contents
        assert "agent inline message" in contents  # agent_message shape

    def test_thread_totals_latest_across_compaction(self) -> None:
        parsed = parse_codex_rollout(FIXTURES / "codex_rollout_compacted.jsonl")
        assert parsed.session_usage is not None
        assert parsed.session_usage["total_tokens"] == 33  # latest, not sum
        assert parsed.header is not None
        assert "token_usage" not in parsed.header.meta


class TestHookMergeIdempotency:
    def _capture(
        self, data_dir: Path, fixture: Path, extra: list[str] | None = None
    ) -> dict[str, object]:
        code = cli.main(
            [
                "--data-dir",
                str(data_dir),
                "hook",
                "transcript",
                "--harness",
                "codex",
                "--path",
                str(fixture),
                *(extra or []),
            ]
        )
        assert code == 0
        return {"code": code}

    def test_repeated_capture_no_duplicate_episode(self, data_dir: Path) -> None:
        self._capture(data_dir, FIXTURES / "codex_rollout_compacted.jsonl")
        self._capture(data_dir, FIXTURES / "codex_rollout_compacted.jsonl")
        episodes = list((data_dir / "docs/global/episodes").glob("*.md"))
        assert len(episodes) == 1

    def test_merge_preserves_earlier_turns_after_shorter_parse(
        self, data_dir: Path, tmp_path: Path
    ) -> None:
        # First capture: full rollout.
        self._capture(data_dir, FIXTURES / "codex_rollout_compacted.jsonl")
        session_id = "sess-comp"  # header-provided id wins
        transcript = next(data_dir.glob(f"transcripts/*/{session_id}.jsonl"))
        first = read_transcript_turns(transcript)
        assert len(first) == 9

        # Simulate post-compaction fresh rollout: shorter, divergent tail.
        shorter = tmp_path / "shorter.jsonl"
        lines = (FIXTURES / "codex_rollout_compacted.jsonl").read_text().splitlines()
        # Keep meta + the post-compaction conversation only.
        shorter.write_text("\n".join([lines[0], *lines[9:]]) + "\n", encoding="utf-8")
        self._capture(data_dir, shorter)
        merged = read_transcript_turns(transcript)

        contents = [turn.content for turn in merged]
        assert "first user turn" in contents  # earlier turns preserved
        assert "assistant after compaction" in contents  # later turns included
        assert len(merged) == 9  # no duplicates from the overlap


class TestWrapper:
    @pytest.fixture(autouse=True)
    def _env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        self.home = tmp_path / "home"
        self.data = tmp_path / "memex"
        (self.home / ".codex").mkdir(parents=True)
        monkeypatch.setenv("HOME", str(self.home))
        monkeypatch.setenv("MEMEX_DATA_DIR", str(self.data))
        return tmp_path

    def _run(self, payload: dict[str, object], memex_bin: str) -> int:
        completed = subprocess.run(  # noqa: S603 - fixture orchestration
            [sys.executable, str(WRAPPER)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=60,
            env={**os.environ, "MEMEX_BIN": memex_bin},
        )
        return completed.returncode

    def _log_lines(self) -> list[dict[str, object]]:
        log = self.data / "logs/codex-capture.log"
        if not log.exists():
            return []
        entries: list[dict[str, object]] = []
        for line in log.read_text().splitlines():
            if line:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    entries.append(parsed)
        return entries

    def test_turn_complete_captures(self, data_dir: Path) -> None:
        fixture = FIXTURES / "codex_rollout_compacted.jsonl"
        code = self._run(
            {
                "type": "agent-turn-complete",
                "session_id": "sess-comp",
                "transcript_path": str(fixture),
            },
            memex_bin="memex",
        )
        assert code == 0
        entries = self._log_lines()
        assert entries[-1]["category"] == "ok"
        assert entries[-1]["event"] == "agent-turn-complete"
        assert list(self.data.glob("transcripts/*/sess-comp.jsonl"))

    def test_post_compact_event_captures(self) -> None:
        code = self._run(
            {
                "type": "PostCompact",
                "session_id": "sess-comp",
                "transcript_path": str(FIXTURES / "codex_rollout_compacted.jsonl"),
            },
            memex_bin="memex",
        )
        assert code == 0
        assert self._log_lines()[-1]["event"] == "postcompact"

    def test_session_end_handoff_is_immediate_and_detached(self) -> None:
        marker = self.data / "handoff-marker"
        slow_bin = self._script(f"#!/bin/sh\nsleep 5\ntouch {marker}\n")
        started = _now()
        code = self._run(
            {
                "type": "SessionEnd",
                "session_id": "sess-x",
                "transcript_path": str(FIXTURES / "codex_rollout_compacted.jsonl"),
            },
            memex_bin=slow_bin,
        )
        elapsed = _now() - started
        assert code == 0
        assert elapsed < 3.0  # fast handoff: hook returned without waiting
        assert self._log_lines()[-1]["detail"] == "detached"

    def test_failing_memex_logs_category(self) -> None:
        failing = self._script("#!/bin/sh\nexit 3\n")
        code = self._run(
            {
                "type": "agent-turn-complete",
                "session_id": "s",
                "transcript_path": str(FIXTURES / "codex_rollout_compacted.jsonl"),
            },
            memex_bin=failing,
        )
        assert code == 0  # nonblocking for Codex
        assert self._log_lines()[-1]["category"] == "nonzero"

    def test_missing_path_logs_and_exits_zero(self) -> None:
        code = self._run({"type": "agent-turn-complete", "session_id": "s"}, memex_bin="memex")
        assert code == 0
        assert self._log_lines()[-1]["category"] == "missing_path"

    def test_no_content_in_diagnostics(self) -> None:
        self._run(
            {
                "type": "agent-turn-complete",
                "session_id": "s",
                "transcript_path": "/nonexistent.jsonl",
            },
            memex_bin="memex",
        )
        raw = (self.data / "logs/codex-capture.log").read_text()
        assert "first user turn" not in raw  # transcript text never logged

    def _script(self, body: str) -> str:
        script = self.data / "fake-bin"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(body, encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return str(script)


def _now() -> float:
    import time

    return time.monotonic()
