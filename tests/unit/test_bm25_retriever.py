from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from memex.domain.models import WikiNode
from memex.infrastructure.bm25_retriever import (
    MAX_QUERY_BYTES,
    MAX_QUERY_TOKENS,
    BM25Retriever,
    production_ranker_metadata,
)
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.wiki_store import WikiStore


def _node(
    title: str,
    body: str,
    *,
    slug: str = "",
    description: str = "",
) -> WikiNode:
    return WikiNode(
        type="entity", title=title, body=body, id=slug, slug=slug, description=description
    )


def _index_nodes(data_dir: Path, nodes: list[WikiNode]) -> IndexManager:
    store = WikiStore(data_dir)
    index = IndexManager(data_dir / "mem.db")
    for node in nodes:
        index.update_record(store.write(node))
    return index


@pytest.fixture
def indexed(data_dir: Path) -> BM25Retriever:
    store = WikiStore(data_dir)
    index = IndexManager(data_dir / "mem.db")
    index.initialize()
    retriever = BM25Retriever(data_dir / "mem.db")
    node = store.write(
        WikiNode(type="entity", title="Alpha Node", body="the quick brown fox", id="")
    )
    index.update_record(node)
    return retriever


def test_empty_query_raises(indexed: BM25Retriever) -> None:
    with pytest.raises(ValueError, match="no searchable terms"):
        indexed.retrieve("!!! ???")

    with pytest.raises(ValueError, match="no searchable terms"):
        indexed.search_fts("---", 5)


def test_query_byte_cap_blocks_semantic_and_legacy_match_builders(
    indexed: BM25Retriever,
) -> None:
    query = "leaksecret " + ("é" * MAX_QUERY_BYTES)

    with pytest.raises(ValueError, match=f"exceeds {MAX_QUERY_BYTES} UTF-8 bytes") as retrieve:
        indexed.retrieve(query)
    with pytest.raises(ValueError, match=f"exceeds {MAX_QUERY_BYTES} UTF-8 bytes") as legacy:
        indexed.search_fts(query, 5)

    assert "leaksecret" not in str(retrieve.value)
    assert "leaksecret" not in str(legacy.value)


def test_query_token_cap_blocks_semantic_and_legacy_match_builders(
    indexed: BM25Retriever,
) -> None:
    query = " ".join(f"term{index}" for index in range(MAX_QUERY_TOKENS + 1))

    with pytest.raises(ValueError, match="too many searchable terms") as retrieve:
        indexed.retrieve(query)
    with pytest.raises(ValueError, match="too many searchable terms") as legacy:
        indexed.retrieve_legacy_or(query)

    assert "term0" not in str(retrieve.value)
    assert "term0" not in str(legacy.value)


def test_fts_injection_is_neutralized(indexed: BM25Retriever) -> None:
    result = indexed.retrieve("quick* OR 1=1")
    assert result.total_indexed == 1
    injection = indexed.search_fts("NEAR(fox brown, 5)", 5)
    assert isinstance(injection, list)


def test_top_k_bounds(indexed: BM25Retriever) -> None:
    with pytest.raises(ValueError, match="top_k"):
        indexed.retrieve("quick", top_k=0)
    with pytest.raises(ValueError, match="top_k"):
        indexed.retrieve("quick", top_k=101)


def test_search_fts_returns_pairs(indexed: BM25Retriever) -> None:
    pairs = indexed.search_fts("quick brown", 5)
    assert pairs and pairs[0][0] == "alpha-node"
    assert isinstance(pairs[0][1], float)


def test_production_ranker_metadata_reports_promoted_strategy() -> None:
    metadata = production_ranker_metadata()

    assert metadata["name"] == "semantic-and-fallback-fts5"
    assert metadata["query_strategy"] == "strict-and-weighted-fts5"
    assert metadata["zero_hit_fallback"] == "broad-or-weighted-fts5"
    assert metadata["column_weights"] == {
        "slug": 1.0,
        "title": 1.0,
        "description": 2.0,
        "body": 2.0,
        "tags": 1.0,
    }
    assert metadata["snippet_tokens"] == 12


