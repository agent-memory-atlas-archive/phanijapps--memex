from pathlib import Path

import pytest

from memex.domain.errors import IndexManagerError
from memex.domain.models import WikiNode
from memex.infrastructure.index_manager import SCHEMA_VERSION, IndexManager, check_slug


def _node(**overrides: object) -> WikiNode:
    fields: dict[str, object] = {"type": "entity", "title": "T", "body": "b", "id": "x1"}
    fields.update(overrides)
    return WikiNode(**fields)  # type: ignore[arg-type]


def test_initialize_is_idempotent(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    index.initialize()
    index.initialize()
    assert index.get_meta("schema_version") == SCHEMA_VERSION


def test_description_column_is_created_and_mirrored(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    columns = {row["name"] for row in index.connection.execute("PRAGMA table_info(wiki_index)")}
    assert "description" in columns

    index.update_record(_node(slug="d", description="signpost text", body="body words", id="x"))
    row = index.get("d")
    assert row is not None
    assert row["description"] == "signpost text"
    fts_row = index.connection.execute(
        "SELECT description FROM wiki_fts WHERE wiki_fts MATCH 'signpost'"
    ).fetchone()
    assert fts_row is not None and fts_row["description"] == "signpost text"


def test_pre_description_index_is_detected_and_rebuilt(data_dir: Path) -> None:
    import sqlite3

    index = IndexManager(data_dir / "mem.db")
    index.update_record(_node(slug="t", file_path=str(data_dir / "t.md"), id="x"))
    index.close()

    connection = sqlite3.connect(data_dir / "mem.db")
    for trigger in ("wiki_index_ai", "wiki_index_ad", "wiki_index_au"):
        connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    connection.execute("ALTER TABLE wiki_index DROP COLUMN description")
    connection.commit()
    connection.close()

    reopened = IndexManager(data_dir / "mem.db")
    assert reopened.needs_rebuild() is True  # column-shape check, not meta stamp
    reopened.drop_for_rebuild()
    assert reopened.needs_rebuild() is False
    columns = {row["name"] for row in reopened.connection.execute("PRAGMA table_info(wiki_index)")}
    assert "description" in columns
    assert reopened.get_meta("schema_version") == SCHEMA_VERSION


def test_initialize_replaces_a_pre_namespace_disposable_index(data_dir: Path) -> None:
    import sqlite3

    data_dir.mkdir()
    connection = sqlite3.connect(data_dir / "mem.db")
    connection.execute("CREATE TABLE wiki_index (id TEXT PRIMARY KEY, slug TEXT NOT NULL)")
    connection.commit()
    connection.close()

    index = IndexManager(data_dir / "mem.db")
    columns = {row["name"] for row in index.connection.execute("PRAGMA table_info(wiki_index)")}
    assert {"scope", "project_id", "project_label"} <= columns


def test_upsert_updates_existing_row(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    node = _node(slug="t", file_path=str(data_dir / "docs/entities/t.md"))
    index.update_record(node)
    node.importance = 0.9
    index.update_record(node)

    row = index.get("t")
    assert row is not None
    assert row["importance"] == 0.9
    assert index.count() == 1


def test_get_refuses_ambiguous_duplicate_project_slug(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    index.update_record(
        _node(
            slug="shared",
            id="first",
            file_path=str(data_dir / "docs/projects/git-one/entities/shared.md"),
            scope="project",
            project_id="a" * 24,
        )
    )
    index.update_record(
        _node(
            slug="shared",
            id="second",
            file_path=str(data_dir / "docs/projects/git-two/entities/shared.md"),
            scope="project",
            project_id="b" * 24,
        )
    )

    with pytest.raises(IndexManagerError, match="ambiguous index row"):
        index.get("shared")
    assert index.get("shared", scope="project", project_id="b" * 24, node_type="entity") is not None


def test_remove_record_purges_links(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    index.initialize()
    node = _node(slug="t", file_path=str(data_dir / "t.md"))
    index.update_record(node)
    index.connection.execute(
        "INSERT INTO wiki_links (source_scope, source_project_id, source_slug, target_slug)"
        " VALUES ('global', '', 't', 'other')"
    )
    index.connection.commit()

    index.remove_record("t")
    assert index.get("t") is None
    remaining = index.connection.execute("SELECT COUNT(*) AS n FROM wiki_links").fetchone()
    assert remaining["n"] == 0


def test_scoped_remove_record_preserves_backlinks_to_remaining_duplicate_slug(
    data_dir: Path,
) -> None:
    index = IndexManager(data_dir / "mem.db")
    index.update_record(_node(slug="source", file_path="/source"))
    index.update_record(
        _node(
            slug="shared",
            id="first",
            file_path="/first",
            scope="project",
            project_id="a" * 24,
        )
    )
    index.update_record(
        _node(
            slug="shared",
            id="second",
            file_path="/second",
            scope="project",
            project_id="b" * 24,
        )
    )
    index.connection.execute(
        "INSERT INTO wiki_links (source_scope, source_project_id, source_slug, target_slug)"
        " VALUES ('global', '', 'source', 'shared')"
    )
    index.connection.commit()

    index.remove_record("shared", scope="project", project_id="a" * 24, node_type="entity")

    remaining = index.connection.execute(
        "SELECT source_slug, target_slug FROM wiki_links"
    ).fetchall()
    assert [(row["source_slug"], row["target_slug"]) for row in remaining] == [("source", "shared")]


def test_body_is_full_text_searchable(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    index.update_record(_node(slug="t", title="Title", body="xylophone unique word", id="x"))
    row = index.connection.execute(
        "SELECT slug FROM wiki_fts WHERE wiki_fts MATCH 'xylophone'"
    ).fetchone()
    assert row is not None and row["slug"] == "t"


def test_increment_access_unknown_slug_noop(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    index.increment_access("ghost")
    assert index.get("ghost") is None


def test_get_by_type_and_all_slugs(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    index.update_record(_node(slug="a", type="entity", file_path="/a", id="1"))
    index.update_record(_node(slug="b", type="preference", file_path="/b", id="2"))
    assert index.get_all_slugs() == ["a", "b"]
    assert index.get_by_type("preference") == ["b"]


def test_reset_clears_everything(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    index.update_record(_node(slug="a", file_path="/a"))
    index.reset()
    assert index.count() == 0


def test_check_slug_rejects_injection(data_dir: Path) -> None:
    with pytest.raises(IndexManagerError):
        check_slug("'; DROP TABLE wiki_index; --")
    with pytest.raises(IndexManagerError):
        check_slug("")
    assert check_slug("Ruff-Linter") == "ruff-linter"


def test_set_get_meta_roundtrip(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    assert index.get_meta("missing") is None
    index.set_meta("k", "v1")
    index.set_meta("k", "v2")
    assert index.get_meta("k") == "v2"
