from pathlib import Path

import pytest

from memex.domain.errors import IndexManagerError
from memex.domain.models import WikiNode
from memex.infrastructure.index_manager import IndexManager, check_slug


def _node(**overrides: object) -> WikiNode:
    fields: dict[str, object] = {"type": "entity", "title": "T", "body": "b", "id": "x1"}
    fields.update(overrides)
    return WikiNode(**fields)  # type: ignore[arg-type]


def test_initialize_is_idempotent(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    index.initialize()
    index.initialize()
    assert index.get_meta("schema_version") == "1"


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


def test_remove_record_purges_links(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    index.initialize()
    node = _node(slug="t", file_path=str(data_dir / "t.md"))
    index.update_record(node)
    index.connection.execute("INSERT INTO wiki_links VALUES ('t', 'other')")
    index.connection.commit()

    index.remove_record("t")
    assert index.get("t") is None
    remaining = index.connection.execute("SELECT COUNT(*) AS n FROM wiki_links").fetchone()
    assert remaining["n"] == 0


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