def test_description_only_match_returns_description_snippet(data_dir: Path) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node(
                "Plain page",
                "ordinary body words",
                slug="plain-page",
                description="quilting pattern archive for agents",
            )
        ],
    )
    retriever = BM25Retriever(data_dir / "mem.db")

    result = retriever.retrieve("quilting", top_k=5)

    assert [hit.slug for hit in result.hits] == ["plain-page"]
    hit = result.hits[0]
    assert hit.snippet_source == "description"
    assert "<mark>quilting</mark>" in hit.snippet
    assert hit.description == "quilting pattern archive for agents"
    retriever.close()
    index.close()


def test_body_match_still_wins_snippet_over_description(data_dir: Path) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node(
                "Mixed page",
                "body carries xylophone",
                slug="mixed-page",
                description="xylophone also in description",
            )
        ],
    )
    retriever = BM25Retriever(data_dir / "mem.db")

    result = retriever.retrieve("xylophone", top_k=5)

    assert [hit.slug for hit in result.hits] == ["mixed-page"]
    assert result.hits[0].snippet_source == "body"
    retriever.close()
    index.close()


def test_empty_description_pages_keep_existing_ranking(data_dir: Path) -> None:
    # Same fixture shape as the pre-description winner tests: identical
    # titles/bodies with no descriptions must keep the deterministic order.
    index = _index_nodes(
        data_dir,
        [
            _node("Beta only", "beta", slug="beta-only"),
            _node("Exact", "alpha beta", slug="exact"),
            _node("Alpha only", "alpha", slug="alpha-only"),
        ],
    )
    retriever = BM25Retriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha beta", top_k=10)

    assert [hit.slug for hit in result.hits] == ["exact"]
    assert result.hits[0].description == ""
    retriever.close()
    index.close()


def test_retrieve_removes_semantic_scaffolding_and_deduplicates_tokens(
    data_dir: Path,
) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node(
                "Query engine rate limiting polling chart rest nodes",
                "query engine rate limiting polling chart rest nodes",
                slug="target",
            )
        ],
    )
    retriever = BM25Retriever(data_dir / "mem.db")
    statements: list[str] = []
    retriever._conn.set_trace_callback(statements.append)

    retriever.retrieve(
        "How does query-engine handle rate limiting instead of polling, "
        "why is chart showing switch from REST? How many nodes nodes!",
        top_k=3,
    )

    assert any(
        "'query AND engine AND rate AND limiting AND polling AND chart AND rest AND nodes'"
        in statement
        for statement in statements
    )
    retriever.close()
    index.close()


def test_retrieve_keeps_showing_when_it_is_content(data_dir: Path) -> None:
    index = _index_nodes(data_dir, [_node("Showing example", "showing details")])
    retriever = BM25Retriever(data_dir / "mem.db")

    result = retriever.retrieve("showing", top_k=3)

    assert [hit.title for hit in result.hits] == ["Showing example"]
    retriever.close()
    index.close()


def test_retrieve_uses_raw_tokens_when_scaffolding_filters_every_token(
    data_dir: Path,
) -> None:
    index = _index_nodes(data_dir, [_node("Scaffold only", "how does handle")])
    retriever = BM25Retriever(data_dir / "mem.db")
    statements: list[str] = []
    retriever._conn.set_trace_callback(statements.append)

    result = retriever.retrieve("how does handle", top_k=3)

    assert [hit.title for hit in result.hits] == ["Scaffold only"]
    assert any("'how AND does AND handle'" in statement for statement in statements)
    retriever.close()
    index.close()


def test_retrieve_stops_after_strict_match_succeeds(data_dir: Path) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node("Exact", "alpha beta", slug="exact"),
            _node("Alpha only", "alpha", slug="alpha-only"),
            _node("Beta only", "beta", slug="beta-only"),
        ],
    )
    retriever = BM25Retriever(data_dir / "mem.db")
    statements: list[str] = []
    retriever._conn.set_trace_callback(statements.append)

    result = retriever.retrieve("alpha beta", top_k=10)

    assert [hit.slug for hit in result.hits] == ["exact"]
    assert sum("wiki_fts MATCH" in statement for statement in statements) == 1
    retriever.close()
    index.close()


