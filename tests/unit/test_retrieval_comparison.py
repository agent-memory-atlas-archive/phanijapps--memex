# STUB: AC-0007
from dataclasses import replace
from typing import cast

import pytest

from eval.comparison import (
    CandidateMetrics,
    ComparisonMetadata,
    QueryContextObservation,
    VolatileRunMetadata,
    build_comparison_report,
    evaluate_candidate,
    p99_latency_from_hits,
    tokens_per_correct_hard_query,
)
from eval.runner import HitResult
from memex.application.context_injection import (
    estimate_tokens,
    format_context_block,
    pack_to_budget,
)
from memex.domain.models import RecallHit, RecallResult


def test_candidate_gate_requires_one_candidate_to_pass_every_threshold() -> None:
    baseline = CandidateMetrics(
        hard_recall_at_10=0.320,
        hard_mrr=0.400,
        recall_at_10={"overall": 0.680, "easy": 0.950, "medium": 0.750},
        tokens_per_correct_hard_query=100.0,
        p99_ms={10_000: 40.0, 100_000: 80.0},
        complete=True,
    )
    candidate = CandidateMetrics(
        hard_recall_at_10=0.370,
        hard_mrr=0.450,
        recall_at_10={"overall": 0.675, "easy": 0.945, "medium": 0.745},
        tokens_per_correct_hard_query=80.0,
        p99_ms={10_000: 44.0, 100_000: 88.0},
        complete=True,
    )

    verdict = evaluate_candidate(baseline=baseline, candidate=candidate)

    assert verdict.passed is True
    assert set(verdict.gates) == {
        "hard_recall_at_10",
        "hard_mrr",
        "recall_regression",
        "tokens_per_correct_hard_query",
        "absolute_p99",
        "paired_p99",
    }
    assert all(gate.passed for gate in verdict.gates.values())


def test_hard_quality_gates_use_absolute_floor_when_baseline_is_already_high() -> None:
    baseline = CandidateMetrics(
        hard_recall_at_10=0.920,
        hard_mrr=0.820,
        recall_at_10={"overall": 0.920, "easy": 0.950, "medium": 0.930},
        tokens_per_correct_hard_query=100.0,
        p99_ms={10_000: 40.0, 100_000: 80.0},
        complete=True,
    )
    candidate = CandidateMetrics(
        hard_recall_at_10=0.915,
        hard_mrr=0.815,
        recall_at_10={"overall": 0.915, "easy": 0.945, "medium": 0.925},
        tokens_per_correct_hard_query=80.0,
        p99_ms={10_000: 44.0, 100_000: 88.0},
        complete=True,
    )

    verdict = evaluate_candidate(baseline=baseline, candidate=candidate)

    assert verdict.gates["hard_recall_at_10"].passed is True
    assert verdict.gates["hard_mrr"].passed is True
    assert verdict.passed is True


def _passing_baseline() -> CandidateMetrics:
    return CandidateMetrics(
        hard_recall_at_10=0.320,
        hard_mrr=0.400,
        recall_at_10={"overall": 0.680, "easy": 0.950, "medium": 0.750},
        tokens_per_correct_hard_query=100.0,
        p99_ms={10_000: 40.0, 100_000: 80.0},
        complete=True,
    )


def _passing_candidate() -> CandidateMetrics:
    return CandidateMetrics(
        hard_recall_at_10=0.370,
        hard_mrr=0.450,
        recall_at_10={"overall": 0.675, "easy": 0.945, "medium": 0.745},
        tokens_per_correct_hard_query=80.0,
        p99_ms={10_000: 44.0, 100_000: 88.0},
        complete=True,
    )


def _hit_result(latency_ms: float) -> HitResult:
    return HitResult(
        query="q",
        difficulty="hard",
        expected_slugs=["target"],
        actual_slugs=["target"],
        found_rank=1,
        latency_ms=latency_ms,
    )


def _recall_hit(slug: str, *, rank: int = 1, snippet: str = "needle") -> RecallHit:
    return RecallHit(
        slug=slug,
        file_path=f"/{slug}.md",
        title=slug,
        node_type="entity",
        importance=0.5,
        score=1.0,
        rank=rank,
        snippet=snippet,
        snippet_source="body",
        tags=[],
        created="2026-01-01T00:00:00Z",
        updated="2026-01-01T00:00:00Z",
        last_access=None,
        transcript_ref=None,
        links=[],
    )


