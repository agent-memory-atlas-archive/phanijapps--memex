"""Paired baseline-versus-candidate retrieval selection for PR evidence."""

from __future__ import annotations

import json
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from eval.comparison import (
    ABSOLUTE_P99_LIMITS_MS,
    COMPARISON_SCHEMA_VERSION,
    FLOAT_TOLERANCE,
    HARD_QUERY_MIN_IMPROVEMENT,
    MAX_RECALL_REGRESSION,
    PAIRED_P99_RATIO,
    TOKEN_COST_RATIO,
    CandidateMetrics,
    ComparisonMetadata,
    QueryContextObservation,
    VolatileRunMetadata,
    build_comparison_report,
    nearest_rank_p99_ms,
    p99_latency_from_hits,
    tokens_per_correct_hard_query,
)
from eval.corpus import CorpusResult, QuerySpec
from eval.realistic import RealisticCorpusGenerator
from eval.rgapi_candidate import rank_rgapi_candidate
from eval.runner import HitResult
from eval.weighted_retriever import WeightedLexicalRetriever
from memex import __version__ as MEMEX_VERSION
from memex.application import context_injection
from memex.application.memory import Memex
from memex.domain.models import RecallHit, utc_now_iso
from memex.infrastructure.config import MemexConfig

type CandidateName = Literal["weighted-lexical-rrf", "rgapi-0.1.22"]
type FailureCategory = Literal[
    "dependency_unavailable",
    "invalid_query",
    "path_rejected",
    "incomplete_search",
    "measurement_failed",
    "report_invalid",
    "source_unreproducible",
]
type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None

CANDIDATE_NAMES: tuple[CandidateName, ...] = ("weighted-lexical-rrf", "rgapi-0.1.22")
CLOSED_FAILURE_CATEGORIES: set[FailureCategory] = {
    "dependency_unavailable",
    "invalid_query",
    "path_rejected",
    "incomplete_search",
    "measurement_failed",
    "report_invalid",
    "source_unreproducible",
}
PROMOTION_SIZES = (10_000, 100_000)
PROMOTION_SEED = 42
PROMOTION_TOP_K = 10
SELECTION_SCHEMA_VERSION = 1
TOKEN_BUDGET = context_injection.DEFAULT_MAX_TOKENS
_MAX_FAILURE_REASON = 120
_QUERY_TOKENS = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class GitState:
    source_revision: str
    git_dirty: bool | None

    @property
    def promotion_eligible(self) -> bool:
        return self.source_revision != "unknown" and self.git_dirty is False


@dataclass(frozen=True, slots=True)
class EvaluationConfig:
    size: int = 100
    seed: int = PROMOTION_SEED
    top_k: int = PROMOTION_TOP_K
    candidates: Sequence[CandidateName] = CANDIDATE_NAMES
    evidence_dir: Path | None = None
    data_root: Path | None = None
    promotion_mode: bool = False
    git_state: GitState | None = None


@dataclass(frozen=True, slots=True)
class SelectionFailure:
    category: FailureCategory
    reason: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {"category": self.category, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class RunSummary:
    query_count: int
    ordered_query_ids: tuple[int, ...]
    ordered_slugs: tuple[tuple[str, ...], ...]
    p99_ms: float
    access_mutations: int
    pre_run_access_count: int
    complete: bool
    stop_reason: FailureCategory | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "query_count": self.query_count,
            "ordered_query_ids": list(self.ordered_query_ids),
            "ordered_slugs": [list(slugs) for slugs in self.ordered_slugs],
            "p99_ms": self.p99_ms,
            "access_mutations": self.access_mutations,
            "pre_run_access_count": self.pre_run_access_count,
            "complete": self.complete,
            "stop_reason": self.stop_reason,
        }


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    name: CandidateName
    baseline: RunSummary
    candidate: RunSummary
    comparison: dict[str, JsonValue]
    passed: bool
    promotion_eligible: bool
    failures: tuple[SelectionFailure, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "baseline": self.baseline.to_dict(),
            "candidate": self.candidate.to_dict(),
            "comparison": self.comparison,
            "passed": self.passed,
            "promotion_eligible": self.promotion_eligible,
            "failures": [failure.to_dict() for failure in self.failures],
        }