def test_retrieve_runs_or_fallback_only_after_zero_strict_hits(data_dir: Path) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node("Alpha only", "alpha", slug="alpha-only"),
            _node("Beta only", "beta", slug="beta-only"),
        ],
    )
    retriever = BM25Retriever(data_dir / "mem.db")
    statements: list[str] = []
    retriever._conn.set_trace_callback(statements.append)

    result = retriever.retrieve("alpha beta", top_k=10)

    assert [hit.slug for hit in result.hits] == ["alpha-only", "beta-only"]
    assert any("'alpha AND beta'" in statement for statement in statements)
    assert any("'alpha OR beta'" in statement for statement in statements)
    retriever.close()
    index.close()


def test_retrieve_preserves_duplicate_titles_with_stable_ranks(data_dir: Path) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node("Alpha repeated", "alpha beta details", slug="alpha-a"),
            _node("Alpha repeated", "alpha beta details", slug="alpha-b"),
            _node("Alpha repeated", "alpha beta details", slug="alpha-c"),
        ],
    )
    retriever = BM25Retriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha beta", top_k=3)

    assert result.search_engine == "semantic-and-fallback-fts5"
    assert [hit.slug for hit in result.hits] == ["alpha-a", "alpha-b", "alpha-c"]
    assert [hit.title for hit in result.hits] == ["Alpha repeated"] * 3
    assert [hit.rank for hit in result.hits] == [1, 2, 3]
    retriever.close()
    index.close()


def test_retrieve_without_access_is_pure_and_retrieve_records_once(data_dir: Path) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node("Beta", "alpha", slug="beta"),
            _node("Alpha", "alpha", slug="alpha"),
            _node("Gamma", "alpha", slug="gamma"),
        ],
    )
    retriever = BM25Retriever(data_dir / "mem.db")

    unrecorded = retriever.retrieve_without_access("alpha", top_k=3)
    before = index.connection.execute(
        "SELECT SUM(access_count) AS total FROM wiki_index"
    ).fetchone()
    recorded = retriever.retrieve("alpha", top_k=3)
    counts = {
        str(row["slug"]): int(row["access_count"])
        for row in index.connection.execute(
            "SELECT slug, access_count FROM wiki_index ORDER BY slug"
        ).fetchall()
    }

    assert [hit.slug for hit in unrecorded.hits] == ["alpha", "beta", "gamma"]
    assert int(before["total"]) == 0
    assert [hit.rank for hit in recorded.hits] == [1, 2, 3]
    assert counts == {"alpha": 1, "beta": 1, "gamma": 1}
    retriever.close()
    index.close()


def test_concurrent_retrieve_hydrates_links_consistently(data_dir: Path) -> None:
    store = WikiStore(data_dir)
    index = IndexManager(data_dir / "mem.db")
    index.initialize()
    retriever = BM25Retriever(data_dir / "mem.db")
    source = store.write(
        WikiNode(
            type="entity",
            title="Alpha Node",
            body="the quick brown fox links to [[target-node]]",
            id="",
        )
    )
    target = store.write(WikiNode(type="entity", title="Target Node", body="linked target", id=""))
    index.build([source, target])
    index.connection.execute(
        "INSERT INTO wiki_links (source_scope, source_project_id, source_slug, target_slug)"
        " VALUES (?, ?, ?, ?)",
        (source.scope, source.project_id or "", source.slug, target.slug),
    )
    index.connection.commit()

    try:

        def retrieve_links(_: int) -> list[str]:
            return retriever.retrieve("quick").hits[0].links

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(retrieve_links, range(64)))

        assert results == [[target.slug]] * 64
    finally:
        retriever.close()
        index.close()
