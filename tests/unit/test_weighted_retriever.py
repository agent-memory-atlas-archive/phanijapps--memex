from pathlib import Path

import pytest

from eval.candidates import RankedCandidate
from eval.weighted_retriever import SinglePassWeightedFts5Retriever, WeightedLexicalRetriever
from memex.domain.models import WikiNode
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.wiki_store import WikiStore


def _build_index(data_dir: Path, pages: list[tuple[str, str]]) -> IndexManager:
    store = WikiStore(data_dir)
    index = IndexManager(data_dir / "mem.db")
    for title, body in pages:
        index.update_record(store.write(WikiNode(type="entity", title=title, body=body, id="")))
    return index


def _index_nodes(data_dir: Path, nodes: list[WikiNode]) -> IndexManager:
    store = WikiStore(data_dir)
    index = IndexManager(data_dir / "mem.db")
    for node in nodes:
        index.update_record(store.write(node))
    return index


def _node(
    title: str,
    body: str,
    *,
    slug: str = "",
    tags: list[str] | None = None,
    status: str = "active",
) -> WikiNode:
    return WikiNode(
        type="entity",
        title=title,
        body=body,
        id=slug or "",
        slug=slug,
        tags=tags or [],
        status=status,
    )


def test_multichannel_rrf_searches_fields_independently(data_dir: Path) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node("Atlas title", "neutral details"),
            _node("Body only", "atlas details"),
            _node("Tagged only", "neutral details", tags=["atlas"]),
            _node("Stable identifier", "neutral details", slug="atlas-identifier"),
        ],
    )
    retriever = WeightedLexicalRetriever(data_dir / "mem.db")

    result = retriever.retrieve("atlas", top_k=10)

    assert result.search_engine == "field-channel-rrf-k60"
    assert {hit.title for hit in result.hits} == {
        "Atlas title",
        "Body only",
        "Tagged only",
        "Stable identifier",
    }
    retriever.close()
    index.close()


def test_multichannel_rrf_overfetches_before_k60_fusion(data_dir: Path) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node("Atlas title blocker", "neutral", slug="aardvark-title"),
            _node("Body blocker", "atlas", slug="aardvark-body"),
            _node("Slug blocker", "neutral", slug="atlas-aardvark"),
            _node("Atlas target", "atlas", slug="atlas-target"),
        ],
    )
    retriever = WeightedLexicalRetriever(data_dir / "mem.db")

    result = retriever.retrieve("atlas", top_k=1)

    assert [hit.slug for hit in result.hits] == ["atlas-target"]
    retriever.close()
    index.close()


def test_multichannel_rrf_deduplicates_with_stable_ties(data_dir: Path) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node("Beta", "atlas"),
            _node("Alpha", "atlas"),
            _node("Gamma", "atlas"),
        ],
    )
    retriever = WeightedLexicalRetriever(data_dir / "mem.db")

    first = retriever.retrieve("atlas", top_k=3)
    second = retriever.retrieve("atlas", top_k=3)

    assert [hit.slug for hit in first.hits] == ["alpha", "beta", "gamma"]
    assert [hit.slug for hit in second.hits] == ["alpha", "beta", "gamma"]
    assert [hit.rank for hit in first.hits] == [1, 2, 3]
    retriever.close()
    index.close()


def test_single_pass_weighted_fts5_retains_duplicate_title_multi_relevance(
    data_dir: Path,
) -> None:
    index = _build_index(
        data_dir,
        [
            ("Alpha repeated", "alpha beta details"),
            ("Alpha repeated", "alpha beta details"),
            ("Alpha repeated", "alpha beta details"),
        ],
    )
    retriever = SinglePassWeightedFts5Retriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha beta", top_k=3)

    assert result.search_engine == "single-pass-weighted-fts5"
    assert [hit.title for hit in result.hits] == [
        "Alpha repeated",
        "Alpha repeated",
        "Alpha repeated",
    ]
    assert [hit.rank for hit in result.hits] == [1, 2, 3]
    retriever.close()
    index.close()


def test_single_pass_weighted_fts5_uses_one_overfetched_search_call(
    data_dir: Path,
) -> None:
    class SpyRetriever(SinglePassWeightedFts5Retriever):
        def __init__(self, db_path: Path) -> None:
            super().__init__(db_path)
            self.search_calls: list[tuple[tuple[str, ...], int]] = []

        def _search_candidates(
            self,
            tokens: list[str],
            limit: int,
            now: str,
        ) -> list[RankedCandidate]:
            del now
            self.search_calls.append((tuple(tokens), limit))
            return [RankedCandidate("alpha", 1, -1.0)]

    index = _index_nodes(data_dir, [_node("Alpha", "alpha beta", slug="alpha")])
    retriever = SpyRetriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha beta", top_k=3)

    assert [hit.slug for hit in result.hits] == ["alpha"]
    assert retriever.search_calls == [(("alpha", "beta"), 12)]
    retriever.close()
    index.close()


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


def test_weighted_candidate_searches_all_query_terms(data_dir: Path) -> None:
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

    assert {hit.title for hit in result.hits} == {"Exact", "Alpha only", "Beta only"}
    retriever.close()
    index.close()


def test_eligibility_filters_apply_before_source_limit(data_dir: Path) -> None:
    index = _build_index(
        data_dir,
        [
            ("Alpha expired", "alpha alpha alpha alpha alpha"),
            ("Alpha active", "alpha beta"),
        ],
    )
    expired_slug = str(
        index.connection.execute(
            "SELECT slug FROM wiki_index WHERE title = ?", ("Alpha expired",)
        ).fetchone()["slug"]
    )
    index.connection.execute(
        "UPDATE wiki_index SET expires_at = ? WHERE slug = ?",
        ("2000-01-01T00:00:00Z", expired_slug),
    )
    index.connection.commit()
    retriever = WeightedLexicalRetriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha", top_k=1)

    assert [hit.title for hit in result.hits] == ["Alpha active"]
    retriever.close()
    index.close()
