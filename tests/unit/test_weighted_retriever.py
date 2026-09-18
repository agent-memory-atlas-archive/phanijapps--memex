from pathlib import Path

import pytest

from eval.weighted_retriever import SemanticAndFallbackFts5Retriever, WeightedLexicalRetriever
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


def test_semantic_fallback_fts5_retains_duplicate_title_multi_relevance(
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
    retriever = SemanticAndFallbackFts5Retriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha beta", top_k=3)

    assert result.search_engine == "semantic-and-fallback-fts5"
    assert [hit.title for hit in result.hits] == [
        "Alpha repeated",
        "Alpha repeated",
        "Alpha repeated",
    ]
    assert [hit.rank for hit in result.hits] == [1, 2, 3]
    retriever.close()
    index.close()


def test_semantic_fallback_fts5_removes_scaffolding_and_dedupes_tokens(
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
    retriever = SemanticAndFallbackFts5Retriever(data_dir / "mem.db")
    matches: list[str] = []
    retriever._conn.set_trace_callback(matches.append)

    retriever.retrieve(
        "How does query-engine handle rate limiting instead of polling, "
        "why is chart showing switch from REST? How many nodes nodes!",
        top_k=3,
    )

    assert any(
        "'query AND engine AND rate AND limiting AND polling AND chart AND rest AND nodes'" in match
        for match in matches
    )
    retriever.close()
    index.close()


def test_semantic_fallback_fts5_keeps_content_word_showing_searchable(
    data_dir: Path,
) -> None:
    index = _index_nodes(data_dir, [_node("Showing example", "showing details")])
    retriever = SemanticAndFallbackFts5Retriever(data_dir / "mem.db")

    result = retriever.retrieve("showing", top_k=3)

    assert [hit.title for hit in result.hits] == ["Showing example"]
    retriever.close()
    index.close()


def test_semantic_fallback_fts5_falls_back_to_raw_tokens_when_filters_empty(
    data_dir: Path,
) -> None:
    index = _index_nodes(data_dir, [_node("Scaffold only", "how does handle")])
    retriever = SemanticAndFallbackFts5Retriever(data_dir / "mem.db")
    matches: list[str] = []
    retriever._conn.set_trace_callback(matches.append)

    result = retriever.retrieve("how does handle", top_k=3)

    assert [hit.title for hit in result.hits] == ["Scaffold only"]
    assert any("'how AND does AND handle'" in match for match in matches)
    retriever.close()
    index.close()


def test_semantic_fallback_fts5_metadata_reports_strategy_and_weights(data_dir: Path) -> None:
    index = _index_nodes(data_dir, [_node("Alpha", "alpha beta", slug="alpha")])
    retriever = SemanticAndFallbackFts5Retriever(data_dir / "mem.db")

    metadata = retriever.metadata()

    assert metadata["name"] == "semantic-and-fallback-fts5"
    assert metadata["query_strategy"] == "strict-and-weighted-fts5"
    assert metadata["zero_hit_fallback"] == "broad-or-weighted-fts5"
    assert metadata["column_weights"] == {
        "slug": 1.0,
        "title": 1.0,
        "body": 2.0,
        "tags": 1.0,
    }
    assert metadata["snippet_tokens"] == 12
    retriever.close()
    index.close()


def test_semantic_fallback_fts5_uses_strict_and_before_or_fallback(data_dir: Path) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node("Exact", "alpha beta", slug="exact"),
            _node("Alpha only", "alpha", slug="alpha-only"),
            _node("Beta only", "beta", slug="beta-only"),
        ],
    )
    retriever = SemanticAndFallbackFts5Retriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha beta", top_k=10)

    assert [hit.slug for hit in result.hits] == ["exact"]
    retriever.close()
    index.close()


