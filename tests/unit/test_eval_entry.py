"""Tests for the external eval entry point (eval/run.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.run import main as eval_main


def test_eval_corpus_basic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert eval_main(["corpus", "--size", "20", "--data-dir", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    # Overlap distractors are added on top of the requested size
    assert payload["memories_written"] >= 20
    assert payload["queries_generated"] > 0
    assert payload["data_dir"] == str(tmp_path)


def test_eval_corpus_realistic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert eval_main(["corpus", "--size", "50", "--realistic", "--data-dir", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["memories_written"] == 50
    assert payload["queries_generated"] > 0
    assert "entity" in payload["domain_counts"]


def test_eval_retrieval_basic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert eval_main(["retrieval", "--size", "20", "--data-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Recall@10" in out or "recall" in out.lower()


def test_eval_retrieval_realistic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        eval_main(
            [
                "retrieval",
                "--size",
                "50",
                "--realistic",
                "--data-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert len(out) > 0


def test_eval_retrieval_writes_reproducible_json(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    report_path = tmp_path / "report.json"

    assert (
        eval_main(
            [
                "retrieval",
                "--size",
                "20",
                "--seed",
                "7",
                "--data-dir",
                str(data_dir),
                "--json-output",
                str(report_path),
            ]
        )
        == 0
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["run"]["seed"] == 7
    assert payload["run"]["git_commit"]
    assert isinstance(payload["run"]["git_dirty"], bool)
    assert payload["run"]["ranker"]["name"] == "sqlite-fts5-bm25"
    assert payload["metrics"]["total_queries"] > 0


def test_eval_retrieval_uses_fresh_temporary_store_by_default(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"

    assert eval_main(["retrieval", "--size", "20", "--json-output", str(report_path)]) == 0

    run = json.loads(report_path.read_text(encoding="utf-8"))["run"]
    assert run["ephemeral_data_dir"] is True
    assert not Path(run["data_dir"]).exists()


def test_eval_retrieval_rejects_nonempty_store(tmp_path: Path) -> None:
    (tmp_path / "unrelated.txt").write_text("do not delete", encoding="utf-8")

    with pytest.raises(ValueError, match="must be empty"):
        eval_main(["retrieval", "--size", "20", "--data-dir", str(tmp_path)])

    assert (tmp_path / "unrelated.txt").read_text(encoding="utf-8") == "do not delete"


def test_cli_no_longer_has_eval_subcommand() -> None:
    """The product CLI must not expose benchmark tooling."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "memex.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert "eval" not in proc.stdout


def test_run_module_help() -> None:
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "eval.run", "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "corpus" in proc.stdout
    assert "retrieval" in proc.stdout
