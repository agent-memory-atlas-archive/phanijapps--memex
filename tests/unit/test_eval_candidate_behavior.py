import pytest

from eval.candidates import (
    MAX_RANK_SPACE_BOOST,
    RRF_RANK_CONSTANT,
    CandidateRequest,
    CandidateSource,
    RankedCandidate,
    fuse_candidate_sources,
    rank_current_fts_candidate,
    rank_with_query_backoff,
    reciprocal_rank_fusion,
    run_declared_candidate_query,
    title_body_tag_sources,
)
from eval.comparison import p99_latency_from_hits


class FakeFtsSearcher:
    def __init__(self, results_by_query: dict[str, list[tuple[str, float]]]) -> None:
        self._results_by_query = results_by_query
        self.calls: list[tuple[str, int]] = []

    def search_fts(self, query: str, top_k: int) -> list[tuple[str, float]]:
        self.calls.append((query, top_k))
        return self._results_by_query[query][:top_k]


def test_fusion_assigns_consecutive_one_based_ranks() -> None:
    sources = [
        [RankedCandidate("charlie", 1), RankedCandidate("bravo", 2)],
        [RankedCandidate("alpha", 1), RankedCandidate("bravo", 2)],
    ]

    ranked = reciprocal_rank_fusion(sources, top_k=3)

    assert [candidate.rank for candidate in ranked] == [1, 2, 3]


def test_reciprocal_rank_fusion_uses_k60_formula() -> None:
    sources = [
        [RankedCandidate("beta", 1), RankedCandidate("alpha", 2)],
        [RankedCandidate("alpha", 1), RankedCandidate("beta", 2)],
    ]

    ranked = reciprocal_rank_fusion(sources)

    assert [(candidate.slug, candidate.score) for candidate in ranked] == [
        ("alpha", (1 / (RRF_RANK_CONSTANT + 2)) + (1 / (RRF_RANK_CONSTANT + 1))),
        ("beta", (1 / (RRF_RANK_CONSTANT + 1)) + (1 / (RRF_RANK_CONSTANT + 2))),
    ]


def test_title_body_tag_weights_feed_reciprocal_rank_fusion() -> None:
    sources = title_body_tag_sources(
        title=[RankedCandidate("title-hit", 1)],
        body=[RankedCandidate("body-hit", 1)],
        tags=[],
    )

    ranked = fuse_candidate_sources(sources)

    assert [candidate.slug for candidate in ranked] == ["title-hit", "body-hit"]


def test_query_backoff_keeps_strict_sources_when_enough_candidates() -> None:
    strict_sources = [
        CandidateSource(
            "strict",
            [RankedCandidate("alpha", 1), RankedCandidate("beta", 2)],
        )
    ]
    backoff_sources = [CandidateSource("backoff", [RankedCandidate("gamma", 1)])]

    ranked = rank_with_query_backoff(
        strict_sources=strict_sources,
        backoff_sources=backoff_sources,
        min_strict_candidates=2,
        top_k=3,
    )

    assert [candidate.slug for candidate in ranked] == ["alpha", "beta"]


def test_query_backoff_broadens_when_strict_sources_are_sparse() -> None:
    strict_sources = [CandidateSource("strict", [RankedCandidate("alpha", 1)])]
    backoff_sources = [CandidateSource("backoff", [RankedCandidate("beta", 1)])]

    ranked = rank_with_query_backoff(
        strict_sources=strict_sources,
        backoff_sources=backoff_sources,
        min_strict_candidates=2,
        top_k=3,
    )

    assert [candidate.slug for candidate in ranked] == ["alpha", "beta"]


def test_bounded_boost_cannot_exceed_one_rank_space_step() -> None:
    sources = [
        CandidateSource(
            "body",
            [
                RankedCandidate("alpha", 1),
                RankedCandidate("beta", 3),
            ],
        )
    ]

    ranked = fuse_candidate_sources(
        sources,
        boosts={"beta": MAX_RANK_SPACE_BOOST * 100, "missing": MAX_RANK_SPACE_BOOST * 100},
    )

    assert [candidate.slug for candidate in ranked] == ["alpha", "beta"]


def test_candidate_ranks_must_be_one_based() -> None:
    sources = [[RankedCandidate("alpha", 0)]]

    with pytest.raises(ValueError, match="one-based"):
        reciprocal_rank_fusion(sources)


def test_current_fts_rows_are_converted_to_declared_recipe_sources() -> None:
    searcher = FakeFtsSearcher(
        {
            "deploy title": [("title-hit", -3.0), ("shared", -2.0)],
            "deploy body": [("body-hit", -4.0), ("shared", -3.0)],
            "deploy tags": [("tag-hit", -5.0)],
        }
    )
    request = CandidateRequest(
        query="deploy",
        top_k=3,
        source_queries={
            "title": "deploy title",
            "body": "deploy body",
            "tags": "deploy tags",
        },
    )

    ranking = rank_current_fts_candidate(searcher, request)

    assert ranking.actual_slugs == ["shared", "title-hit", "tag-hit"]
    assert searcher.calls == [("deploy title", 3), ("deploy body", 3), ("deploy tags", 3)]
    assert ranking.ranker_metadata()["source_queries"] == dict(request.source_queries)


def test_declared_candidate_query_returns_hit_results_for_comparison() -> None:
    searcher = FakeFtsSearcher(
        {
            "deploy strict": [("alpha", -3.0)],
            "deploy broad": [("beta", -2.0), ("gamma", -1.0)],
        }
    )
    request = CandidateRequest(
        query="deploy",
        top_k=3,
        source_queries={"body": "deploy strict"},
        backoff_query="deploy broad",
    )

    outcomes = run_declared_candidate_query(
        searcher,
        request,
        difficulty="hard",
        expected_slugs=["gamma"],
    )

    assert [outcome.ranking.recipe.name for outcome in outcomes] == ["weighted-lexical-rrf"]
    assert outcomes[0].hit_result.actual_slugs == ["alpha", "beta", "gamma"]
    assert outcomes[0].hit_result.found_rank == 3
    assert p99_latency_from_hits([outcomes[0].hit_result]) >= 0.0
