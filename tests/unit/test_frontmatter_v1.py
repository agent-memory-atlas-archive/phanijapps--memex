"""T1 + T1b: front-matter schema (status/occurred_at/provenance), v2 index
with auto-rebuild, and the consolidation/capture run log."""

import json
from pathlib import Path

import pytest

from memex import Memex
from memex.domain.models import WriteInput
from memex.infrastructure.config import MemexConfig as Config
from memex.infrastructure.index_manager import SCHEMA_VERSION, IndexManager
from memex.infrastructure.run_log import append_run, read_runs, zero_yield_streak
from memex.infrastructure.wiki_store import WikiStore


class TestFrontMatterRoundTrip:
    def test_status_and_provenance_round_trip(self, data_dir: Path) -> None:
        store = WikiStore(data_dir)
        from memex.domain.models import WikiNode

        store.write(
            WikiNode(
                type="entity",
                title="Guarded node",
                body="content",
                id="g1",
                status="pending",
                occurred_at="2026-09-10T08:00:00Z",
                source="transcript",
                harness="codex",
                confidence="high",
            )
        )
        read_back = store.read("guarded-node")
        assert read_back is not None
        assert read_back.status == "pending"
        assert read_back.occurred_at == "2026-09-10T08:00:00Z"
        assert read_back.source == "transcript"
        assert read_back.harness == "codex"
        assert read_back.confidence == "high"

    def test_missing_status_defaults_active(self, data_dir: Path) -> None:
        store = WikiStore(data_dir)
        store.write(_node())
        page = data_dir / "docs/entities/plain.md"
        text = page.read_text(encoding="utf-8")
        assert 'status: "active"' in text  # explicit default is serialized
        read_back = store.read("plain")
        assert read_back is not None
        assert read_back.status == "active"

    def test_invalid_status_rejected(self, data_dir: Path) -> None:
        from memex.domain.models import WikiNode

        with pytest.raises(Exception, match="status"):
            WikiNode(type="entity", title="x", body="y", id="z", status="bogus")

    def test_backup_restore_parity(self, data_dir: Path) -> None:
        memex = Memex(Config(data_dir=data_dir))
        memex.write(WriteInput(type="entity", title="Parity", body="b", importance=0.7))
        archive = data_dir.parent / "parity.tar.gz"
        memex.backup(archive)
        report = memex.restore(archive)
        assert report.restored is True
        memex.close()


def _node():
    from memex.domain.models import WikiNode

    return WikiNode(type="entity", title="Plain", body="b", id="p1")


class TestSchemaV2AutoRebuild:
    def test_needs_rebuild_on_version_mismatch(self, data_dir: Path) -> None:
        store = WikiStore(data_dir)
        store.write(_node())
        index = IndexManager(data_dir / "mem.db")
        index.update_record(store.read("plain") or store.list()[0])
        # Forge a v1 marker.
        index.set_meta("schema_version", "1")
        assert index.needs_rebuild() is True
        index.drop_for_rebuild()
        assert index.needs_rebuild() is False
        assert index.get_meta("schema_version") == SCHEMA_VERSION
        index.close()

    def test_facade_rebuilds_stale_index_transparently(self, data_dir: Path) -> None:
        memex = Memex(Config(data_dir=data_dir))
        memex.write(WriteInput(type="entity", title="Stale", body="b"))
        memex.index_manager.set_meta("schema_version", "1")
        memex.close()

        reopened = Memex(Config(data_dir=data_dir))
        assert reopened.index_manager.get_meta("schema_version") == SCHEMA_VERSION
        result = reopened.recall("stale")
        assert [hit.slug for hit in result.hits] == ["stale"]  # rebuilt from wiki
        reopened.close()


class TestRunLog:
    def test_append_read_round_trip(self, tmp_path: Path) -> None:
        append_run(
            tmp_path,
            {
                "ts": "2026-09-16T10:00:00Z",
                "kind": "consolidation",
                "nodes_created": 0,
            },
        )
        append_run(
            tmp_path,
            {
                "ts": "2026-09-16T10:01:00Z",
                "kind": "capture",
                "harness": "codex",
                "cwd_recorded": True,
            },
        )
        runs = read_runs(tmp_path)
        assert [run["kind"] for run in runs] == ["consolidation", "capture"]

    def test_invalid_kind_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="kind"):
            append_run(tmp_path, {"kind": "bogus"})

    def test_zero_yield_streak(self, tmp_path: Path) -> None:
        for i in range(4):
            append_run(
                tmp_path,
                {
                    "ts": f"2026-09-16T10:0{i}:00Z",
                    "kind": "consolidation",
                    "nodes_created": 0 if i < 3 else 2,
                },
            )
        assert zero_yield_streak(read_runs(tmp_path)) == 0  # newest is nonzero
        append_run(
            tmp_path,
            {"ts": "2026-09-16T10:05:00Z", "kind": "consolidation", "nodes_created": 0},
        )
        assert zero_yield_streak(read_runs(tmp_path)) == 1

    def test_empty_log(self, tmp_path: Path) -> None:
        assert read_runs(tmp_path) == []
        assert zero_yield_streak([]) == 0


class TestCaptureCwdGuard:
    """Non-AC characterization: attribution uses only recorded cwd."""

    def test_capture_records_cwd_flag(self, data_dir: Path, tmp_path: Path) -> None:
        from memex import cli

        turns = tmp_path / "turns.jsonl"
        turns.write_text(
            json.dumps({"role": "user", "content": "hi", "ts": "2026-09-16T10:00:00Z", "turn": 1})
            + "\n",
            encoding="utf-8",
        )
        code = cli.main(
            [
                "--data-dir",
                str(data_dir),
                "ingest-transcript",
                "--session-id",
                "cwdless",
                "--turns-file",
                str(turns),
            ]
        )
        assert code == 0
        runs = read_runs(data_dir)
        capture = [run for run in runs if run["kind"] == "capture"]
        assert capture and capture[-1]["cwd_recorded"] is False
