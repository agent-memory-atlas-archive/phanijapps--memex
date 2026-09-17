"""CLI eval command tests."""

import argparse
import json
from pathlib import Path

import pytest

from memex.cli import _run_eval


def _corpus_args(data_dir: Path, size: int = 50, realistic: bool = False) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.eval_command = "corpus"
    ns.data_dir = str(data_dir)
    ns.size = size
    ns.seed = 42
    ns.realistic = realistic
    return ns


def _retrieval_args(data_dir: Path, size: int = 50, realistic: bool = False) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.eval_command = "retrieval"
    ns.data_dir = str(data_dir)
    ns.size = size
    ns.seed = 42
    ns.top_k = 10
    ns.realistic = realistic
    return ns


def test_eval_corpus_basic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run_eval(_corpus_args(tmp_path, size=20)) == 0
    payload = json.loads(capsys.readouterr().out)
    # Overlap distractors are added on top of the requested size
    assert payload["memories_written"] >= 20
    assert payload["queries_generated"] > 0
    assert payload["data_dir"] == str(tmp_path)


def test_eval_corpus_realistic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run_eval(_corpus_args(tmp_path, size=50, realistic=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["memories_written"] == 50
    assert payload["queries_generated"] > 0
    assert "entity" in payload["domain_counts"]


def test_eval_retrieval_basic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run_eval(_retrieval_args(tmp_path, size=20)) == 0
    out = capsys.readouterr().out
    assert "Recall@10" in out or "recall" in out.lower()


def test_eval_retrieval_realistic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run_eval(_retrieval_args(tmp_path, size=50, realistic=True)) == 0
    out = capsys.readouterr().out
    assert len(out) > 0


def test_main_dispatches_eval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from memex.cli import main

    monkeypatch.setattr(
        "sys.argv",
        ["memex", "eval", "corpus", "--size", "10", "--data-dir", str(tmp_path)],
    )
    assert main() == 0