def test_semantic_fallback_fts5_runs_or_only_after_zero_strict_hits(data_dir: Path) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node("Alpha only", "alpha", slug="alpha-only"),
            _node("Beta only", "beta", slug="beta-only"),
        ],
    )
    retriever = SemanticAndFallbackFts5Retriever(data_dir / "mem.db")
    matches: list[str] = []
    retriever._conn.set_trace_callback(matches.append)

    result = retriever.retrieve("alpha beta", top_k=10)

    assert [hit.slug for hit in result.hits] == ["alpha-only", "beta-only"]
    assert any("'alpha AND beta'" in match for match in matches)
    assert any("'alpha OR beta'" in match for match in matches)
    retriever.close()
    index.close()


def test_semantic_fallback_fts5_uses_one_fts_statement_when_strict_hits_exist(
    data_dir: Path,
) -> None:
    index = _index_nodes(data_dir, [_node("Exact", "alpha beta", slug="exact")])
    retriever = SemanticAndFallbackFts5Retriever(data_dir / "mem.db")
    matches: list[str] = []
    retriever._conn.set_trace_callback(matches.append)

    result = retriever.retrieve("alpha beta", top_k=10)

    assert [hit.slug for hit in result.hits] == ["exact"]
    assert sum("wiki_fts MATCH" in match for match in matches) == 1
    retriever.close()
    index.close()


def test_semantic_fallback_fts5_applies_filters_before_limit(data_dir: Path) -> None:
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
    retriever = SemanticAndFallbackFts5Retriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha", top_k=1)

    assert [hit.title for hit in result.hits] == ["Alpha active"]
    retriever.close()
    index.close()


def test_semantic_fallback_fts5_stabilizes_ties_ranks_and_access(data_dir: Path) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node("Beta", "alpha", slug="beta"),
            _node("Alpha", "alpha", slug="alpha"),
            _node("Gamma", "alpha", slug="gamma"),
        ],
    )
    retriever = SemanticAndFallbackFts5Retriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha", top_k=3)

    counts = {
        str(row["slug"]): int(row["access_count"])
        for row in index.connection.execute(
            "SELECT slug, access_count FROM wiki_index ORDER BY slug"
        ).fetchall()
    }
    assert [hit.slug for hit in result.hits] == ["alpha", "beta", "gamma"]
    assert [hit.rank for hit in result.hits] == [1, 2, 3]
    assert counts == {"alpha": 1, "beta": 1, "gamma": 1}
    retriever.close()
    index.close()


def test_weighted_candidate_uses_pure_rrf_tie_break_and_records_access_once(
    data_dir: Path,
) -> None:
    index = _index_nodes(
        data_dir,
        [
            _node("Alpha repeated", "alpha beta details", slug="aaa-repeated"),
            _node("Alpha repeated", "alpha beta details", slug="aab-repeated"),
            _node("Alpha repeated", "alpha beta details", slug="aac-repeated"),
            _node("Alpha second", "alpha beta details", slug="zzz-second"),
            _node("Alpha third", "alpha beta details", slug="zzz-third"),
        ],
    )
    retriever = WeightedLexicalRetriever(data_dir / "mem.db")

    result = retriever.retrieve("alpha beta", top_k=3)
    metadata = retriever.metadata()

    assert [hit.slug for hit in result.hits] == [
        "aaa-repeated",
        "aab-repeated",
        "aac-repeated",
    ]
    assert [hit.title for hit in result.hits] == [
        "Alpha repeated",
        "Alpha repeated",
        "Alpha repeated",
    ]
    assert [hit.rank for hit in result.hits] == [1, 2, 3]
    assert metadata["final_tie_break"] == "descending-rrf-score-then-ascending-slug"
    counts = {
        str(row["slug"]): int(row["access_count"])
        for row in index.connection.execute(
            "SELECT slug, access_count FROM wiki_index ORDER BY slug"
        ).fetchall()
    }
    assert sum(counts.values()) == 3
    assert {slug: counts[slug] for slug in [hit.slug for hit in result.hits]} == {
        "aaa-repeated": 1,
        "aab-repeated": 1,
        "aac-repeated": 1,
    }
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