@dataclass(frozen=True, slots=True)
class SelectionReport:
    metadata: dict[str, JsonValue]
    query_manifest: tuple[dict[str, JsonValue], ...]
    candidates: Mapping[str, CandidateSelection]
    selected_candidate: str | None
    failures: tuple[SelectionFailure, ...]
    volatile: dict[str, JsonValue] = field(default_factory=dict)
    report_path: Path | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema_version": SELECTION_SCHEMA_VERSION,
            "metadata": self.metadata,
            "query_manifest": [dict(item) for item in self.query_manifest],
            "candidates": {name: item.to_dict() for name, item in self.candidates.items()},
            "selected_candidate": self.selected_candidate,
            "failures": [failure.to_dict() for failure in self.failures],
            "volatile": dict(self.volatile),
        }


@dataclass(slots=True)
class _MeasuredRun:
    results: list[HitResult]
    observations: list[QueryContextObservation]
    summary: RunSummary
    ranker_metadata: dict[str, JsonValue]


def run_selection(config: EvaluationConfig) -> SelectionReport:
    """Run a diagnostic or the canonical two-scale promotion evaluation."""
    _validate_config(config)
    _preflight_output_dirs(config)
    started = time.perf_counter()
    git_state = config.git_state or _git_state()
    sizes = PROMOTION_SIZES if config.promotion_mode else (config.size,)
    root_context: tempfile.TemporaryDirectory[str] | nullcontext[str]
    if config.data_root is None:
        root_context = tempfile.TemporaryDirectory(prefix="memex-selection-")
    else:
        config.data_root.mkdir(parents=True, exist_ok=True)
        root_context = nullcontext(str(config.data_root))
    with root_context as root:
        report = _run_in_root(config, Path(root), sizes, git_state, started)
    return _write_report(report, config.evidence_dir)


def _run_in_root(
    config: EvaluationConfig,
    root: Path,
    sizes: Sequence[int],
    git_state: GitState,
    started: float,
) -> SelectionReport:
    quality_size = sizes[0]
    corpora: dict[int, CorpusResult] = {}
    baselines: dict[int, _MeasuredRun] = {}
    candidate_runs: dict[CandidateName, dict[int, _MeasuredRun]] = {
        name: {} for name in config.candidates
    }
    corpus, baseline = _run_scale_setup(root, quality_size, config, retain_quality=True)
    corpora[quality_size] = corpus
    baselines[quality_size] = baseline
    for name in config.candidates:
        candidate_runs[name][quality_size] = _run_candidate_pair(
            name=name,
            snapshot_dir=root / str(quality_size) / "snapshot",
            data_dir=root / str(quality_size) / f"candidate-{name}",
            corpus=corpus,
            top_k=config.top_k,
            retain_quality=True,
        )
    eligible = {
        name
        for name, runs in candidate_runs.items()
        if config.promotion_mode and _eligible_for_large_scale(baseline, runs[quality_size])
    }
    if config.promotion_mode:
        large_size = sizes[1]
        large_corpus, large_baseline = _run_scale_setup(
            root, large_size, config, retain_quality=False
        )
        corpora[large_size] = large_corpus
        baselines[large_size] = large_baseline
        for name in config.candidates:
            if name in eligible:
                candidate_runs[name][large_size] = _run_candidate_pair(
                    name=name,
                    snapshot_dir=root / str(large_size) / "snapshot",
                    data_dir=root / str(large_size) / f"candidate-{name}",
                    corpus=large_corpus,
                    top_k=config.top_k,
                    retain_quality=False,
                )
    reports: dict[str, CandidateSelection] = {
        name: _candidate_selection(
            name=name,
            baselines=baselines,
            candidates=runs,
            corpora=corpora,
            config=config,
            git_state=git_state,
        )
        for name, runs in candidate_runs.items()
    }
    failures = [failure for item in reports.values() for failure in item.failures]
    selected = _select_candidate(reports) if config.promotion_mode else None
    if not git_state.promotion_eligible:
        failures.append(_failure("source_unreproducible", "source revision is dirty or unknown"))
    return SelectionReport(
        metadata=_metadata(config, corpora, git_state, selected is not None),
        query_manifest=_query_manifest(corpora[quality_size].queries),
        candidates=reports,
        selected_candidate=selected,
        failures=tuple(_dedupe_failures(failures)),
        volatile={
            "created_at": datetime.now(UTC).isoformat(),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        },
    )


