from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from memex.domain.models import WikiNode
from memex.infrastructure.bm25_retriever import (
    MAX_QUERY_BYTES,
    MAX_QUERY_TOKENS,
    BM25Retriever,
)
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.wiki_store import WikiStore


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
        "INSERT INTO wiki_links (source_slug, target_slug) VALUES (?, ?)",
        (source.slug, target.slug),
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
