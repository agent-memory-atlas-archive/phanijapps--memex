from pathlib import Path

import pytest

from memex.domain.models import WikiNode
from memex.infrastructure.bm25_retriever import BM25Retriever
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