def stable_selection_payload(report: SelectionReport) -> dict[str, JsonValue]:
    payload = report.to_dict()
    payload.pop("volatile", None)
    for candidate in _candidate_payloads(payload):
        _drop_timing(candidate)
    return payload


def _validate_config(config: EvaluationConfig) -> None:
    if config.size < 1:
        raise ValueError("size must be positive")
    if config.promotion_mode and (config.seed, config.top_k) != (PROMOTION_SEED, PROMOTION_TOP_K):
        raise ValueError("promotion mode requires seed=42 and top_k=10")


def _preflight_output_dirs(config: EvaluationConfig) -> None:
    paths = [path for path in (config.evidence_dir, config.data_root) if path is not None]
    if len(paths) == 2 and paths[0].resolve() == paths[1].resolve():
        raise ValueError("evidence and paired data directories must differ")
    for path in paths:
        _assert_fresh_dir(path, "selection output directory")


def _run_scale_setup(
    root: Path,
    size: int,
    config: EvaluationConfig,
    *,
    retain_quality: bool,
) -> tuple[CorpusResult, _MeasuredRun]:
    scale_root = root / str(size)
    snapshot_dir = scale_root / "snapshot"
    corpus = _generate_snapshot(snapshot_dir, size=size, seed=config.seed)
    baseline = _run_baseline_pair(
        snapshot_dir=snapshot_dir,
        data_dir=scale_root / "baseline",
        corpus=corpus,
        top_k=config.top_k,
        retain_quality=retain_quality,
    )
    return corpus, baseline


def _generate_snapshot(snapshot_dir: Path, *, size: int, seed: int) -> CorpusResult:
    snapshot_dir.mkdir(parents=True)
    return RealisticCorpusGenerator(snapshot_dir, seed=seed).generate(size)


def _run_baseline_pair(
    *,
    snapshot_dir: Path,
    data_dir: Path,
    corpus: CorpusResult,
    top_k: int,
    retain_quality: bool = True,
) -> _MeasuredRun:
    _copy_snapshot(snapshot_dir, data_dir)
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        memex.rebuild_index(force=True)
        pre_access = _total_access_count(data_dir)
        results: list[HitResult] = []
        observations: list[QueryContextObservation] = []
        latencies: list[float] = []
        for query in corpus.queries:
            started = time.perf_counter()
            recalled = memex.recall(query.query, top_k=top_k)
            latency_ms = (time.perf_counter() - started) * 1000
            latencies.append(latency_ms)
            if retain_quality:
                results.append(_hit_result(query, [hit.slug for hit in recalled.hits], latency_ms))
                observations.append(
                    _observation(query, recalled.hits, recalled.total_indexed, "bm25", latency_ms)
                )
        access_mutations = _total_access_count(data_dir) - pre_access
    finally:
        memex.close()
    metadata: dict[str, JsonValue] = {"name": "sqlite-fts5-bm25", "query_strategy": "or"}
    if not retain_quality:
        return _latency_only_run(
            latencies, len(corpus.queries), access_mutations, pre_access, metadata
        )
    return _measured_run(results, observations, access_mutations, pre_access, metadata)