@pytest.mark.parametrize(
    ("candidate", "failed_gate"),
    [
        (
            CandidateMetrics(
                hard_recall_at_10=0.369,
                hard_mrr=0.450,
                recall_at_10={"overall": 0.675, "easy": 0.945, "medium": 0.745},
                tokens_per_correct_hard_query=80.0,
                p99_ms={10_000: 44.0, 100_000: 88.0},
                complete=True,
            ),
            "hard_recall_at_10",
        ),
        (
            CandidateMetrics(
                hard_recall_at_10=0.370,
                hard_mrr=0.449,
                recall_at_10={"overall": 0.675, "easy": 0.945, "medium": 0.745},
                tokens_per_correct_hard_query=80.0,
                p99_ms={10_000: 44.0, 100_000: 88.0},
                complete=True,
            ),
            "hard_mrr",
        ),
        (
            CandidateMetrics(
                hard_recall_at_10=0.370,
                hard_mrr=0.450,
                recall_at_10={"overall": 0.6749, "easy": 0.945, "medium": 0.745},
                tokens_per_correct_hard_query=80.0,
                p99_ms={10_000: 44.0, 100_000: 88.0},
                complete=True,
            ),
            "recall_regression",
        ),
        (
            CandidateMetrics(
                hard_recall_at_10=0.370,
                hard_mrr=0.450,
                recall_at_10={"overall": 0.675, "easy": 0.945, "medium": 0.745},
                tokens_per_correct_hard_query=80.01,
                p99_ms={10_000: 44.0, 100_000: 88.0},
                complete=True,
            ),
            "tokens_per_correct_hard_query",
        ),
        (
            CandidateMetrics(
                hard_recall_at_10=0.370,
                hard_mrr=0.450,
                recall_at_10={"overall": 0.675, "easy": 0.945, "medium": 0.745},
                tokens_per_correct_hard_query=80.0,
                p99_ms={10_000: 50.0, 100_000: 88.0},
                complete=True,
            ),
            "absolute_p99",
        ),
        (
            CandidateMetrics(
                hard_recall_at_10=0.370,
                hard_mrr=0.450,
                recall_at_10={"overall": 0.675, "easy": 0.945, "medium": 0.745},
                tokens_per_correct_hard_query=80.0,
                p99_ms={10_000: 44.01, 100_000: 88.0},
                complete=True,
            ),
            "paired_p99",
        ),
    ],
)
def test_candidate_gate_rejects_each_failing_threshold(
    candidate: CandidateMetrics,
    failed_gate: str,
) -> None:
    verdict = evaluate_candidate(baseline=_passing_baseline(), candidate=candidate)

    assert verdict.passed is False
    assert verdict.gates[failed_gate].passed is False


def test_incomplete_candidate_cannot_pass_promotion() -> None:
    candidate = CandidateMetrics(
        hard_recall_at_10=0.370,
        hard_mrr=0.450,
        recall_at_10={"overall": 0.675, "easy": 0.945, "medium": 0.745},
        tokens_per_correct_hard_query=80.0,
        p99_ms={10_000: 44.0, 100_000: 88.0},
        complete=False,
    )

    verdict = evaluate_candidate(baseline=_passing_baseline(), candidate=candidate)

    assert verdict.passed is False
    assert all(gate.passed for gate in verdict.gates.values())


def test_candidate_gate_fails_closed_for_zero_baseline_latency() -> None:
    baseline = replace(_passing_baseline(), p99_ms={10_000: 0.0, 100_000: 80.0})

    verdict = evaluate_candidate(baseline=baseline, candidate=_passing_candidate())

    assert verdict.passed is False
    assert verdict.gates["paired_p99"].reason == "baseline p99 must be positive"


def test_p99_latency_uses_nearest_rank_from_raw_hit_results() -> None:
    results = [_hit_result(float(value)) for value in range(1, 101)]

    assert p99_latency_from_hits(results) == 99.0


def test_tokens_per_correct_hard_query_uses_packed_rendered_context() -> None:
    correct = QueryContextObservation(
        query="needle",
        difficulty="hard",
        expected_slugs=["target"],
        hits=[_recall_hit("target", snippet="x" * 10)],
    )
    miss = QueryContextObservation(
        query="needle",
        difficulty="hard",
        expected_slugs=["missing"],
        hits=[_recall_hit("other", snippet="y" * 10)],
    )

    expected_tokens = 0
    for observation in (correct, miss):
        packed = pack_to_budget(list(observation.hits), max_tokens=4096)
        rendered = format_context_block(
            RecallResult(
                query=observation.query,
                hits=packed,
                total_indexed=0,
                search_engine="eval",
                search_time_ms=0.0,
            )
        )
        expected_tokens += estimate_tokens(rendered)

    assert tokens_per_correct_hard_query([correct, miss]) == float(expected_tokens)


def test_tokens_per_correct_hard_query_rejects_zero_correct_hard_queries() -> None:
    miss = QueryContextObservation(
        query="needle",
        difficulty="hard",
        expected_slugs=["missing"],
        hits=[_recall_hit("other")],
    )

    with pytest.raises(ValueError, match="at least one hard query"):
        tokens_per_correct_hard_query([miss])


def test_comparison_report_separates_stable_and_volatile_fields() -> None:
    report = build_comparison_report(
        baseline=_passing_baseline(),
        candidate=_passing_candidate(),
        metadata=ComparisonMetadata(
            source_revision="abc123",
            git_dirty=False,
            python_version="3.12.11",
            memex_version="0.2.4",
            os_family="Linux",
            cpu_architecture="x86_64",
            corpus_generator="realistic",
            seed=42,
            requested_corpus_sizes=[10_000, 100_000],
            generated_corpus_sizes={10_000: 10_000, 100_000: 100_000},
            query_count=208,
            top_k=10,
            token_budget=4096,
            renderer_identity="memex.application.context_injection.format_context_block",
            token_estimator_identity="memex.application.context_injection.estimate_tokens",  # noqa: S106
            percentile_method="nearest-rank",
            baseline_ranker={"name": "sqlite-fts5-bm25"},
            candidate_ranker={"name": "candidate"},
        ),
        volatile=VolatileRunMetadata(created_at="2026-09-18T12:00:00Z", elapsed_ms=12.3),
    )

    payload = report.to_dict()
    stable = cast(dict[str, object], payload["stable"])
    metadata = cast(dict[str, object], stable["metadata"])
    verdict = cast(dict[str, object], stable["verdict"])

    assert stable["schema_version"] == 1
    assert metadata["seed"] == 42
    assert metadata["percentile_method"] == "nearest-rank"
    assert metadata["os_family"] == "Linux"
    assert metadata["cpu_architecture"] == "x86_64"
    assert verdict["passed"] is True
    assert "created_at" not in metadata
    assert payload["volatile"] == {"created_at": "2026-09-18T12:00:00Z", "elapsed_ms": 12.3}
