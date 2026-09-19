"""Deterministic lexical candidate ranking for retrieval evaluation."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from eval.runner import HitResult

RRF_RANK_CONSTANT = 60
MAX_RANK_SPACE_BOOST = (1.0 / (RRF_RANK_CONSTANT + 1)) - (1.0 / (RRF_RANK_CONSTANT + 2))


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    slug: str
    rank: int
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class CandidateSource:
    name: str
    candidates: Sequence[RankedCandidate]
    weight: float = 1.0


class CurrentFtsSearcher(Protocol):
    def search_fts(self, query: str, top_k: int) -> Sequence[tuple[str, float]]: ...


@dataclass(frozen=True, slots=True)
class LexicalCandidateRecipe:
    name: str
    title_weight: float
    body_weight: float
    tag_weight: float
    min_strict_candidates: int
    max_boost: float = MAX_RANK_SPACE_BOOST

    def metadata(self) -> dict[str, float | int | str]:
        return {
            "name": self.name,
            "title_weight": self.title_weight,
            "body_weight": self.body_weight,
            "tag_weight": self.tag_weight,
            "min_strict_candidates": self.min_strict_candidates,
            "max_boost": self.max_boost,
            "rank_constant": RRF_RANK_CONSTANT,
        }


DEFAULT_LEXICAL_RECIPE = LexicalCandidateRecipe(
    name="weighted-lexical-rrf",
    title_weight=3.0,
    body_weight=1.0,
    tag_weight=2.0,
    min_strict_candidates=10,
)
DECLARED_LEXICAL_RECIPES = (DEFAULT_LEXICAL_RECIPE,)


@dataclass(frozen=True, slots=True)
class CandidateRequest:
    query: str
    top_k: int
    source_queries: Mapping[str, str]
    backoff_query: str | None = None
    boosts: Mapping[str, float] | None = None


@dataclass(frozen=True, slots=True)
class CandidateRanking:
    recipe: LexicalCandidateRecipe
    request: CandidateRequest
    ranked: Sequence[RankedCandidate]
    complete: bool = True

    @property
    def actual_slugs(self) -> list[str]:
        return [candidate.slug for candidate in self.ranked]

    def ranker_metadata(self) -> dict[str, object]:
        return {
            **self.recipe.metadata(),
            "source_queries": dict(self.request.source_queries),
            "backoff_query": self.request.backoff_query,
            "complete": self.complete,
        }


@dataclass(frozen=True, slots=True)
class CandidateQueryOutcome:
    ranking: CandidateRanking
    hit_result: HitResult


def reciprocal_rank_fusion(
    sources: Sequence[Sequence[RankedCandidate]],
    *,
    top_k: int | None = None,
) -> list[RankedCandidate]:
    weighted_sources = [
        CandidateSource(name=f"source_{index}", candidates=candidates)
        for index, candidates in enumerate(sources)
    ]
    return fuse_candidate_sources(weighted_sources, top_k=top_k)


def rank_current_fts_candidate(
    searcher: CurrentFtsSearcher,
    request: CandidateRequest,
    recipe: LexicalCandidateRecipe = DEFAULT_LEXICAL_RECIPE,
) -> CandidateRanking:
    if request.top_k < 1:
        raise ValueError("top_k must be positive")
    sources = [
        _search_source(searcher, name, query, request.top_k, recipe)
        for name, query in request.source_queries.items()
    ]
    backoff_sources: list[CandidateSource] = []
    if request.backoff_query is not None:
        backoff_sources.append(
            CandidateSource(
                "backoff",
                _ranked_from_fts_rows(searcher.search_fts(request.backoff_query, request.top_k)),
            )
        )
    ranked = rank_with_query_backoff(
        strict_sources=sources,
        backoff_sources=backoff_sources,
        min_strict_candidates=recipe.min_strict_candidates,
        top_k=request.top_k,
        boosts=request.boosts,
    )
    return CandidateRanking(recipe=recipe, request=request, ranked=ranked)


def rank_declared_lexical_candidates(
    searcher: CurrentFtsSearcher,
    request: CandidateRequest,
    recipes: Sequence[LexicalCandidateRecipe] = DECLARED_LEXICAL_RECIPES,
) -> list[CandidateRanking]:
    return [rank_current_fts_candidate(searcher, request, recipe) for recipe in recipes]


def run_declared_candidate_query(
    searcher: CurrentFtsSearcher,
    request: CandidateRequest,
    *,
    difficulty: str,
    expected_slugs: Sequence[str],
    recipes: Sequence[LexicalCandidateRecipe] = DECLARED_LEXICAL_RECIPES,
) -> list[CandidateQueryOutcome]:
    started = time.perf_counter()
    rankings = rank_declared_lexical_candidates(searcher, request, recipes)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return [
        CandidateQueryOutcome(
            ranking=ranking,
            hit_result=_hit_result_from_ranking(
                ranking=ranking,
                difficulty=difficulty,
                expected_slugs=expected_slugs,
                latency_ms=elapsed_ms,
            ),
        )
        for ranking in rankings
    ]


def fuse_candidate_sources(
    sources: Sequence[CandidateSource],
    *,
    top_k: int | None = None,
    boosts: Mapping[str, float] | None = None,
    max_boost: float = MAX_RANK_SPACE_BOOST,
) -> list[RankedCandidate]:
    if top_k is not None and top_k < 1:
        raise ValueError("top_k must be positive")
    scores: dict[str, float] = {}
    for source in sources:
        for candidate in source.candidates:
            _validate_rank(candidate.rank)
            scores[candidate.slug] = scores.get(candidate.slug, 0.0) + (
                source.weight / (RRF_RANK_CONSTANT + candidate.rank)
            )
    for slug, boost in (boosts or {}).items():
        if slug not in scores:
            continue
        scores[slug] += min(max(boost, 0.0), max_boost)

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    if top_k is not None:
        ordered = ordered[:top_k]
    return [
        RankedCandidate(slug=slug, rank=rank, score=score)
        for rank, (slug, score) in enumerate(ordered, start=1)
    ]


def rank_with_query_backoff(
    *,
    strict_sources: Sequence[CandidateSource],
    backoff_sources: Sequence[CandidateSource],
    min_strict_candidates: int,
    top_k: int,
    boosts: Mapping[str, float] | None = None,
) -> list[RankedCandidate]:
    if min_strict_candidates < 1:
        raise ValueError("min_strict_candidates must be positive")
    strict_ranked = fuse_candidate_sources(strict_sources, top_k=top_k, boosts=boosts)
    if len(strict_ranked) >= min_strict_candidates:
        return strict_ranked
    return fuse_candidate_sources(
        [*strict_sources, *backoff_sources],
        top_k=top_k,
        boosts=boosts,
    )


def title_body_tag_sources(
    *,
    title: Sequence[RankedCandidate],
    body: Sequence[RankedCandidate],
    tags: Sequence[RankedCandidate],
    recipe: LexicalCandidateRecipe = DEFAULT_LEXICAL_RECIPE,
) -> list[CandidateSource]:
    return [
        CandidateSource("title", title, recipe.title_weight),
        CandidateSource("body", body, recipe.body_weight),
        CandidateSource("tags", tags, recipe.tag_weight),
    ]


def _search_source(
    searcher: CurrentFtsSearcher,
    name: str,
    query: str,
    top_k: int,
    recipe: LexicalCandidateRecipe,
) -> CandidateSource:
    return CandidateSource(
        name,
        _ranked_from_fts_rows(searcher.search_fts(query, top_k)),
        _source_weight(name, recipe),
    )


def _ranked_from_fts_rows(rows: Sequence[tuple[str, float]]) -> list[RankedCandidate]:
    return [
        RankedCandidate(slug=slug, rank=rank, score=score)
        for rank, (slug, score) in enumerate(rows, start=1)
    ]


def _source_weight(name: str, recipe: LexicalCandidateRecipe) -> float:
    if name == "title":
        return recipe.title_weight
    if name == "tags":
        return recipe.tag_weight
    return recipe.body_weight


def _hit_result_from_ranking(
    *,
    ranking: CandidateRanking,
    difficulty: str,
    expected_slugs: Sequence[str],
    latency_ms: float,
) -> HitResult:
    found_rank = None
    for rank, slug in enumerate(ranking.actual_slugs, start=1):
        if slug in expected_slugs:
            found_rank = rank
            break
    return HitResult(
        query=ranking.request.query,
        difficulty=difficulty,
        expected_slugs=list(expected_slugs),
        actual_slugs=ranking.actual_slugs,
        found_rank=found_rank,
        latency_ms=latency_ms,
    )


def _validate_rank(rank: int) -> None:
    if rank < 1:
        raise ValueError("candidate ranks must be one-based")
