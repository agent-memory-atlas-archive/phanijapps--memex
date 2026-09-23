from pathlib import Path

import pytest

from memex.domain.errors import IndexManagerError
from memex.domain.models import WikiNode
from memex.infrastructure.search.index_manager import IndexManager
from memex.infrastructure.search.link_manager import LinkManager


def _link_manager(data_dir: Path) -> LinkManager:
    index = IndexManager(data_dir / "mem.db")
    return LinkManager(index.connection, data_dir / "docs")


def test_outgoing_links_refuse_ambiguous_source_slug(data_dir: Path) -> None:
    links = _link_manager(data_dir)
    links.sync_links("shared", "one [[target]]", source_scope="project", source_project_id="a")
    links.sync_links("shared", "two [[target]]", source_scope="project", source_project_id="b")

    with pytest.raises(IndexManagerError, match="ambiguous link source slug"):
        links.get_outgoing("shared")

    assert links.get_outgoing("shared", source_scope="project", source_project_id="a") == ["target"]


def test_link_exists_refuses_ambiguous_source_slug(data_dir: Path) -> None:
    links = _link_manager(data_dir)
    links.sync_links("shared", "one [[target]]", source_scope="project", source_project_id="a")
    links.sync_links("shared", "two [[target]]", source_scope="project", source_project_id="b")

    with pytest.raises(IndexManagerError, match="ambiguous link source slug"):
        links.link_exists("shared", "target")

    assert links.link_exists("shared", "target", source_scope="project", source_project_id="a")


def test_link_exists_refuses_ambiguity_before_target_filter(data_dir: Path) -> None:
    links = _link_manager(data_dir)
    links.sync_links("shared", "[[target]]", source_scope="project", source_project_id="a")
    links.sync_links("shared", "[[other]]", source_scope="project", source_project_id="b")

    with pytest.raises(IndexManagerError, match="ambiguous link source slug"):
        links.link_exists("shared", "target")
    with pytest.raises(IndexManagerError, match="ambiguous link source slug"):
        links.link_exists("shared", "target", source_scope="project")

    assert links.link_exists("shared", "target", source_scope="project", source_project_id="a")
    assert not links.link_exists("shared", "target", source_scope="project", source_project_id="b")


def test_link_queries_refuse_same_slug_page_without_links(data_dir: Path) -> None:
    index = IndexManager(data_dir / "mem.db")
    for project_id in ("a" * 24, "b" * 24):
        index.update_record(
            WikiNode(
                type="entity",
                title="Shared",
                body="",
                id=project_id,
                slug="shared",
                scope="project",
                project_id=project_id,
                file_path=str(data_dir / "docs/projects" / project_id / "entities/shared.md"),
            )
        )
    links = LinkManager(index.connection, data_dir / "docs")
    links.sync_links("shared", "[[target]]", source_scope="project", source_project_id="a" * 24)

    with pytest.raises(IndexManagerError, match="ambiguous link source slug"):
        links.get_outgoing("shared")
    with pytest.raises(IndexManagerError, match="ambiguous link source slug"):
        links.link_exists("shared", "target", source_scope="project")
    with pytest.raises(IndexManagerError, match="ambiguous link source slug"):
        links.get_backlinks("target")
    with pytest.raises(IndexManagerError, match="ambiguous link source slug"):
        links.get_link_graph()

    assert links.link_exists("shared", "target", source_scope="project", source_project_id="a" * 24)
    assert not links.link_exists(
        "shared", "target", source_scope="project", source_project_id="b" * 24
    )


def test_invalid_link_target_is_broken_without_globbing(data_dir: Path) -> None:
    docs = data_dir / "docs"
    docs.mkdir(parents=True)
    links = _link_manager(data_dir)

    assert links._page_exists("[bad") is False