def _run_candidate_pair(
    *,
    name: CandidateName,
    snapshot_dir: Path,
    data_dir: Path,
    corpus: CorpusResult,
    top_k: int,
    retain_quality: bool = True,
) -> _MeasuredRun:
    _copy_snapshot(snapshot_dir, data_dir)
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        memex.rebuild_index(force=True)
    finally:
        memex.close()
    pre_access = _total_access_count(data_dir)
    results: list[HitResult] = []
    observations: list[QueryContextObservation] = []
    latencies: list[float] = []
    complete = True
    stop_reason: FailureCategory | None = None
    metadata: dict[str, JsonValue] = {"name": name}
    weighted = (
        WeightedLexicalRetriever(data_dir / "mem.db") if name == "weighted-lexical-rrf" else None
    )
    rgapi_conn = sqlite3.connect(data_dir / "mem.db") if name == "rgapi-0.1.22" else None
    if rgapi_conn is not None:
        rgapi_conn.row_factory = sqlite3.Row
    try:
        for query in corpus.queries:
            outcome = (
                _run_weighted_query(weighted, query, top_k)
                if weighted is not None
                else _run_rgapi_query(data_dir, rgapi_conn, query, top_k)
            )
            metadata = outcome.ranker_metadata
            latencies.append(outcome.latency_ms)
            if retain_quality:
                results.append(
                    _hit_result(query, [hit.slug for hit in outcome.hits], outcome.latency_ms)
                )
                observations.append(
                    _observation(
                        query, outcome.hits, corpus.memories_written, name, outcome.latency_ms
                    )
                )
            if not outcome.complete:
                complete = False
                stop_reason = outcome.stop_reason or "incomplete_search"
                break
    finally:
        if weighted is not None:
            weighted.close()
        if rgapi_conn is not None:
            rgapi_conn.close()
    access_mutations = _total_access_count(data_dir) - pre_access
    measured = (
        _measured_run(results, observations, access_mutations, pre_access, metadata)
        if retain_quality
        else _latency_only_run(
            latencies, len(results) or len(latencies), access_mutations, pre_access, metadata
        )
    )
    return _replace_completion(measured, complete, stop_reason)


@dataclass(frozen=True, slots=True)
class _CandidateOutcome:
    hits: list[RecallHit]
    latency_ms: float
    complete: bool
    stop_reason: FailureCategory | None
    ranker_metadata: dict[str, JsonValue]


def _run_weighted_query(
    retriever: WeightedLexicalRetriever | None, query: QuerySpec, top_k: int
) -> _CandidateOutcome:
    if retriever is None:
        raise RuntimeError("weighted retriever is unavailable")
    started = time.perf_counter()
    recalled = retriever.retrieve(query.query, top_k=top_k)
    latency_ms = (time.perf_counter() - started) * 1000
    return _CandidateOutcome(
        recalled.hits, latency_ms, True, None, _json_mapping(retriever.metadata())
    )


def _run_rgapi_query(
    data_dir: Path, conn: sqlite3.Connection | None, query: QuerySpec, top_k: int
) -> _CandidateOutcome:
    if conn is None:
        raise RuntimeError("rgapi database is unavailable")
    started = time.perf_counter()
    try:
        ranking = rank_rgapi_candidate(query.query, data_dir / "docs", top_k=top_k)
    except ValueError:
        return _CandidateOutcome(
            [],
            (time.perf_counter() - started) * 1000,
            False,
            "invalid_query",
            {"name": "rgapi-0.1.22", "complete": False},
        )
    stop_reason = _failure_category(ranking.stop_reason)
    if not ranking.complete:
        return _CandidateOutcome(
            [],
            (time.perf_counter() - started) * 1000,
            False,
            stop_reason,
            _json_mapping(ranking.ranker_metadata()),
        )
    hits = _hydrate_rgapi_hits(conn, query.query, ranking.actual_slugs)
    _record_access(conn, hits)
    return _CandidateOutcome(
        hits,
        (time.perf_counter() - started) * 1000,
        True,
        None,
        _json_mapping(ranking.ranker_metadata()),
    )


