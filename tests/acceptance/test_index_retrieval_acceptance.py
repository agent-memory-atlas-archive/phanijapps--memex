"""Spec acceptance tests 6-12: links, index, BM25 retrieval."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from memex.domain.models import WikiNode
from memex.infrastructure.search.bm25_retriever import BM25Retriever
from memex.infrastructure.search.index_manager import SCHEMA_VERSION, IndexManager
from memex.infrastructure.search.link_manager import LinkManager
from memex.infrastructure.store.wiki_store import WikiStore


def _node(**overrides: object) -> WikiNode:
    fields: dict[str, object] = {
        "type": "entity",
        "title": "Placeholder",
        "body": "placeholder body",
        "id": "",
    }
    fields.update(overrides)
    return WikiNode(**fields)  # type: ignore[arg-type]


@pytest.fixture
def components(data_dir: Path) -> dict[str, object]:
    store = WikiStore(data_dir)
    index = IndexManager(data_dir / "mem.db")
    index.initialize()
    links = LinkManager(index.connection, store.wiki_dir)
    retriever = BM25Retriever(data_dir / "mem.db")
    return {"store": store, "index": index, "links": links, "retriever": retriever}


def _write_indexed(store: WikiStore, index: IndexManager, **overrides: object) -> WikiNode:
    node = store.write(_node(**overrides))
    index.update_record(node)
    return node


def test_wiki_link_parsing(components: dict[str, object]) -> None:
    store = components["store"]
    assert isinstance(store, WikiStore)
    index = components["index"]
    assert isinstance(index, IndexManager)
    links = components["links"]
    assert isinstance(links, LinkManager)

    target = _write_indexed(store, index, title="Python 3.12", body="Python version.")
    source = _write_indexed(
        store,
        index,
        title="Ruff linter",
        body="Ruff works with [[python-3-12]] and [[missing-page]].",
    )

    stored = store.read(source.slug)
    assert stored is not None
    # Body references are graph edges, not declared front-matter relations.
    assert stored.links == []

    links.sync_node(stored)
    assert links.get_outgoing(source.slug) == ["missing-page", "python-3-12"]
    assert links.get_backlinks(target.slug) == [source.slug]
    assert links.link_exists(source.slug, target.slug)
    assert links.validate_links(source.slug) == ["missing-page"]


def test_index_build_and_query(components: dict[str, object]) -> None:
    store = components["store"]
    assert isinstance(store, WikiStore)
    index = components["index"]
    assert isinstance(index, IndexManager)
    retriever = components["retriever"]
    assert isinstance(retriever, BM25Retriever)

    nodes = [
        store.write(_node(title="SQLite database", body="SQLite stores rows in tables.", id="i1")),
        store.write(_node(title="Ruff linter", body="Ruff lints Python quickly.", id="i2")),
    ]
    index.build(nodes)

    result = retriever.retrieve("sqlite")
    assert len(result.hits) == 1
    hit = result.hits[0]
    assert hit.slug == "sqlite-database"
    assert hit.rank == 1
    assert hit.snippet
    assert hit.node_type == "entity"


def test_index_rebuild_from_wiki(components: dict[str, object]) -> None:
    store = components["store"]
    assert isinstance(store, WikiStore)
    index = components["index"]
    assert isinstance(index, IndexManager)
    retriever = components["retriever"]
    assert isinstance(retriever, BM25Retriever)

    for i in range(5):
        store.write(_node(title=f"Node {i}", body=f"body number {i} unique{i}", id=f"r{i}"))

    index.close()
    retriever.close()
    (store.data_dir / "mem.db").unlink()

    fresh_index = IndexManager(store.data_dir / "mem.db")
    fresh_index.initialize()
    scanned = store.scan_all()
    count = fresh_index.build(scanned)
    fresh_index.set_meta("last_index_rebuild", "2026-09-15T00:00:00Z")

    assert count == 5
    assert fresh_index.count() == 5
    assert fresh_index.get_meta("last_index_rebuild") == "2026-09-15T00:00:00Z"
    assert fresh_index.get_meta("schema_version") == SCHEMA_VERSION


def test_bm25_scoring(components: dict[str, object]) -> None:
    store = components["store"]
    assert isinstance(store, WikiStore)
    index = components["index"]
    assert isinstance(index, IndexManager)
    retriever = components["retriever"]
    assert isinstance(retriever, BM25Retriever)

    nodes = [
        store.write(_node(title="Widget alpha", body="kubernetes orchestration", id="b1")),
        store.write(
            _node(
                title="Widget beta",
                body="kubernetes kubernetes orchestration twice mentioned",
                id="b2",
            )
        ),
        store.write(_node(title="Widget gamma", body="docker containers", id="b3")),
        store.write(_node(title="Widget delta", body="rust compiler", id="b4")),
        store.write(_node(title="Widget epsilon", body="python interpreter", id="b5")),
    ]
    index.build(nodes)

    result = retriever.retrieve("kubernetes")
    assert [hit.slug for hit in result.hits] == ["widget-beta", "widget-alpha"]
    # Lower bm25 score = better; the node with more term occurrences ranks first.
    assert result.hits[0].score < result.hits[1].score
    assert result.search_engine == "semantic-and-fallback-fts5"
    assert result.total_indexed == 5


def test_recall_increments_access(components: dict[str, object]) -> None:
    store = components["store"]
    assert isinstance(store, WikiStore)
    index = components["index"]
    assert isinstance(index, IndexManager)
    retriever = components["retriever"]
    assert isinstance(retriever, BM25Retriever)

    _write_indexed(store, index, title="Access counter", body="count my recalls please", id="c1")

    retriever.retrieve("counter")
    row_after_first = index.get("access-counter")
    assert row_after_first is not None
    assert row_after_first["access_count"] == 1
    first_access = row_after_first["last_access"]

    time.sleep(1.05)
    retriever.retrieve("counter")
    row_after_second = index.get("access-counter")
    assert row_after_second is not None
    assert row_after_second["access_count"] == 2
    assert row_after_second["last_access"] > first_access


def test_recall_filters(components: dict[str, object]) -> None:
    store = components["store"]
    assert isinstance(store, WikiStore)
    index = components["index"]
    assert isinstance(index, IndexManager)
    retriever = components["retriever"]
    assert isinstance(retriever, BM25Retriever)

    _write_indexed(store, index, title="Ruff entity", body="linting tool", id="f1", tags=["tool"])
    time.sleep(1.05)
    _write_indexed(
        store,
        index,
        title="Ruff preference",
        body="linting preference",
        id="f2",
        type="preference",
        tags=["style"],
    )

    by_type = retriever.retrieve("linting", node_type="preference")
    assert [hit.slug for hit in by_type.hits] == ["ruff-preference"]

    by_tag = retriever.retrieve("linting", tags=["tool"])
    assert [hit.slug for hit in by_tag.hits] == ["ruff-entity"]

    recent = retriever.retrieve(
        "linting", time_range=("2100-01-01T00:00:00Z", "2101-01-01T00:00:00Z")
    )
    assert recent.hits == []

    both = retriever.retrieve("linting")
    assert len(both.hits) == 2


def test_recall_snippet_source(components: dict[str, object]) -> None:
    store = components["store"]
    assert isinstance(store, WikiStore)
    index = components["index"]
    assert isinstance(index, IndexManager)
    retriever = components["retriever"]
    assert isinstance(retriever, BM25Retriever)

    _write_indexed(
        store,
        index,
        title="Kubernetes Deployment Probe",
        body="no mention of that word here at all",
        id="s1",
    )

    result = retriever.retrieve("probe")
    assert len(result.hits) == 1
    assert result.hits[0].snippet_source == "title"


def test_recall_finds_project_page_by_description_only(components: dict[str, object]) -> None:
    store = components["store"]
    assert isinstance(store, WikiStore)
    index = components["index"]
    assert isinstance(index, IndexManager)
    retriever = components["retriever"]
    assert isinstance(retriever, BM25Retriever)

    node = _write_indexed(
        store,
        index,
        title="Release notes",
        body="ordinary body with no rare words",
        id="d1",
        description="quilting retrospectives across releases",
        scope="project",
        project_id="a" * 24,
    )

    result = retriever.retrieve("quilting retrospective", scope="project", project_id="a" * 24)

    assert [hit.slug for hit in result.hits] == [node.slug]
    hit = result.hits[0]
    assert hit.snippet_source == "description"
    assert "<mark>quilting</mark>" in hit.snippet
    assert hit.description == "quilting retrospectives across releases"


def test_forced_rebuild_reproduces_description_hit(components: dict[str, object]) -> None:
    store = components["store"]
    assert isinstance(store, WikiStore)
    index = components["index"]
    assert isinstance(index, IndexManager)
    retriever = components["retriever"]
    assert isinstance(retriever, BM25Retriever)

    _write_indexed(
        store,
        index,
        title="Onboarding flow",
        body="body text",
        id="d2",
        description="xylophone onboarding checklist",
    )
    assert [hit.slug for hit in retriever.retrieve("xylophone").hits] == ["onboarding-flow"]

    index.reset()
    assert retriever.retrieve("xylophone").hits == []

    rebuilt = index.build(store.scan_all())
    assert rebuilt == 1
    second = retriever.retrieve("xylophone")
    assert [hit.slug for hit in second.hits] == ["onboarding-flow"]
    assert second.hits[0].snippet_source == "description"
