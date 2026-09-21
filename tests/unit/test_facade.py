from pathlib import Path

import pytest

from memex.application.memory import Memex
from memex.domain.models import IngestTranscriptInput, TurnStreamEntry, WriteInput
from memex.infrastructure.config import MemexConfig


@pytest.fixture
def memex(data_dir: Path) -> Memex:
    return Memex(MemexConfig(data_dir=data_dir))


def test_write_updates_index_and_links(memex: Memex) -> None:
    memex.write(WriteInput(type="entity", title="Python 3.12", body="the version"))
    node = memex.write(
        WriteInput(type="entity", title="Ruff linter", body="lints for [[python-3-12]]")
    )

    row = memex.index_manager.get(node.slug)
    assert row is not None and row["node_type"] == "entity"
    assert memex.link_manager.link_exists(node.slug, "python-3-12")
    assert memex.link_manager.get_backlinks("python-3-12") == [node.slug]


def test_write_persists_description_and_returns_it_on_recall(memex: Memex) -> None:
    memex.write(
        WriteInput(
            type="entity",
            title="Kubernetes probes",
            body="ordinary body words",
            description="liveness and readiness probe settings",
        )
    )
    row = memex.index_manager.get("kubernetes-probes")
    assert row is not None
    assert row["description"] == "liveness and readiness probe settings"

    result = memex.recall("liveness")
    assert [hit.slug for hit in result.hits] == ["kubernetes-probes"]
    assert result.hits[0].description == "liveness and readiness probe settings"
    assert result.hits[0].snippet_source == "description"


def test_rebuild_index_picks_up_description_only_edit(memex: Memex) -> None:
    memex.write(
        WriteInput(
            type="entity",
            title="Rebuildable",
            body="same body",
            description="before-edit signpost",
        )
    )
    page = Path("docs/global/entities/rebuildable.md")
    page = memex.data_dir / page
    page.write_text(
        page.read_text().replace(
            'description: "before-edit signpost"', 'description: "after-edit signpost"'
        ),
        encoding="utf-8",
    )

    report = memex.rebuild_index()

    assert report.nodes_indexed == 1
    row = memex.index_manager.get("rebuildable")
    assert row is not None
    assert row["description"] == "after-edit signpost"
    result = memex.recall("after-edit")
    assert [hit.slug for hit in result.hits] == ["rebuildable"]


def test_status_counts_description_mismatch_as_stale(memex: Memex) -> None:
    memex.write(
        WriteInput(type="entity", title="Stale desc", body="b", description="original signpost")
    )
    page = memex.data_dir / "docs/global/entities/stale-desc.md"
    page.write_text(
        page.read_text().replace(
            'description: "original signpost"', 'description: "edited signpost"'
        ),
        encoding="utf-8",
    )

    assert memex.status()["index_stale_rows"] == 1
    memex.rebuild_index()
    assert memex.status()["index_stale_rows"] == 0


def test_write_rejects_oversized_body(data_dir: Path) -> None:
    import dataclasses

    base = MemexConfig(data_dir=data_dir)
    config = dataclasses.replace(base, wiki=dataclasses.replace(base.wiki, max_body_chars=10))
    small = Memex(config)
    with pytest.raises(ValueError, match="max_body_chars"):
        small.write(WriteInput(type="entity", title="Big", body="x" * 50))


def test_recall_via_facade(memex: Memex) -> None:
    memex.write(WriteInput(type="entity", title="Zebra entity", body="striped animal"))
    result = memex.recall("zebra")
    assert result.search_engine == "semantic-and-fallback-fts5"
    assert [hit.slug for hit in result.hits] == ["zebra-entity"]
    row = memex.index_manager.get("zebra-entity")
    assert row is not None and row["access_count"] == 1


def test_provenance_and_sessions(memex: Memex) -> None:
    memex.ingest_transcript(
        IngestTranscriptInput(
            session_id="sess-facade",
            turns=[TurnStreamEntry("user", "I prefer ruff", 1, "2026-09-15T10:00:00Z")],
        )
    )
    sessions = memex.list_sessions()
    assert [session.session_id for session in sessions] == ["sess-facade"]

    provenance = memex.get_provenance("sess-facade")
    assert provenance is not None
    assert provenance.confidence == "direct"
    assert provenance.transcript_files[0].endswith("sess-facade.jsonl")


def test_export_import_roundtrip(memex: Memex, data_dir: Path) -> None:
    memex.write(WriteInput(type="entity", title="Export me", body="roundtrip body"))
    export_path = data_dir.parent / "export.json"
    document = memex.import_export.export(export_path)
    assert document["version"] == "1.0"
    assert len(document["nodes"]) == 1  # type: ignore[arg-type]
    assert export_path.exists()

    import shutil

    shutil.rmtree(data_dir / "docs")
    memex.import_export.import_file(export_path)
    assert memex.wiki_store.exists("export-me")
    assert memex.index_manager.get("export-me") is not None


def test_export_import_roundtrip_preserves_project_scope(memex: Memex, data_dir: Path) -> None:
    node = memex.write(
        WriteInput(
            type="entity",
            title="Scoped export",
            body="roundtrip project body",
            scope="project",
            project_id="a" * 24,
            project_label="Project alpha",
            project_locator="git-alpha",
        )
    )
    export_path = data_dir.parent / "scoped-export.json"
    document = memex.import_export.export(export_path)
    nodes = document["nodes"]
    assert isinstance(nodes, list)
    exported = nodes[0]
    assert isinstance(exported, dict)
    assert exported["scope"] == "project"
    assert exported["project_id"] == "a" * 24
    assert exported["project_label"] == "Project alpha"

    import shutil

    shutil.rmtree(data_dir / "docs")
    memex.import_export.import_file(export_path)

    restored = memex.wiki_store.read(node.slug, "entity", scope="project", project_id="a" * 24)
    assert restored is not None
    assert restored.project_id == "a" * 24


def test_import_scrubs_secret_shaped_description(memex: Memex, data_dir: Path) -> None:
    secret = "sk-proj-1234567890abcdefghij"  # noqa: S105 - fixture, never real
    document: dict[str, object] = {
        "nodes": [
            {
                "slug": "imported-secret",
                "type": "entity",
                "title": "Imported secret",
                "body": "clean body",
                "description": f"token {secret} here",
            }
        ]
    }
    result = memex.import_export.import_data(document)
    assert result["imported"] == 1
    node = memex.wiki_store.read("imported-secret")
    assert node is not None and node.file_path
    assert secret not in node.description
    assert "[REDACTED:openai_key]" in node.description
    assert secret not in Path(node.file_path).read_text(encoding="utf-8")


def test_rebuild_after_manual_edit(memex: Memex) -> None:
    memex.write(WriteInput(type="entity", title="Manual edit", body="original"))
    page = data_dir_page(memex)
    page.write_text(page.read_text().replace("original", "edited by hand"), encoding="utf-8")

    report = memex.rebuild_index()
    assert report.nodes_indexed == 1
    row = memex.index_manager.get("manual-edit")
    assert row is not None
    assert "edited by hand" in str(row["body"])


def data_dir_page(memex: Memex) -> Path:
    return next(
        p for p in (memex.data_dir / "docs/global/entities").glob("*.md") if p.name != "index.md"
    )


def test_apply_decay_via_facade(memex: Memex) -> None:
    memex.write(WriteInput(type="entity", title="Decayable", body="x"))
    changes = memex.apply_decay(dry_run=True)
    assert changes == [] or changes[0][0] == "decayable"