def _hydrate_rgapi_hits(
    conn: sqlite3.Connection, query: str, slugs: Sequence[str]
) -> list[RecallHit]:
    if not slugs:
        return []
    placeholders = ",".join("?" for _ in slugs)
    now = utc_now_iso()
    rows = conn.execute(
        "SELECT * FROM wiki_index WHERE slug IN (" + placeholders + ") "  # noqa: S608
        "AND (expires_at IS NULL OR expires_at >= ?) "
        "AND (valid_to IS NULL OR valid_to >= ?) "
        "AND (status IS NULL OR status = 'active')",
        (*slugs, now, now),
    ).fetchall()
    by_slug = {str(row["slug"]): row for row in rows}
    links = _links_for_slugs(conn, slugs)
    retained_slugs = [slug for slug in slugs if slug in by_slug]
    return [
        _rgapi_hit(by_slug[slug], rank, query, links.get(slug, []))
        for rank, slug in enumerate(retained_slugs, start=1)
    ]


def _links_for_slugs(conn: sqlite3.Connection, slugs: Sequence[str]) -> dict[str, list[str]]:
    placeholders = ",".join("?" for _ in slugs)
    rows = conn.execute(
        "SELECT source_slug, target_slug FROM wiki_links WHERE source_slug IN ("  # noqa: S608
        + placeholders
        + ") ORDER BY source_slug, target_slug",
        tuple(slugs),
    ).fetchall()
    links: dict[str, list[str]] = {}
    for row in rows:
        links.setdefault(str(row["source_slug"]), []).append(str(row["target_slug"]))
    return links


def _rgapi_hit(row: sqlite3.Row, rank: int, query: str, links: list[str]) -> RecallHit:
    return RecallHit(
        slug=str(row["slug"]),
        file_path=str(row["file_path"]),
        title=str(row["title"]),
        node_type=str(row["node_type"]),
        importance=float(row["importance"]),
        score=0.0,
        rank=rank,
        snippet=_snippet(str(row["body"]), query),
        snippet_source="body",
        tags=json.loads(str(row["tags"])),
        created=str(row["created"]),
        updated=str(row["updated"]),
        last_access=row["last_access"],
        transcript_ref=row["transcript_ref"],
        links=links,
        status=str(row["status"]),
    )


def _record_access(conn: sqlite3.Connection, hits: Sequence[RecallHit]) -> None:
    now = utc_now_iso()
    with conn:
        conn.executemany(
            "UPDATE wiki_index SET access_count = access_count + 1, last_access = ? WHERE slug = ?",
            [(now, hit.slug) for hit in hits],
        )


def _observation(
    query: QuerySpec,
    hits: Sequence[RecallHit],
    total_indexed: int,
    engine: str,
    latency_ms: float,
) -> QueryContextObservation:
    return QueryContextObservation(
        query=query.query,
        difficulty=query.difficulty,
        expected_slugs=query.expected_slugs,
        hits=hits,
        total_indexed=total_indexed,
        search_engine=engine,
        search_time_ms=latency_ms,
    )


def _measured_run(
    results: list[HitResult],
    observations: list[QueryContextObservation],
    access_mutations: int,
    pre_access: int,
    ranker_metadata: dict[str, JsonValue],
) -> _MeasuredRun:
    summary = RunSummary(
        query_count=len(results),
        ordered_query_ids=tuple(range(len(results))),
        ordered_slugs=tuple(tuple(result.actual_slugs) for result in results),
        p99_ms=p99_latency_from_hits(results) if results else 0.0,
        access_mutations=access_mutations,
        pre_run_access_count=pre_access,
        complete=True,
    )
    return _MeasuredRun(results, observations, summary, ranker_metadata)


def _latency_only_run(
    latencies: Sequence[float],
    query_count: int,
    access_mutations: int,
    pre_access: int,
    ranker_metadata: dict[str, JsonValue],
) -> _MeasuredRun:
    summary = RunSummary(
        query_count=query_count,
        ordered_query_ids=(),
        ordered_slugs=(),
        p99_ms=nearest_rank_p99_ms(latencies) if latencies else 0.0,
        access_mutations=access_mutations,
        pre_run_access_count=pre_access,
        complete=True,
    )
    return _MeasuredRun([], [], summary, ranker_metadata)


