from pathlib import Path

import pytest

from eval.weighted_retriever import WeightedLexicalRetriever
from memex.domain.models import WikiNode
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.wiki_store import WikiStore


def _build_index(data_dir: Path, pages: list[tuple[str, str]]) -> IndexManager:
    store = WikiStore(data_dir)
    index = IndexManager(data_dir / "mem.db")
    for title, body in pages:
        index.update_record(store.write(WikiNode(type="entity", title=title, body=body, id="")))
    return index


def test_weighted_candidate_diversifies_duplicate_titles_and_records_access_once(
    data_dir: Path,
) -> None:
    index = _build_index(
        data_dir,
        [
            ("Alpha repeated", "alpha beta details"),
            ("Alpha repeated", "alpha beta details"),
            ("Alpha repeated", "alpha beta details"),
            ("Alpha second", "alpha beta details"),
            ("Alpha third", "alpha beta details"),
        ],
    )
    retriever = WeightedLexicalRetriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha beta", top_k=3)

    assert len(result.hits) == 3
    assert len({hit.slug for hit in result.hits}) == 3
    assert len({hit.title for hit in result.hits}) == 3
    assert [hit.rank for hit in result.hits] == [1, 2, 3]
    counts = {
        str(row["slug"]): int(row["access_count"])
        for row in index.connection.execute(
            "SELECT slug, access_count FROM wiki_index ORDER BY slug"
        ).fetchall()
    }
    assert sum(counts.values()) == 3
    assert {counts[hit.slug] for hit in result.hits} == {1}
    retriever.close()
    index.close()


def test_weighted_candidate_preserves_query_and_top_k_validation(data_dir: Path) -> None:
    index = _build_index(data_dir, [("Alpha", "alpha body")])
    retriever = WeightedLexicalRetriever(data_dir / "mem.db")

    with pytest.raises(ValueError, match="no searchable terms"):
        retriever.retrieve("!!!")
    with pytest.raises(ValueError, match="top_k"):
        retriever.retrieve("alpha", top_k=0)
    with pytest.raises(ValueError, match="top_k"):
        retriever.retrieve("alpha", top_k=101)

    retriever.close()
    index.close()


def test_weighted_candidate_prefers_title_match_over_repeated_body_match(
    data_dir: Path,
) -> None:
    index = _build_index(
        data_dir,
        [
            ("Alpha title", "neutral details"),
            ("Body repetition", "alpha alpha alpha"),
        ],
    )
    retriever = WeightedLexicalRetriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha", top_k=2)

    assert [hit.title for hit in result.hits] == ["Alpha title", "Body repetition"]
    retriever.close()
    index.close()


def test_weighted_candidate_uses_or_backoff_after_strict_results(data_dir: Path) -> None:
    index = _build_index(
        data_dir,
        [
            ("Exact", "alpha beta"),
            ("Alpha only", "alpha"),
            ("Beta only", "beta"),
        ],
    )
    retriever = WeightedLexicalRetriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha beta", top_k=3)

    assert result.hits[0].title == "Exact"
    assert {hit.title for hit in result.hits} == {"Exact", "Alpha only", "Beta only"}
    retriever.close()
    index.close()
