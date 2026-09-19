"""Acceptance coverage for project namespaces and rebuildable scoped search."""

from __future__ import annotations

from pathlib import Path

import pytest

from memex.application.memory import Memex
from memex.domain.errors import IndexManagerError, WikiStoreError
from memex.domain.models import WriteInput
from memex.infrastructure.config import MemexConfig


def test_scoped_recall_and_force_rebuild_keep_duplicate_project_slugs(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        first = memex.write(
            WriteInput(
                type="entity",
                title="Shared name",
                body="project one marker",
                scope="project",
                project_id="a" * 24,
                project_label="Project one",
            )
        )
        second = memex.write(
            WriteInput(
                type="entity",
                title="Shared name",
                body="project two marker",
                scope="project",
                project_id="b" * 24,
                project_label="Project two",
            )
        )
        assert first.slug == second.slug

        local = memex.recall("marker", scope="project", project_id="a" * 24)
        assert [(hit.project_id, hit.slug) for hit in local.hits] == [("a" * 24, "shared-name")]

        memex.rebuild_index(force=True)
        global_result = memex.recall("marker", scope="global")
        assert {hit.project_id for hit in global_result.hits} == {"a" * 24, "b" * 24}
    finally:
        memex.close()


def test_force_rebuild_keeps_legacy_project_directory_retrievable(data_dir: Path) -> None:
    project_id = "a" * 24
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        stored = memex.write(
            WriteInput(
                type="entity",
                title="Legacy scoped",
                body="legacy project marker",
                scope="project",
                project_id=project_id,
                project_label="Legacy project",
            )
        )
        assert stored.file_path == str(
            data_dir / "docs/projects" / project_id / "entities/legacy-scoped.md"
        )

        memex.index_manager.reset()
        memex.rebuild_index(force=True)

        result = memex.recall("legacy marker", scope="project", project_id=project_id)
        assert [(hit.project_id, hit.slug) for hit in result.hits] == [
            (project_id, "legacy-scoped")
        ]
    finally:
        memex.close()


def test_force_rebuild_refuses_duplicate_same_project_key(data_dir: Path) -> None:
    project_id = "a" * 24
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        stored = memex.write(
            WriteInput(
                type="entity",
                title="Mixed duplicate",
                body="ambiguous project marker",
                scope="project",
                project_id=project_id,
                project_label="Readable project",
                project_locator="git-memex",
            )
        )
        duplicate = data_dir / "docs/projects" / project_id / "entities/mixed-duplicate.md"
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text(Path(stored.file_path or "").read_text(encoding="utf-8"))

        with pytest.raises(WikiStoreError, match="ambiguous wiki page namespace"):
            memex.rebuild_index(force=True)
    finally:
        memex.close()


def test_links_are_owned_by_duplicate_project_slug_namespace(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        first = memex.write(
            WriteInput(
                type="entity",
                title="Shared source",
                body="first project links [[first-target]]",
                scope="project",
                project_id="a" * 24,
                project_label="Project one",
                project_locator="git-one",
            )
        )
        second = memex.write(
            WriteInput(
                type="entity",
                title="Shared source",
                body="second project links [[second-target]]",
                scope="project",
                project_id="b" * 24,
                project_label="Project two",
                project_locator="git-two",
            )
        )

        first_links = memex.recall("first project", scope="project", project_id="a" * 24).hits[0]
        second_links = memex.recall("second project", scope="project", project_id="b" * 24).hits[0]

        assert first.slug == second.slug
        assert first_links.links == ["first-target"]
        assert second_links.links == ["second-target"]
    finally:
        memex.close()


def test_scoped_delete_preserves_backlinks_to_remaining_duplicate_target_slug(
    data_dir: Path,
) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        memex.write(WriteInput(type="entity", title="Source", body="links [[shared-target]]"))
        memex.write(
            WriteInput(
                type="entity",
                title="Shared target",
                body="first project target",
                scope="project",
                project_id="a" * 24,
                project_label="Project one",
                project_locator="git-one",
            )
        )
        memex.write(
            WriteInput(
                type="entity",
                title="Shared target",
                body="second project target",
                scope="project",
                project_id="b" * 24,
                project_label="Project two",
                project_locator="git-two",
            )
        )

        memex.index_manager.remove_record(
            "shared-target", scope="project", project_id="a" * 24, node_type="entity"
        )
        memex.link_manager.remove_slug(
            "shared-target", source_scope="project", source_project_id="a" * 24
        )

        assert memex.link_manager.get_backlinks("shared-target") == ["source"]
    finally:
        memex.close()


def test_slug_only_link_views_refuse_duplicate_source_namespaces(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        memex.write(
            WriteInput(
                type="entity",
                title="Shared source",
                body="first project links [[target]]",
                scope="project",
                project_id="a" * 24,
                project_label="Project one",
                project_locator="git-one",
            )
        )
        memex.write(
            WriteInput(
                type="entity",
                title="Shared source",
                body="second project links [[target]]",
                scope="project",
                project_id="b" * 24,
                project_label="Project two",
                project_locator="git-two",
            )
        )

        with pytest.raises(IndexManagerError, match="ambiguous link source slug"):
            memex.link_manager.get_backlinks("target")
        with pytest.raises(IndexManagerError, match="ambiguous link source slug"):
            memex.link_manager.get_link_graph()
    finally:
        memex.close()


def test_status_handles_duplicate_project_slugs(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        memex.write(
            WriteInput(
                type="entity",
                title="Status shared",
                body="first status marker",
                scope="project",
                project_id="a" * 24,
                project_label="Project one",
                project_locator="git-one",
            )
        )
        memex.write(
            WriteInput(
                type="entity",
                title="Status shared",
                body="second status marker",
                scope="project",
                project_id="b" * 24,
                project_label="Project two",
                project_locator="git-two",
            )
        )

        assert memex.status()["index_stale_rows"] == 0
    finally:
        memex.close()


def test_opening_pre_namespace_index_rebuilds_from_markdown_before_recall(
    data_dir: Path,
) -> None:
    import sqlite3

    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        memex.write(WriteInput(type="entity", title="Old index", body="legacy marker"))
    finally:
        memex.close()

    (data_dir / "mem.db").unlink()
    connection = sqlite3.connect(data_dir / "mem.db")
    connection.execute("CREATE TABLE wiki_index (id TEXT PRIMARY KEY, slug TEXT NOT NULL)")
    connection.commit()
    connection.close()

    reopened = Memex(MemexConfig(data_dir=data_dir))
    try:
        result = reopened.recall("legacy marker")
        assert [hit.slug for hit in result.hits] == ["old-index"]
    finally:
        reopened.close()


def test_opening_pre_namespace_links_rebuilds_markdown_links(
    data_dir: Path,
) -> None:
    import sqlite3

    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        memex.write(WriteInput(type="entity", title="Target", body="target body"))
        memex.write(WriteInput(type="entity", title="Source", body="links to [[target]]"))
    finally:
        memex.close()

    connection = sqlite3.connect(data_dir / "mem.db")
    connection.execute("DROP TABLE wiki_links")
    connection.execute("CREATE TABLE wiki_links (source_slug TEXT, target_slug TEXT)")
    connection.commit()
    connection.close()

    reopened = Memex(MemexConfig(data_dir=data_dir))
    try:
        assert reopened.link_manager.link_exists("source", "target")
    finally:
        reopened.close()


def test_project_metadata_cannot_persist_a_remote_or_absolute_path(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        with pytest.raises(ValueError, match="opaque"):
            memex.write(
                WriteInput(
                    type="entity",
                    title="Unsafe project",
                    body="should not be written",
                    scope="project",
                    project_id="git@internal.example:team/repo.git",
                )
            )
        assert not list((data_dir / "docs").rglob("*.md"))
    finally:
        memex.close()