def _replace_completion(
    measured: _MeasuredRun, complete: bool, stop_reason: FailureCategory | None
) -> _MeasuredRun:
    old = measured.summary
    summary = RunSummary(
        old.query_count,
        old.ordered_query_ids,
        old.ordered_slugs,
        old.p99_ms,
        old.access_mutations,
        old.pre_run_access_count,
        complete,
        stop_reason,
    )
    return _MeasuredRun(measured.results, measured.observations, summary, measured.ranker_metadata)


def _eligible_for_large_scale(baseline: _MeasuredRun, candidate: _MeasuredRun) -> bool:
    if not candidate.summary.complete:
        return False
    try:
        base = _quality_metrics(baseline, {})
        cand = _quality_metrics(candidate, {})
    except ValueError:
        return False
    regressions = [
        base.recall_at_10[bucket] - cand.recall_at_10[bucket]
        for bucket in ("overall", "easy", "medium")
    ]
    return (
        cand.hard_recall_at_10 - base.hard_recall_at_10 + FLOAT_TOLERANCE
        >= HARD_QUERY_MIN_IMPROVEMENT
        and cand.hard_mrr - base.hard_mrr + FLOAT_TOLERANCE >= HARD_QUERY_MIN_IMPROVEMENT
        and all(value <= MAX_RECALL_REGRESSION + FLOAT_TOLERANCE for value in regressions)
        and cand.tokens_per_correct_hard_query
        <= base.tokens_per_correct_hard_query * TOKEN_COST_RATIO
        and candidate.summary.p99_ms < ABSOLUTE_P99_LIMITS_MS[10_000]
        and baseline.summary.p99_ms > 0
        and candidate.summary.p99_ms / baseline.summary.p99_ms <= PAIRED_P99_RATIO + FLOAT_TOLERANCE
    )


def _candidate_selection(
    *,
    name: CandidateName,
    baselines: Mapping[int, _MeasuredRun],
    candidates: Mapping[int, _MeasuredRun],
    corpora: Mapping[int, CorpusResult],
    config: EvaluationConfig,
    git_state: GitState,
) -> CandidateSelection:
    quality_size = min(corpora)
    baseline = baselines[quality_size]
    candidate = candidates[quality_size]
    failures: list[SelectionFailure] = []
    if candidate.summary.stop_reason is not None:
        failures.append(
            _failure(candidate.summary.stop_reason, "candidate search did not complete")
        )
    try:
        comparison_report = build_comparison_report(
            baseline=_quality_metrics(
                baseline,
                {size: run.summary.p99_ms for size, run in baselines.items()},
                complete=all(run.summary.complete for run in baselines.values()),
            ),
            candidate=_quality_metrics(
                candidate,
                {size: run.summary.p99_ms for size, run in candidates.items()},
                complete=all(run.summary.complete for run in candidates.values()),
            ),
            metadata=_comparison_metadata(
                name,
                config,
                corpora,
                git_state,
                baseline.ranker_metadata,
                candidate.ranker_metadata,
            ),
            volatile=VolatileRunMetadata(datetime.now(UTC).isoformat(), 0.0),
        )
        comparison = comparison_report.stable_payload()
    except ValueError:
        failures.append(_failure("measurement_failed", "token metric could not be computed"))
        comparison = {"schema_version": COMPARISON_SCHEMA_VERSION, "verdict": {"passed": False}}
    verdict = comparison.get("verdict", {})
    passed = bool(isinstance(verdict, dict) and verdict.get("passed") is True)
    promotion_eligible = config.promotion_mode and passed and git_state.promotion_eligible
    if config.promotion_mode and passed and not git_state.promotion_eligible:
        failures.append(_failure("source_unreproducible", "source revision is dirty or unknown"))
    return CandidateSelection(
        name,
        baseline.summary,
        candidate.summary,
        comparison,
        passed,
        promotion_eligible,
        tuple(failures),
    )


