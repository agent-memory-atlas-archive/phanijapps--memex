import json
from pathlib import Path

import pytest

from memex import cli


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "cli-home"


def test_write_and_recall_roundtrip(data_dir: Path, capture: dict[str, str]) -> None:
    code = cli.main(
        [
            "--data-dir",
            str(data_dir),
            "write",
            "--type",
            "entity",
            "--title",
            "CLI entity",
            "--body",
            "written from the command line",
            "--tags",
            "cli,test",
        ]
    )
    assert code == 0
    payload = json.loads(capture["out"])
    assert payload["slug"] == "cli-entity"

    code = cli.main(["--data-dir", str(data_dir), "recall", "command line"])
    assert code == 0
    result = json.loads(capture["out"])
    assert [hit["slug"] for hit in result["hits"]] == ["cli-entity"]


def test_forget_missing_slug_errors(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["--data-dir", str(data_dir), "forget", "ghost"])
    assert code == 1
    assert "no wiki page" in capsys.readouterr().err


def test_invalid_write_type_rejected(data_dir: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(
            ["--data-dir", str(data_dir), "write", "--type", "bogus", "--title", "x", "--body", "y"]
        )
    assert excinfo.value.code == 2  # argparse choices


def test_info(data_dir: Path, capture: dict[str, str]) -> None:
    cli.main(
        ["--data-dir", str(data_dir), "write", "--type", "entity", "--title", "Info", "--body", "b"]
    )
    code = cli.main(["--data-dir", str(data_dir), "info"])
    assert code == 0
    info = json.loads(capture["out"])
    assert info["wiki_file_counts"]["entity"] == 1
    assert info["index_total"] == 1


def test_ingest_transcript_cli(data_dir: Path, capture: dict[str, str], tmp_path: Path) -> None:
    turns_file = tmp_path / "turns.jsonl"
    turns_file.write_text(
        json.dumps({"role": "user", "content": "hello", "ts": "2026-09-15T10:00:00Z", "turn": 1})
        + "\n",
        encoding="utf-8",
    )
    code = cli.main(
        [
            "--data-dir",
            str(data_dir),
            "ingest-transcript",
            "--session-id",
            "sess-cli",
            "--turns-file",
            str(turns_file),
        ]
    )
    assert code == 0
    report = json.loads(capture["out"])
    assert report["episode_node"] == "sess-cli"
    assert report["turn_count"] == 1


def test_ingest_bad_turns_file(
    data_dir: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text("not json\n", encoding="utf-8")
    code = cli.main(
        [
            "--data-dir",
            str(data_dir),
            "ingest-transcript",
            "--session-id",
            "sess-bad",
            "--turns-file",
            str(bad),
        ]
    )
    assert code == 1
    assert "bad.jsonl:1" in capsys.readouterr().err


def test_export_import_cli(data_dir: Path, capture: dict[str, str], tmp_path: Path) -> None:
    cli.main(
        ["--data-dir", str(data_dir), "write", "--type", "entity", "--title", "Ex", "--body", "b"]
    )
    export_path = tmp_path / "nodes.json"
    code = cli.main(["--data-dir", str(data_dir), "export", "--output", str(export_path)])
    assert code == 0
    assert export_path.exists()

    other_dir = tmp_path / "other-home"
    code = cli.main(["--data-dir", str(other_dir), "import", "--input", str(export_path)])
    assert code == 0
    payload = json.loads(capture["out"])
    assert payload["imported"] == 1
    assert (other_dir / "wiki/entities/ex.md").exists()


def test_consolidate_requires_api_key(
    data_dir: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MEMEX_API_KEY", raising=False)
    monkeypatch.delenv("MEMEX_LLM_PROVIDER", raising=False)
    code = cli.main(["--data-dir", str(data_dir), "consolidate", "--mode", "dry-run"])
    assert code == 1
    assert "api_key" in capsys.readouterr().err
