"""Spec acceptance tests 13-15, 19-21: forget modes, CLI rebuild, backup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memex import cli
from memex.application.memory import Memex
from memex.domain.models import IngestTranscriptInput, TurnStreamEntry, WriteInput
from memex.infrastructure.config import MemexConfig


@pytest.fixture
def memex(data_dir: Path) -> Memex:
    return Memex(MemexConfig(data_dir=data_dir))


@pytest.fixture
def config(data_dir: Path) -> MemexConfig:
    return MemexConfig(data_dir=data_dir)


def _write(memex: Memex, title: str, body: str = "some body text", **overrides: object) -> str:
    fields: dict[str, object] = {"type": "entity", "title": title, "body": body}
    fields.update(overrides)
    node = memex.write(WriteInput(**fields))  # type: ignore[arg-type]
    return node.slug


def test_forget_hard(memex: Memex) -> None:
    slug = _write(memex, "Hard target", "delete me completely")
    assert memex.wiki_store.exists(slug)

    result = memex.forget(slug, mode="hard")

    assert result.forgotten is True
    assert result.file_path is None
    assert not memex.wiki_store.exists(slug)
    assert memex.index_manager.get(slug) is None
    outgoing = memex.link_manager.get_outgoing(slug)
    backlinks = memex.link_manager.get_backlinks(slug)
    assert outgoing == [] and backlinks == []


def test_forget_soft(memex: Memex) -> None:
    slug = _write(memex, "Soft target", "retire me temporally")
    result = memex.forget(slug, mode="soft", valid_to="2020-01-01T00:00:00Z")

    assert result.forgotten is True
    assert result.file_path is not None and Path(result.file_path).exists()
    node = memex.wiki_store.read(slug)
    assert node is not None
    assert node.valid_to == "2020-01-01T00:00:00Z"

    # Excluded from recall once valid_to is in the past.
    hits = memex.recall("retire").hits
    assert slug not in [hit.slug for hit in hits]
    included = memex.recall("retire", include_expired=True).hits
    assert slug in [hit.slug for hit in included]


def test_forget_decay(memex: Memex) -> None:
    slug = _write(memex, "Decay target", "let me expire naturally")
    result = memex.forget(slug, mode="decay", valid_to="2020-01-01T00:00:00Z")

    assert result.mode == "decay"
    node = memex.wiki_store.read(slug)
    assert node is not None
    assert node.expires_at == "2020-01-01T00:00:00Z"
    assert slug not in [hit.slug for hit in memex.recall("expire").hits]


def test_forget_errors(memex: Memex) -> None:
    with pytest.raises(FileNotFoundError):
        memex.forget("ghost-slug")
    _write(memex, "Mode target", "x")
    with pytest.raises(ValueError, match="mode"):
        memex.forget("mode-target", mode="explode")


def test_rebuild_index_command(
    config: MemexConfig, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    memex = Memex(config)
    for i in range(4):
        _write(memex, f"Rebuild node {i}", f"rebuildable content {i}")
    memex.close()

    exit_code = cli.main(["--data-dir", str(data_dir), "rebuild-index", "--force"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["nodes_indexed"] == 4
    assert output["nodes_errored"] == 0
    wiki_files = list((data_dir / "docs").rglob("*.md"))
    assert output["nodes_indexed"] == len(wiki_files)

    memex = Memex(config)
    assert memex.index_manager.get_meta("last_index_rebuild") is not None
    assert memex.index_manager.get_meta("wiki_file_count") == "4"
    memex.close()


def test_backup_and_restore(config: MemexConfig, data_dir: Path) -> None:
    memex = Memex(config)
    _write(memex, "Backup entity", "content that survives backup")
    _write(memex, "Second entity", "more content", type="preference")
    memex.ingest_transcript(
        IngestTranscriptInput(
            session_id="sess-backup",
            turns=[
                TurnStreamEntry("user", "hello", 1, "2026-09-15T10:00:00Z"),
                TurnStreamEntry("agent", "hi", 2, "2026-09-15T10:00:01Z"),
            ],
        )
    )
    archive = data_dir.parent / "backup.tar.gz"
    report = memex.backup(archive)
    assert report.file_counts["wiki"] == 3
    assert report.file_counts["mem_db"] == 1
    assert memex.backup_restore.verify(archive) is True

    import shutil

    shutil.rmtree(data_dir / "docs")
    shutil.rmtree(data_dir / "transcripts")
    (data_dir / "mem.db").unlink()
    memex.close()

    restored_memex = Memex(config)
    restore_report = restored_memex.restore(archive)

    assert restore_report.restored is True
    assert restore_report.index_rebuilt is True
    assert restore_report.file_counts["wiki"] == 3
    assert restore_report.file_counts["transcripts"] == 2
    assert restored_memex.wiki_store.exists("backup-entity")
    assert restored_memex.wiki_store.exists("second-entity")
    assert (data_dir / "transcripts/2026-09-15/sess-backup.jsonl").exists()

    result = restored_memex.recall("survives backup")
    assert result.hits[0].slug == "backup-entity"
    restored_memex.close()


def test_backup_restore_skips_missing_mem_db(config: MemexConfig, data_dir: Path) -> None:
    memex = Memex(config)
    _write(memex, "No db entity", "index rebuilds from wiki alone")
    archive = data_dir.parent / "backup-nodb.tar.gz"
    backup_report = memex.backup(archive, include_mem_db=False)
    assert backup_report.file_counts["mem_db"] == 0
    memex.close()

    import shutil

    shutil.rmtree(data_dir / "docs")
    (data_dir / "mem.db").unlink()

    restored_memex = Memex(config)
    restore_report = restored_memex.restore(archive)

    assert restore_report.restored is True
    assert restore_report.index_rebuilt is True
    assert restored_memex.wiki_store.exists("no-db-entity")
    assert restored_memex.index_manager.get("no-db-entity") is not None
    restored_memex.close()