def _quality_metrics(
    measured: _MeasuredRun,
    p99_ms: Mapping[int, float],
    *,
    complete: bool | None = None,
) -> CandidateMetrics:
    hard = [result for result in measured.results if result.difficulty == "hard"]
    if not hard:
        raise ValueError("evaluation corpus must include hard queries")
    by_difficulty = _recall_by_difficulty(measured.results)
    return CandidateMetrics(
        hard_recall_at_10=_recall_at_k(hard, 10),
        hard_mrr=_mrr(hard),
        recall_at_10={
            "overall": _recall_at_k(measured.results, 10),
            "easy": by_difficulty.get("easy", 0.0),
            "medium": by_difficulty.get("medium", 0.0),
        },
        tokens_per_correct_hard_query=tokens_per_correct_hard_query(
            measured.observations, token_budget=TOKEN_BUDGET
        ),
        p99_ms=p99_ms,
        complete=measured.summary.complete if complete is None else complete,
    )


def _recall_by_difficulty(results: Sequence[HitResult]) -> dict[str, float]:
    return {
        difficulty: _recall_at_k(
            [result for result in results if result.difficulty == difficulty], 10
        )
        for difficulty in ("easy", "medium")
    }


def _recall_at_k(results: Sequence[HitResult], k: int) -> float:
    if not results:
        return 0.0
    return sum(
        1 for result in results if result.found_rank is not None and result.found_rank <= k
    ) / len(results)


def _mrr(results: Sequence[HitResult]) -> float:
    if not results:
        return 0.0
    return sum(
        1.0 / result.found_rank for result in results if result.found_rank is not None
    ) / len(results)


def _hit_result(query: QuerySpec, actual_slugs: Sequence[str], latency_ms: float) -> HitResult:
    found_rank = next(
        (rank for rank, slug in enumerate(actual_slugs, start=1) if slug in query.expected_slugs),
        None,
    )
    return HitResult(
        query.query,
        query.difficulty,
        list(query.expected_slugs),
        list(actual_slugs),
        found_rank,
        latency_ms,
    )


def _snippet(body: str, query: str) -> str:
    tokens = _QUERY_TOKENS.findall(query.lower())
    index = body.lower().find(tokens[0]) if tokens else -1
    if index < 0:
        return body[:256]
    return body[max(index - 96, 0) : min(index + 160, len(body))]


def _copy_snapshot(snapshot_dir: Path, data_dir: Path) -> None:
    _assert_fresh_dir(data_dir, "paired data directory")
    data_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(snapshot_dir / "docs", data_dir / "docs")


def _total_access_count(data_dir: Path) -> int:
    conn = sqlite3.connect(data_dir / "mem.db")
    try:
        row = conn.execute("SELECT COALESCE(SUM(access_count), 0) FROM wiki_index").fetchone()
    finally:
        conn.close()
    return int(row[0])


def _metadata(
    config: EvaluationConfig,
    corpora: Mapping[int, CorpusResult],
    git_state: GitState,
    has_selected_candidate: bool,
) -> dict[str, JsonValue]:
    sizes = list(corpora)
    quality_size = min(sizes)
    return {
        "source_revision": git_state.source_revision,
        "git_dirty": git_state.git_dirty,
        "promotion_mode": config.promotion_mode,
        "promotion_eligible": config.promotion_mode
        and git_state.promotion_eligible
        and has_selected_candidate,
        "python_version": platform.python_version(),
        "memex_version": MEMEX_VERSION,
        "os_family": platform.system(),
        "cpu_architecture": platform.machine(),
        "corpus_generator": "realistic",
        "seed": config.seed,
        "requested_corpus_size": quality_size,
        "requested_corpus_sizes": [int(size) for size in sizes],
        "generated_corpus_size": corpora[quality_size].memories_written,
        "generated_corpus_sizes": {str(size): corpora[size].memories_written for size in sizes},
        "query_count": len(corpora[quality_size].queries),
        "top_k": config.top_k,
        "token_budget": TOKEN_BUDGET,
        "renderer_identity": "memex.application.context_injection.format_context_block",
        "token_estimator_identity": "memex.application.context_injection.estimate_tokens",
        "percentile_method": "nearest-rank",
    }


