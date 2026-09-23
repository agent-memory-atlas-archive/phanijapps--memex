import os
from pathlib import Path

from memex.application.memory import Memex
from memex.domain.models import WriteInput
from memex.infrastructure.config import MemexConfig


def make_memex(data_dir: Path) -> Memex:
    return Memex(MemexConfig(data_dir=data_dir))


def test_detects_external_edit(data_dir: Path) -> None:
    from memex.infrastructure.store.watcher import IndexWatcher

    memex = make_memex(data_dir)
    from memex.domain.models import WriteInput

    memex.write(WriteInput(type="entity", title="Watched", body="original"))
    watcher = IndexWatcher(memex.wiki_store.wiki_dir, memex.index_manager, memex.wiki_store)
    assert watcher.check() == []

    page = data_dir / "docs/global/entities/watched.md"
    os.utime(page, None)
    assert watcher.check() == ["watched"]


def test_reindexes_real_content_changes(data_dir: Path) -> None:
    from memex.infrastructure.store.watcher import IndexWatcher

    memex = make_memex(data_dir)
    memex.write(WriteInput(type="entity", title="Watched", body="original"))
    watcher = IndexWatcher(
        memex.wiki_store.wiki_dir,
        memex.index_manager,
        memex.wiki_store,
        link_mgr=memex.link_manager,
    )

    page = data_dir / "docs/global/entities/watched.md"
    page.write_text(page.read_text().replace("original", "hand-edited"), encoding="utf-8")
    os.utime(page, None)

    assert watcher.reindex_changed() == 1
    row = memex.index_manager.get("watched")
    assert row is not None
    assert "hand-edited" in str(row["body"])


def test_reindexes_external_link_changes(data_dir: Path) -> None:
    from memex.infrastructure.store.watcher import IndexWatcher

    memex = make_memex(data_dir)
    memex.write(WriteInput(type="entity", title="Target", body="target body"))
    memex.write(WriteInput(type="entity", title="Watched", body="original"))
    watcher = IndexWatcher(
        memex.wiki_store.wiki_dir,
        memex.index_manager,
        memex.wiki_store,
        link_mgr=memex.link_manager,
    )

    page = data_dir / "docs/global/entities/watched.md"
    page.write_text(page.read_text().replace("original", "links to [[target]]"), encoding="utf-8")
    os.utime(page, None)

    assert watcher.reindex_changed() == 1
    assert memex.link_manager.link_exists("watched", "target")


def test_reindexes_description_only_edit(data_dir: Path) -> None:
    from memex.infrastructure.store.watcher import IndexWatcher

    memex = make_memex(data_dir)
    memex.write(
        WriteInput(
            type="entity",
            title="Watched",
            body="unchanged body",
            description="old signpost",
        )
    )
    watcher = IndexWatcher(
        memex.wiki_store.wiki_dir,
        memex.index_manager,
        memex.wiki_store,
        link_mgr=memex.link_manager,
    )

    page = data_dir / "docs/global/entities/watched.md"
    page.write_text(
        page.read_text().replace('description: "old signpost"', 'description: "new signpost"'),
        encoding="utf-8",
    )
    os.utime(page, None)

    assert watcher.reindex_changed() == 1
    row = memex.index_manager.get("watched")
    assert row is not None
    assert row["description"] == "new signpost"
    assert "unchanged body" in str(row["body"])


def test_touched_but_unchanged_skipped(data_dir: Path) -> None:
    from memex.infrastructure.store.watcher import IndexWatcher

    memex = make_memex(data_dir)
    memex.write(WriteInput(type="entity", title="Stable", body="same"))
    watcher = IndexWatcher(memex.wiki_store.wiki_dir, memex.index_manager, memex.wiki_store)

    page = data_dir / "docs/global/entities/stable.md"
    os.utime(page, (946684800, 946684800))  # old mtime, same content

    assert watcher.check() == ["stable"]
    assert watcher.reindex_changed() == 0


def test_deleted_page_removed_from_index(data_dir: Path) -> None:
    from memex.infrastructure.store.watcher import IndexWatcher

    memex = make_memex(data_dir)
    memex.write(WriteInput(type="entity", title="Doomed", body="bye"))
    watcher = IndexWatcher(memex.wiki_store.wiki_dir, memex.index_manager, memex.wiki_store)

    (data_dir / "docs/global/entities/doomed.md").unlink()
    watcher.reindex_changed()

    assert memex.index_manager.get("doomed") is None


def test_reindexes_duplicate_project_slug_by_namespace(data_dir: Path) -> None:
    from memex.infrastructure.store.watcher import IndexWatcher

    memex = make_memex(data_dir)
    first = memex.write(
        WriteInput(
            type="entity",
            title="Watched shared",
            body="first body",
            scope="project",
            project_id="a" * 24,
            project_label="One",
            project_locator="git-one",
        )
    )
    second = memex.write(
        WriteInput(
            type="entity",
            title="Watched shared",
            body="second body",
            scope="project",
            project_id="b" * 24,
            project_label="Two",
            project_locator="git-two",
        )
    )
    watcher = IndexWatcher(
        memex.wiki_store.wiki_dir,
        memex.index_manager,
        memex.wiki_store,
        link_mgr=memex.link_manager,
    )

    page = Path(first.file_path or "")
    page.write_text(page.read_text().replace("first body", "first changed"), encoding="utf-8")
    os.utime(page, None)

    assert first.slug == second.slug
    assert watcher.reindex_changed() == 1
    first_row = memex.index_manager.get(
        first.slug, scope="project", project_id="a" * 24, node_type="entity"
    )
    second_row = memex.index_manager.get(
        second.slug, scope="project", project_id="b" * 24, node_type="entity"
    )
    assert first_row is not None and "first changed" in str(first_row["body"])
    assert second_row is not None and "second body" in str(second_row["body"])


def test_start_stop_polling(data_dir: Path) -> None:
    from memex.infrastructure.store.watcher import IndexWatcher

    memex = make_memex(data_dir)
    watcher = IndexWatcher(
        memex.wiki_store.wiki_dir, memex.index_manager, memex.wiki_store, poll_interval=1
    )
    watcher.start_polling()
    assert watcher._thread is not None
    watcher.stop_polling()
    assert watcher._thread is None


def test_zero_interval_disables_polling(data_dir: Path) -> None:
    from memex.infrastructure.store.watcher import IndexWatcher

    memex = make_memex(data_dir)
    disabled = IndexWatcher(
        memex.wiki_store.wiki_dir, memex.index_manager, memex.wiki_store, poll_interval=0
    )
    disabled.start_polling()
    assert disabled._thread is None
