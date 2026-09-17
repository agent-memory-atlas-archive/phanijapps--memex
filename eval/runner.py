"""Retrieval quality evaluation against a synthetic corpus."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from eval.corpus import CorpusResult
from memex.application.memory import Memex


@dataclass(slots=True)
class HitResult:
    query: str
    difficulty: str
    expected_slugs: list[str]
    actual_slugs: list[str]
    found_rank: int | None  # 1-based rank of first expected hit found
    latency_ms: float


@dataclass(slots=True)
class EvalReport:
    corpus_size: int
    total_queries: int
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    mrr: float  # mean reciprocal rank
    precision_at_5: float
    distractor_discrimination: float  # recall on discriminator queries
    avg_latency_ms: float
    p99_latency_ms: float
    by_difficulty: dict[str, dict[str, float]] = field(default_factory=dict)
    misses: list[HitResult] = field(default_factory=list)


def run_retrieval_eval(
    memex: Memex,
    corpus: CorpusResult,
    *,
    top_k: int = 10,
) -> EvalReport:
    """Run all ground-truth queries and compute metrics."""
    results: list[HitResult] = []
    for q in corpus.queries:
        started = time.perf_counter()
        try:
            recall_result = memex.recall(q.query, top_k=top_k)
            actual = [hit.slug for hit in recall_result.hits]
        except Exception:
            actual = []
        elapsed = (time.perf_counter() - started) * 1000

        found_rank = None
        for i, slug in enumerate(actual, start=1):
            if slug in q.expected_slugs:
                found_rank = i
                break
        results.append(
            HitResult(
                query=q.query,
                difficulty=q.difficulty,
                expected_slugs=q.expected_slugs,
                actual_slugs=actual,
                found_rank=found_rank,
                latency_ms=round(elapsed, 2),
            )
        )

    return _compute_metrics(results, corpus.memories_written)


def _compute_metrics(results: list[HitResult], corpus_size: int) -> EvalReport:
    n = len(results)
    if n == 0:
        return EvalReport(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    def _recall(k: int) -> float:
        return sum(1 for r in results if r.found_rank is not None and r.found_rank <= k) / n

    def _precision_at_5() -> float:
        """Fraction of top-5 results that are in the expected set."""
        scores = []
        for r in results[:100]:  # sample to keep it fast
            top5 = r.actual_slugs[:5]
            relevant = sum(1 for s in top5 if s in r.expected_slugs)
            scores.append(relevant / 5 if top5 else 0.0)
        return sum(scores) / len(scores) if scores else 0.0

    mrr = sum(1.0 / r.found_rank for r in results if r.found_rank is not None) / n
    latencies = sorted(r.latency_ms for r in results)
    p99_idx = min(int(len(latencies) * 0.99), len(latencies) - 1)

    # By-difficulty breakdown
    by_difficulty: dict[str, dict[str, float]] = {}
    for diff in ("easy", "medium", "hard", "discriminator"):
        subset = [r for r in results if r.difficulty == diff]
        if not subset:
            continue
        sub_n = len(subset)
        by_difficulty[diff] = {
            "count": sub_n,
            "recall_at_5": sum(1 for r in subset if r.found_rank is not None and r.found_rank <= 5)
            / sub_n,
            "recall_at_10": sum(
                1 for r in subset if r.found_rank is not None and r.found_rank <= 10
            )
            / sub_n,
            "mrr": sum(1.0 / r.found_rank for r in subset if r.found_rank is not None) / sub_n,
        }

    distractors = [r for r in results if r.difficulty == "discriminator"]
    disc_score = (
        sum(1 for r in distractors if r.found_rank is not None) / len(distractors)
        if distractors
        else 0.0
    )

    misses = [r for r in results if r.found_rank is None][:20]  # top 20 for review

    return EvalReport(
        corpus_size=corpus_size,
        total_queries=n,
        recall_at_1=_recall(1),
        recall_at_5=_recall(5),
        recall_at_10=_recall(10),
        mrr=mrr,
        precision_at_5=_precision_at_5(),
        distractor_discrimination=disc_score,
        avg_latency_ms=sum(latencies) / len(latencies),
        p99_latency_ms=latencies[p99_idx],
        by_difficulty=by_difficulty,
        misses=misses,
    )


def format_report(report: EvalReport) -> str:
    """Human-readable evaluation report."""
    lines = [
        "=" * 60,
        "MEMORY LAYER RETRIEVAL EVALUATION",
        "=" * 60,
        f"Corpus size:   {report.corpus_size} memories",
        f"Queries:       {report.total_queries}",
        "",
        "--- Core Metrics ---",
        f"Recall@1:      {report.recall_at_1:.1%}",
        f"Recall@5:      {report.recall_at_5:.1%}",
        f"Recall@10:     {report.recall_at_10:.1%}",
        f"MRR:           {report.mrr:.3f}",
        f"Precision@5:   {report.precision_at_5:.1%}",
        f"Discriminator: {report.distractor_discrimination:.1%}",
        "",
        "--- Latency ---",
        f"Average:       {report.avg_latency_ms:.1f}ms",
        f"P99:           {report.p99_latency_ms:.1f}ms",
        "",
        "--- By Difficulty ---",
    ]
    for diff, metrics in report.by_difficulty.items():
        lines.append(
            f"  {diff:14s} n={metrics['count']:4d}  R@5={metrics['recall_at_5']:.1%}  "
            f"R@10={metrics['recall_at_10']:.1%}  MRR={metrics['mrr']:.3f}"
        )
    if report.misses:
        lines.append("")
        lines.append(f"--- Top Misses ({len(report.misses)} shown) ---")
        for m in report.misses:
            lines.append(f"  [{m.difficulty}] '{m.query}' → expected {m.expected_slugs[:2]}")
    lines.append("=" * 60)
    return "\n".join(lines)
