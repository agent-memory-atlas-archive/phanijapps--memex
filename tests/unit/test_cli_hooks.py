"""CLI hook commands: the adapter contract for harness integrations."""

import json
from pathlib import Path

import pytest

from memex import cli
from memex.application.memory import Memex
from memex.domain.models import WriteInput
from memex.infrastructure.config import MemexConfig

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def seeded(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    memex = Memex(MemexConfig(data_dir=data_dir))
    memex.write(WriteInput(type="preference", title="Prefer ruff", body="lint with ruff always"))
    memex.close()
    monkeypatch.chdir(data_dir)
    return data_dir


def test_session_start_emits_context_block(seeded: Path, capture: dict[str, str]) -> None:
    code = cli.main(["--data-dir", str(seeded), "hook", "session-start", "--query", "linting"])
    assert code == 0
    out = capture["out"]
    assert out.startswith("[memex] Memories below are yours")
    assert "=== memex MEMORY ===" in out
    assert "Prefer ruff" in out
    assert out.rstrip().endswith("=== END memex MEMORY ===")


def test_session_start_no_memory_is_silent(seeded: Path, capture: dict[str, str]) -> None:
    code = cli.main(
        ["--data-dir", str(seeded), "hook", "session-start", "--query", "quantum chromodynamics"]
    )
    assert code == 0
    assert capture.get("out", "") == ""


def test_prompt_hook_accepts_raw_text(
    seeded: Path, capture: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", _fake_stdin("ruff preferences"))
    code = cli.main(["--data-dir", str(seeded), "hook", "prompt"])
    assert code == 0
    assert "Prefer ruff" in capture["out"]


def test_prompt_hook_accepts_claude_json_payload(
    seeded: Path, capture: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = json.dumps({"session_id": "abc", "prompt": "ruff preferences?", "cwd": "/workspace"})
    monkeypatch.setattr("sys.stdin", _fake_stdin(payload))
    code = cli.main(["--data-dir", str(seeded), "hook", "prompt"])
    assert code == 0
    assert "Prefer ruff" in capture["out"]


def test_prompt_hook_empty_stdin(
    seeded: Path, capture: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", _fake_stdin(""))
    code = cli.main(["--data-dir", str(seeded), "hook", "prompt"])
    assert code == 0
    assert capture.get("out", "") == ""


def test_prompt_hook_prompt_flag(seeded: Path, capture: dict[str, str]) -> None:
    code = cli.main(["--data-dir", str(seeded), "hook", "prompt", "--prompt", "ruff preferences"])
    assert code == 0
    assert "Prefer ruff" in capture["out"]


def test_transcript_hook_ingests_pi_session(seeded: Path, capture: dict[str, str]) -> None:
    session_file = FIXTURES / "pi_session.jsonl"
    code = cli.main(
        [
            "--data-dir",
            str(seeded),
            "hook",
            "transcript",
            "--harness",
            "pi",
            "--path",
            str(session_file),
        ]
    )
    assert code == 0
    report = json.loads(capture["out"])
    assert report["harness"] == "pi"
    assert report["episode_node"]
    assert report["turn_count"] >= 3

    data_dir = seeded
    transcript = data_dir / f"transcripts/{report['session_id']}.jsonl"
    assert transcript.exists()


def test_transcript_hook_idempotent(seeded: Path, capture: dict[str, str]) -> None:
    args = [
        "--data-dir",
        str(seeded),
        "hook",
        "transcript",
        "--harness",
        "claude",
        "--path",
        str(FIXTURES / "claude_transcript.jsonl"),
    ]
    assert cli.main(args) == 0
    assert cli.main(args) == 0  # overwrite by default: no error, no duplicate

    episodes = list((seeded / "docs/episodes").glob("*.md"))
    assert len(episodes) == 1


def test_transcript_hook_no_overwrite_quiet(seeded: Path, capture: dict[str, str]) -> None:
    base = [
        "--data-dir",
        str(seeded),
        "hook",
        "transcript",
        "--harness",
        "codex",
        "--path",
        str(FIXTURES / "codex_rollout.jsonl"),
    ]
    assert cli.main(base) == 0
    code = cli.main([*base, "--no-overwrite"])
    assert code == 0  # already ingested is not a failure for a hook


def test_transcript_hook_missing_file(seeded: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(
        [
            "--data-dir",
            str(seeded),
            "hook",
            "transcript",
            "--harness",
            "pi",
            "--path",
            "/nonexistent/session.jsonl",
        ]
    )
    assert code == 1
    assert "transcript not found" in capsys.readouterr().err


class _FakeStdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def isatty(self) -> bool:
        return False

    def read(self) -> str:
        return self._text


def _fake_stdin(text: str) -> _FakeStdin:
    return _FakeStdin(text)