def _comparison_metadata(
    name: CandidateName,
    config: EvaluationConfig,
    corpora: Mapping[int, CorpusResult],
    git_state: GitState,
    baseline_ranker: Mapping[str, JsonValue],
    candidate_ranker: Mapping[str, JsonValue],
) -> ComparisonMetadata:
    sizes = list(corpora)
    return ComparisonMetadata(
        source_revision=git_state.source_revision,
        git_dirty=git_state.git_dirty,
        python_version=platform.python_version(),
        memex_version=MEMEX_VERSION,
        os_family=platform.system(),
        cpu_architecture=platform.machine(),
        corpus_generator="realistic",
        seed=config.seed,
        requested_corpus_sizes=sizes,
        generated_corpus_sizes={size: corpora[size].memories_written for size in sizes},
        query_count=len(corpora[min(sizes)].queries),
        top_k=config.top_k,
        token_budget=TOKEN_BUDGET,
        renderer_identity="memex.application.context_injection.format_context_block",
        token_estimator_identity="memex.application.context_injection.estimate_tokens",  # noqa: S106
        percentile_method="nearest-rank",
        baseline_ranker=baseline_ranker,
        candidate_ranker={"candidate": name, **candidate_ranker},
    )


def _query_manifest(queries: Sequence[QuerySpec]) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        {"id": index, "difficulty": query.difficulty, "expected_slugs": list(query.expected_slugs)}
        for index, query in enumerate(queries)
    )


def _select_candidate(candidates: Mapping[str, CandidateSelection]) -> str | None:
    eligible = [name for name, item in candidates.items() if item.promotion_eligible]
    return eligible[0] if len(eligible) == 1 else None


def _write_report(report: SelectionReport, evidence_dir: Path | None) -> SelectionReport:
    if evidence_dir is None:
        return report
    evidence_dir.mkdir(parents=True, exist_ok=True)
    suffix = (
        "promotion"
        if report.metadata["promotion_mode"]
        else str(report.metadata["requested_corpus_size"])
    )
    path = evidence_dir / f"selection-{suffix}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return SelectionReport(
        report.metadata,
        report.query_manifest,
        report.candidates,
        report.selected_candidate,
        report.failures,
        report.volatile,
        path,
    )


def _git_state() -> GitState:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],  # noqa: S607
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return GitState("unknown", None)
    return GitState(revision or "unknown", bool(status))


def _assert_fresh_dir(path: Path, label: str) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f"{label} must be empty")


def _failure(category: FailureCategory, reason: str) -> SelectionFailure:
    if category not in CLOSED_FAILURE_CATEGORIES:
        category = "measurement_failed"
    return SelectionFailure(
        category, " ".join(reason.split())[:_MAX_FAILURE_REASON] or "evaluation failed"
    )


def _failure_category(value: object) -> FailureCategory | None:
    if value is None:
        return None
    if isinstance(value, str) and value in CLOSED_FAILURE_CATEGORIES:
        return value
    return "incomplete_search"


def _dedupe_failures(failures: Sequence[SelectionFailure]) -> list[SelectionFailure]:
    return list(dict.fromkeys(failures))


def _candidate_payloads(payload: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, dict):
        return []
    return [candidate for candidate in candidates.values() if isinstance(candidate, dict)]


def _drop_timing(candidate: dict[str, JsonValue]) -> None:
    for side in ("baseline", "candidate"):
        summary = candidate.get(side)
        if isinstance(summary, dict):
            summary.pop("p99_ms", None)
    comparison = candidate.get("comparison")
    if not isinstance(comparison, dict):
        return
    for side in ("baseline", "candidate"):
        metrics = comparison.get(side)
        if isinstance(metrics, dict):
            metrics.pop("p99_ms", None)
    verdict = comparison.get("verdict")
    if isinstance(verdict, dict):
        gates = verdict.get("gates")
        if isinstance(gates, dict):
            gates.pop("absolute_p99", None)
            gates.pop("paired_p99", None)


def _json_mapping(values: Mapping[str, object]) -> dict[str, JsonValue]:
    return {key: _json_value(value) for key, value in values.items()}


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_json_value(item) for item in value]
    return str(value)


def main(argv: Sequence[str] | None = None) -> int:
    from eval.run import main as run_main

    return run_main(list(argv) if argv is not None else sys.argv[1:])
