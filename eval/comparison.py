"""Paired retrieval metrics and candidate promotion gates."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from eval.runner import HitResult
from memex.application import context_injection
from memex.domain.models import RecallHit, RecallResult

HARD_QUERY_MIN_IMPROVEMENT = 0.05
MAX_RECALL_REGRESSION = 0.005
TOKEN_COST_RATIO = 0.80
PAIRED_P99_RATIO = 1.10
ABSOLUTE_P99_LIMITS_MS = {10_000: 50.0, 100_000: 100.0}
REGRESSION_BUCKETS = ("overall", "easy", "medium")
PERCENTILE_METHOD = "nearest-rank"
COMPARISON_SCHEMA_VERSION = 1
FLOAT_TOLERANCE = 1e-12

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    hard_recall_at_10: float
    hard_mrr: float
    recall_at_10: Mapping[str, float]
    tokens_per_correct_hard_query: float
    p99_ms: Mapping[int, float]
    complete: bool


@dataclass(frozen=True, slots=True)
class GateVerdict:
    passed: bool
    observed: JsonValue
    threshold: JsonValue
    reason: str = ""

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "passed": self.passed,
            "observed": self.observed,
            "threshold": self.threshold,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CandidateVerdict:
    passed: bool
    gates: Mapping[str, GateVerdict]
    complete: bool

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "passed": self.passed,
            "complete": self.complete,
            "gates": {name: gate.to_dict() for name, gate in self.gates.items()},
        }


@dataclass(frozen=True, slots=True)
class QueryContextObservation:
    query: str
    difficulty: str
    expected_slugs: Sequence[str]
    hits: Sequence[RecallHit]
    total_indexed: int = 0
    search_engine: str = "eval"
    search_time_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class ComparisonMetadata:
    source_revision: str
    git_dirty: bool | None
    python_version: str
    memex_version: str
    os_family: str
    cpu_architecture: str
    corpus_generator: str
    seed: int
    requested_corpus_sizes: Sequence[int]
    generated_corpus_sizes: Mapping[int, int]
    query_count: int
    top_k: int
    token_budget: int
    renderer_identity: str
    token_estimator_identity: str
    percentile_method: str
    baseline_ranker: Mapping[str, JsonValue]
    candidate_ranker: Mapping[str, JsonValue]

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "source_revision": self.source_revision,
            "git_dirty": self.git_dirty,
            "python_version": self.python_version,
            "memex_version": self.memex_version,
            "os_family": self.os_family,
            "cpu_architecture": self.cpu_architecture,
            "corpus_generator": self.corpus_generator,
            "seed": self.seed,
            "requested_corpus_sizes": list(self.requested_corpus_sizes),
            "generated_corpus_sizes": {
                str(size): generated for size, generated in self.generated_corpus_sizes.items()
            },
            "query_count": self.query_count,
            "top_k": self.top_k,
            "token_budget": self.token_budget,
            "renderer_identity": self.renderer_identity,
            "token_estimator_identity": self.token_estimator_identity,
            "percentile_method": self.percentile_method,
            "baseline_ranker": dict(self.baseline_ranker),
            "candidate_ranker": dict(self.candidate_ranker),
        }


@dataclass(frozen=True, slots=True)
class VolatileRunMetadata:
    created_at: str
    elapsed_ms: float

    def to_dict(self) -> dict[str, JsonValue]:
        return {"created_at": self.created_at, "elapsed_ms": self.elapsed_ms}


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    metadata: ComparisonMetadata
    baseline: CandidateMetrics
    candidate: CandidateMetrics
    verdict: CandidateVerdict
    volatile: VolatileRunMetadata

    def stable_payload(self) -> dict[str, JsonValue]:
        return {
            "schema_version": COMPARISON_SCHEMA_VERSION,
            "metadata": self.metadata.to_dict(),
            "baseline": _metrics_to_dict(self.baseline),
            "candidate": _metrics_to_dict(self.candidate),
            "verdict": self.verdict.to_dict(),
        }

    def volatile_payload(self) -> dict[str, JsonValue]:
        return self.volatile.to_dict()

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "stable": self.stable_payload(),
            "volatile": self.volatile_payload(),
        }


def evaluate_candidate(
    *,
    baseline: CandidateMetrics,
    candidate: CandidateMetrics,
) -> CandidateVerdict:
    gates = {
        "hard_recall_at_10": _minimum_delta_gate(
            candidate.hard_recall_at_10,
            baseline.hard_recall_at_10,
            HARD_QUERY_MIN_IMPROVEMENT,
        ),
        "hard_mrr": _minimum_delta_gate(
            candidate.hard_mrr,
            baseline.hard_mrr,
            HARD_QUERY_MIN_IMPROVEMENT,
        ),
        "recall_regression": _recall_regression_gate(baseline, candidate),
        "tokens_per_correct_hard_query": _token_gate(baseline, candidate),
        "absolute_p99": _absolute_p99_gate(candidate),
        "paired_p99": _paired_p99_gate(baseline, candidate),
    }
    passed = candidate.complete and all(gate.passed for gate in gates.values())
    return CandidateVerdict(passed=passed, gates=gates, complete=candidate.complete)


def nearest_rank_p99_ms(latencies_ms: Sequence[float]) -> float:
    if not latencies_ms:
        raise ValueError("latencies_ms must not be empty")
    sorted_latencies = sorted(latencies_ms)
    index = math.ceil(0.99 * len(sorted_latencies)) - 1
    return sorted_latencies[index]


def p99_latency_from_hits(results: Sequence[HitResult]) -> float:
    return nearest_rank_p99_ms([result.latency_ms for result in results])


def tokens_per_correct_hard_query(
    observations: Sequence[QueryContextObservation],
    *,
    token_budget: int = context_injection.DEFAULT_MAX_TOKENS,
) -> float:
    total_tokens = 0
    correct_hard_queries = 0
    for observation in observations:
        if observation.difficulty != "hard":
            continue
        packed_hits = context_injection.pack_to_budget(
            list(observation.hits),
            max_tokens=token_budget,
        )
        rendered = context_injection.format_context_block(
            RecallResult(
                query=observation.query,
                hits=packed_hits,
                total_indexed=observation.total_indexed,
                search_engine=observation.search_engine,
                search_time_ms=observation.search_time_ms,
            )
        )
        total_tokens += context_injection.estimate_tokens(rendered)
        if _contains_expected_slug(packed_hits, observation.expected_slugs):
            correct_hard_queries += 1
    if correct_hard_queries == 0:
        raise ValueError("at least one hard query must keep an expected page in packed context")
    return total_tokens / correct_hard_queries


def build_comparison_report(
    *,
    baseline: CandidateMetrics,
    candidate: CandidateMetrics,
    metadata: ComparisonMetadata,
    volatile: VolatileRunMetadata,
) -> ComparisonReport:
    return ComparisonReport(
        metadata=metadata,
        baseline=baseline,
        candidate=candidate,
        verdict=evaluate_candidate(baseline=baseline, candidate=candidate),
        volatile=volatile,
    )


def _minimum_delta_gate(candidate_value: float, baseline_value: float, delta: float) -> GateVerdict:
    observed_delta = candidate_value - baseline_value
    passed = observed_delta + FLOAT_TOLERANCE >= delta
    return GateVerdict(
        passed=passed,
        observed=observed_delta,
        threshold=delta,
        reason="" if passed else "candidate improvement is below the threshold",
    )


def _recall_regression_gate(
    baseline: CandidateMetrics,
    candidate: CandidateMetrics,
) -> GateVerdict:
    regressions: dict[str, float] = {}
    for bucket in REGRESSION_BUCKETS:
        if bucket not in baseline.recall_at_10 or bucket not in candidate.recall_at_10:
            return GateVerdict(
                passed=False,
                observed=bucket,
                threshold=MAX_RECALL_REGRESSION,
                reason="missing recall bucket",
            )
        regressions[bucket] = baseline.recall_at_10[bucket] - candidate.recall_at_10[bucket]
    passed = all(
        regression <= MAX_RECALL_REGRESSION + FLOAT_TOLERANCE for regression in regressions.values()
    )
    observed: dict[str, JsonValue] = dict(regressions)
    return GateVerdict(
        passed=passed,
        observed=observed,
        threshold=MAX_RECALL_REGRESSION,
        reason="" if passed else "recall regression exceeds the threshold",
    )


def _token_gate(baseline: CandidateMetrics, candidate: CandidateMetrics) -> GateVerdict:
    threshold = baseline.tokens_per_correct_hard_query * TOKEN_COST_RATIO
    passed = candidate.tokens_per_correct_hard_query <= threshold
    return GateVerdict(
        passed=passed,
        observed=candidate.tokens_per_correct_hard_query,
        threshold=threshold,
        reason="" if passed else "token cost exceeds 80% of baseline",
    )


def _absolute_p99_gate(candidate: CandidateMetrics) -> GateVerdict:
    observed: dict[str, JsonValue] = {}
    for size, threshold in ABSOLUTE_P99_LIMITS_MS.items():
        if size not in candidate.p99_ms:
            return GateVerdict(
                passed=False,
                observed=str(size),
                threshold={str(k): v for k, v in ABSOLUTE_P99_LIMITS_MS.items()},
                reason="missing p99 latency size",
            )
        observed[str(size)] = candidate.p99_ms[size]
        if candidate.p99_ms[size] >= threshold:
            return GateVerdict(
                passed=False,
                observed=observed,
                threshold={str(k): v for k, v in ABSOLUTE_P99_LIMITS_MS.items()},
                reason="candidate p99 must be below the absolute threshold",
            )
    return GateVerdict(
        passed=True,
        observed=observed,
        threshold={str(k): v for k, v in ABSOLUTE_P99_LIMITS_MS.items()},
    )


def _paired_p99_gate(baseline: CandidateMetrics, candidate: CandidateMetrics) -> GateVerdict:
    ratios: dict[str, JsonValue] = {}
    for size, baseline_p99 in baseline.p99_ms.items():
        if baseline_p99 <= 0:
            return GateVerdict(
                passed=False,
                observed=baseline_p99,
                threshold=PAIRED_P99_RATIO,
                reason="baseline p99 must be positive",
            )
        if size not in candidate.p99_ms:
            return GateVerdict(
                passed=False,
                observed=str(size),
                threshold=PAIRED_P99_RATIO,
                reason="missing paired p99 latency size",
            )
        ratio = candidate.p99_ms[size] / baseline_p99
        ratios[str(size)] = ratio
        if ratio > PAIRED_P99_RATIO + FLOAT_TOLERANCE:
            return GateVerdict(
                passed=False,
                observed=ratios,
                threshold=PAIRED_P99_RATIO,
                reason="candidate p99 exceeds paired baseline allowance",
            )
    return GateVerdict(passed=True, observed=ratios, threshold=PAIRED_P99_RATIO)


def _contains_expected_slug(hits: Sequence[RecallHit], expected_slugs: Sequence[str]) -> bool:
    expected = set(expected_slugs)
    return any(hit.slug in expected for hit in hits)


def _metrics_to_dict(metrics: CandidateMetrics) -> dict[str, JsonValue]:
    return {
        "hard_recall_at_10": metrics.hard_recall_at_10,
        "hard_mrr": metrics.hard_mrr,
        "recall_at_10": dict(metrics.recall_at_10),
        "tokens_per_correct_hard_query": metrics.tokens_per_correct_hard_query,
        "p99_ms": {str(size): value for size, value in metrics.p99_ms.items()},
        "complete": metrics.complete,
    }
