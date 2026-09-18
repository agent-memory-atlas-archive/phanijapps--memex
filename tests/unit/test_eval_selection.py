from __future__ import annotations

import getpass
import json
import platform
from pathlib import Path
from typing import cast

import pytest

import eval.selection as selection
from eval.comparison import CandidateMetrics, QueryContextObservation
from eval.corpus import CorpusResult, QuerySpec
from eval.runner import HitResult
from eval.selection import (
    CLOSED_FAILURE_CATEGORIES,
    EvaluationConfig,
    GitState,
    WorkloadMetrics,
    run_selection,
    stable_selection_payload,
    validate_workload_metrics,
)
from memex.domain.models import RecallHit


def test_selection_refuses_nonempty_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "evidence"
    output_dir.mkdir()
    (output_dir / "keep.txt").write_text("leave me alone", encoding="utf-8")

    with pytest.raises(ValueError, match="must be empty"):
        run_selection(
            EvaluationConfig(
                size=12, evidence_dir=output_dir, candidates=("field-channel-rrf-k60",)
            )
        )

    assert (output_dir / "keep.txt").read_text(encoding="utf-8") == "leave me alone"


def test_selection_refuses_nonempty_paired_data_root_without_mutation(tmp_path: Path) -> None:
    data_root = tmp_path / "paired"
    data_root.mkdir()
    marker = data_root / "keep.txt"
    marker.write_text("leave me alone", encoding="utf-8")
    evidence_dir = tmp_path / "evidence"

    with pytest.raises(ValueError, match="must be empty"):
        run_selection(
            EvaluationConfig(
                size=12,
                data_root=data_root,
                evidence_dir=evidence_dir,
                candidates=("field-channel-rrf-k60",),
            )
        )

    assert marker.read_text(encoding="utf-8") == "leave me alone"
    assert not evidence_dir.exists()


def test_selection_refuses_configured_memex_store_and_descendants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_store = tmp_path / "live-memex"
    monkeypatch.setenv("MEMEX_DATA_DIR", str(live_store))

    for requested in (live_store, live_store / "evaluation"):
        with pytest.raises(ValueError, match="outside protected Memex stores"):
            run_selection(
                EvaluationConfig(
                    size=12,
                    data_root=requested,
                    candidates=("field-channel-rrf-k60",),
                )
            )
        assert not requested.exists()


def test_selection_preflight_ignores_unrelated_invalid_live_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_store = tmp_path / "live-memex"
    live_store.mkdir()
    (live_store / "memex.toml").write_text('[llm]\nprovider = "not-a-provider"\n', encoding="utf-8")
    monkeypatch.setenv("MEMEX_DATA_DIR", str(live_store))
    evaluation_root = tmp_path / "isolated-evaluation"

    report = run_selection(
        EvaluationConfig(
            size=12,
            data_root=evaluation_root,
            candidates=("field-channel-rrf-k60",),
            git_state=GitState(source_revision="abc123", git_dirty=False),
        )
    )

    assert report.metadata["requested_corpus_size"] == 12
    assert evaluation_root.exists()


def test_selection_protects_default_store_when_environment_uses_isolated_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEMEX_DATA_DIR", str(tmp_path / "isolated-live-store"))
    default_store = Path.home() / ".memex"

    for requested in (default_store, default_store / "evaluation"):
        with pytest.raises(ValueError, match="outside protected Memex stores"):
            run_selection(
                EvaluationConfig(
                    size=12,
                    data_root=requested,
                    candidates=("field-channel-rrf-k60",),
                )
            )
        assert not requested.exists()


def test_selection_writes_sanitized_schema_and_blocks_dirty_promotion(tmp_path: Path) -> None:
    output_dir = tmp_path / "evidence"

    report = run_selection(
        EvaluationConfig(
            size=12,
            evidence_dir=output_dir,
            candidates=("field-channel-rrf-k60",),
            git_state=GitState(source_revision="abc123", git_dirty=True),
        )
    )

    payload = json.loads((output_dir / "selection-12.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["metadata"]["source_revision"] == "abc123"
    assert payload["metadata"]["git_dirty"] is True
    assert payload["metadata"]["promotion_eligible"] is False
    assert payload["selected_candidate"] is None
    assert report.failures[0].category == "source_unreproducible"
    assert set(payload["failures"][0]) == {"category", "reason"}
    assert str(tmp_path) not in json.dumps(payload)


def test_selection_stable_payload_excludes_volatile_metadata(tmp_path: Path) -> None:
    config = EvaluationConfig(
        size=12,
        candidates=("field-channel-rrf-k60",),
        git_state=GitState(source_revision="abc123", git_dirty=False),
    )

    first = run_selection(config)
    second = run_selection(config)

    assert stable_selection_payload(first) == stable_selection_payload(second)


def test_selection_uses_independent_paired_stores(tmp_path: Path) -> None:
    report = run_selection(
        EvaluationConfig(
            size=12,
            candidates=("field-channel-rrf-k60",),
            git_state=GitState(source_revision="abc123", git_dirty=False),
        )
    )
    weighted = report.candidates["field-channel-rrf-k60"]

    assert weighted.baseline.access_mutations > 0
    assert weighted.candidate.pre_run_access_count == 0
    assert weighted.candidate.query_count == weighted.baseline.query_count
    assert weighted.candidate.ordered_query_ids == weighted.baseline.ordered_query_ids


def test_candidate_run_is_independent_of_baseline_access_state(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshot"
    corpus = selection._generate_snapshot(snapshot_dir, size=12, seed=42)
    baseline = selection._run_baseline_pair(
        snapshot_dir=snapshot_dir,
        data_dir=tmp_path / "baseline",
        corpus=corpus,
        top_k=10,
    )
    paired = selection._run_candidate_pair(
        name="field-channel-rrf-k60",
        snapshot_dir=snapshot_dir,
        data_dir=tmp_path / "candidate-paired",
        corpus=corpus,
        top_k=10,
    )
    clean = selection._run_candidate_pair(
        name="field-channel-rrf-k60",
        snapshot_dir=snapshot_dir,
        data_dir=tmp_path / "candidate-clean",
        corpus=corpus,
        top_k=10,
    )

    assert baseline.summary.access_mutations > 0
    assert paired.summary.pre_run_access_count == clean.summary.pre_run_access_count == 0
    assert paired.summary.ordered_slugs == clean.summary.ordered_slugs
    assert [result.found_rank for result in paired.results] == [
        result.found_rank for result in clean.results
    ]


def test_single_pass_weighted_candidate_is_selectable(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshot"
    corpus = selection._generate_snapshot(snapshot_dir, size=12, seed=42)

    candidate = selection._run_candidate_pair(
        name="single-pass-weighted-fts5",
        snapshot_dir=snapshot_dir,
        data_dir=tmp_path / "candidate-single-pass",
        corpus=corpus,
        top_k=10,
    )

    assert "single-pass-weighted-fts5" in selection.CANDIDATE_NAMES
    assert candidate.ranker_metadata["name"] == "single-pass-weighted-fts5"
    assert candidate.summary.query_count == len(corpus.queries)


def test_promotion_uses_one_baseline_per_actual_scale_and_never_duplicates_p99(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_sizes: list[int] = []
    candidate_sizes: list[int] = []

    def fake_scale_setup(
        root: Path, size: int, config: EvaluationConfig, *, retain_quality: bool
    ) -> tuple[CorpusResult, selection._MeasuredRun]:
        del root, config, retain_quality
        setup_sizes.append(size)
        return _fake_corpus(size), _fake_measured(float(size // 10_000))

    def fake_candidate_pair(
        *,
        name: selection.CandidateName,
        snapshot_dir: Path,
        data_dir: Path,
        corpus: CorpusResult,
        top_k: int,
        retain_quality: bool,
    ) -> selection._MeasuredRun:
        del name, snapshot_dir, data_dir, top_k, retain_quality
        candidate_sizes.append(corpus.memories_written)
        return _fake_measured(float(corpus.memories_written // 10_000) + 0.25)

    monkeypatch.setattr(selection, "_run_scale_setup", fake_scale_setup)
    monkeypatch.setattr(selection, "_run_candidate_pair", fake_candidate_pair)
    monkeypatch.setattr(selection, "_eligible_for_large_scale", lambda baseline, candidate: True)

    report = run_selection(
        EvaluationConfig(
            promotion_mode=True,
            candidates=("field-channel-rrf-k60",),
            git_state=GitState(source_revision="abc123", git_dirty=False),
        )
    )

    assert setup_sizes == [10_000, 100_000]
    assert candidate_sizes == [10_000, 100_000]
    comparison = report.candidates["field-channel-rrf-k60"].comparison
    baseline = cast(dict[str, selection.JsonValue], comparison["baseline"])
    candidate = cast(dict[str, selection.JsonValue], comparison["candidate"])
    assert baseline["p99_ms"] == {"10000": 1.0, "100000": 10.0}
    assert candidate["p99_ms"] == {"10000": 1.25, "100000": 10.25}


def test_diagnostic_run_can_never_select_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(selection, "_select_candidate", lambda candidates: "field-channel-rrf-k60")

    report = run_selection(
        EvaluationConfig(
            size=12,
            candidates=("field-channel-rrf-k60",),
            git_state=GitState(source_revision="abc123", git_dirty=False),
        )
    )

    assert report.selected_candidate is None
    assert report.metadata["promotion_mode"] is False
    assert report.metadata["promotion_eligible"] is False


def test_promotion_skips_large_scale_when_no_candidate_clears_quality_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_sizes: list[int] = []

    def fake_scale_setup(
        root: Path, size: int, config: EvaluationConfig, *, retain_quality: bool
    ) -> tuple[CorpusResult, selection._MeasuredRun]:
        del root, config, retain_quality
        setup_sizes.append(size)
        return _fake_corpus(size), _fake_measured(1.0)

    monkeypatch.setattr(selection, "_run_scale_setup", fake_scale_setup)
    monkeypatch.setattr(selection, "_run_candidate_pair", lambda **kwargs: _fake_measured(1.0))
    monkeypatch.setattr(selection, "_eligible_for_large_scale", lambda baseline, candidate: False)

    report = run_selection(
        EvaluationConfig(
            promotion_mode=True,
            candidates=("field-channel-rrf-k60",),
            git_state=GitState(source_revision="abc123", git_dirty=False),
        )
    )

    assert setup_sizes == [10_000]
    assert report.selected_candidate is None
    assert report.metadata["requested_corpus_sizes"] == [10_000]


def test_large_scale_eligibility_accepts_high_baseline_non_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _fake_measured(20.0)
    candidate = _fake_measured(21.0)
    _patch_quality_metrics(
        monkeypatch,
        baseline=CandidateMetrics(
            hard_recall_at_10=0.98,
            hard_mrr=0.97,
            recall_at_10={"overall": 0.96, "easy": 0.95, "medium": 0.95},
            tokens_per_correct_hard_query=100.0,
            p99_ms={},
            complete=True,
        ),
        candidate=CandidateMetrics(
            hard_recall_at_10=0.98,
            hard_mrr=0.97,
            recall_at_10={"overall": 0.96, "easy": 0.95, "medium": 0.95},
            tokens_per_correct_hard_query=80.0,
            p99_ms={},
            complete=True,
        ),
    )

    assert selection._eligible_for_large_scale(baseline, candidate) is True


def test_large_scale_eligibility_requires_delta_when_baseline_below_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _fake_measured(20.0)
    candidate = _fake_measured(21.0)
    _patch_quality_metrics(
        monkeypatch,
        baseline=CandidateMetrics(
            hard_recall_at_10=0.70,
            hard_mrr=0.70,
            recall_at_10={"overall": 0.8666666666666667, "easy": 0.95, "medium": 0.95},
            tokens_per_correct_hard_query=100.0,
            p99_ms={},
            complete=True,
        ),
        candidate=CandidateMetrics(
            hard_recall_at_10=0.749,
            hard_mrr=0.749,
            recall_at_10={"overall": 0.883, "easy": 0.95, "medium": 0.95},
            tokens_per_correct_hard_query=80.0,
            p99_ms={},
            complete=True,
        ),
    )

    assert selection._eligible_for_large_scale(baseline, candidate) is False


def test_incomplete_large_scale_retains_closed_failure_and_scale_status() -> None:
    large_candidate = selection._replace_completion(
        _fake_measured(2.0), complete=False, stop_reason="incomplete_search"
    )

    result = selection._candidate_selection(
        name="field-channel-rrf-k60",
        baselines={10_000: _fake_measured(1.0), 100_000: _fake_measured(2.0)},
        candidates={10_000: _fake_measured(1.0), 100_000: large_candidate},
        corpora={10_000: _fake_corpus(10_000), 100_000: _fake_corpus(100_000)},
        config=EvaluationConfig(promotion_mode=True, candidates=("field-channel-rrf-k60",)),
        git_state=GitState(source_revision="abc123", git_dirty=False),
    )

    assert result.passed is False
    assert result.failures[0].category == "incomplete_search"
    assert result.scales[100_000]["candidate"] == {
        "query_count": 1,
        "p99_ms": 2.0,
        "complete": False,
        "stop_reason": "incomplete_search",
    }


@pytest.mark.parametrize(("seed", "top_k"), [(7, 10), (42, 5)])
def test_promotion_rejects_noncanonical_seed_or_top_k(seed: int, top_k: int) -> None:
    with pytest.raises(ValueError, match="requires seed=42 and top_k=10"):
        run_selection(
            EvaluationConfig(
                promotion_mode=True,
                seed=seed,
                top_k=top_k,
                candidates=("field-channel-rrf-k60",),
            )
        )


def test_selection_failure_categories_are_closed_and_bounded(tmp_path: Path) -> None:
    report = run_selection(
        EvaluationConfig(
            size=12,
            candidates=("rgapi-0.1.22",),
            git_state=GitState(source_revision="abc123", git_dirty=False),
        )
    )

    assert {failure.category for failure in report.failures} <= CLOSED_FAILURE_CATEGORIES
    for failure in report.failures:
        assert len(failure.reason) <= 120
        assert "\n" not in failure.reason


def test_selection_rejects_missing_family_or_failed_workload_floor() -> None:
    metrics = WorkloadMetrics(
        recall_at_10=0.89,
        mrr=0.60,
        ndcg_at_10=0.80,
        hard_recall_at_10=0.80,
        hard_mrr=0.80,
        by_family={"alias": 0.90},
    )
    assert validate_workload_metrics(metrics).passed is False


def test_selection_rejects_failed_hard_mrr_workload_floor() -> None:
    metrics = WorkloadMetrics(
        recall_at_10=0.90,
        mrr=0.80,
        ndcg_at_10=0.75,
        hard_recall_at_10=0.90,
        hard_mrr=0.79,
        by_family={"alias": 0.90},
    )

    verdict = validate_workload_metrics(metrics)

    assert verdict.passed is False
    assert verdict.gates["hard_mrr"] is False


def test_selection_treats_hard_floor_as_inapplicable_without_hard_queries() -> None:
    metrics = WorkloadMetrics(
        recall_at_10=0.90,
        mrr=0.50,
        ndcg_at_10=0.75,
        hard_recall_at_10=0.0,
        hard_mrr=0.0,
        by_family={"book-title": 0.90},
        hard_query_count=0,
    )

    verdict = validate_workload_metrics(metrics)

    assert verdict.passed is True
    assert verdict.gates["hard_recall_at_10"] is True
    assert verdict.gates["hard_mrr"] is True


def test_selection_report_includes_workload_manifest_and_ndcg() -> None:
    measured = _fake_measured(1.0)

    result = selection._candidate_selection(
        name="field-channel-rrf-k60",
        baselines={10_000: measured},
        candidates={10_000: measured},
        corpora={10_000: _fake_corpus(10_000)},
        config=EvaluationConfig(
            promotion_mode=True,
            candidates=("field-channel-rrf-k60",),
            workloads=("realistic", "gutenberg", "salesforce"),
        ),
        git_state=GitState(source_revision="abc123", git_dirty=False),
    )

    workload_metrics = cast(dict[str, selection.JsonValue], result.to_dict()["workload_metrics"])
    overall = cast(dict[str, selection.JsonValue], workload_metrics["overall"])
    by_workload = cast(dict[str, selection.JsonValue], workload_metrics["by_workload"])
    realistic = cast(dict[str, selection.JsonValue], by_workload["realistic"])
    realistic_family = cast(dict[str, selection.JsonValue], realistic["by_family"])

    assert result.to_dict()["workload_manifest"] == [
        {"name": "realistic", "fixture_version": "generated", "source_manifest": "seed-42"},
        {
            "name": "gutenberg",
            "fixture_version": "eval/data/gutenberg-books.jsonl",
            "source_manifest": "gutenberg-books.jsonl provenance",
        },
        {
            "name": "salesforce",
            "fixture_version": "eval/data/salesforce-facts.jsonl",
            "source_manifest": "salesforce-facts.jsonl citations",
        },
    ]
    assert overall["ndcg_at_10"] == 1.0
    assert realistic_family["unit"] == 1.0


def test_large_selection_manifest_is_bounded_by_family_and_difficulty() -> None:
    queries = [
        QuerySpec(f"query {index}", ["target"], "hard", family="unit", corpus="realistic")
        for index in range(selection.SELECTION_QUERY_BOUND_THRESHOLD + 1)
    ]

    bounded = selection._bound_query_manifest(queries)

    assert len(bounded) == selection.SELECTION_MAX_QUERIES_PER_GROUP
    assert bounded[0].query == "query 0"


def test_retained_report_excludes_prohibited_content_canaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory_canary = "PRIVATE-MEMORY-CONTENT-7f91"
    credential_canary = "sk-live-CREDENTIAL-7f91"
    query_canary = "raw private query 7f91"
    stack_canary = 'Traceback (most recent call last): File "/private/secret.py"'
    original_generate = selection._generate_snapshot

    def generate_with_canaries(
        snapshot_dir: Path,
        *,
        size: int,
        seed: int,
        workloads: tuple[selection.WorkloadName, ...] = ("realistic",),
    ) -> CorpusResult:
        corpus = original_generate(snapshot_dir, size=size, seed=seed, workloads=workloads)
        corpus.queries[0].query = f"{query_canary} {credential_canary}"
        page = next((snapshot_dir / "docs").rglob("*.md"))
        page.write_text(
            page.read_text(encoding="utf-8") + f"\n{memory_canary}\n{stack_canary}\n",
            encoding="utf-8",
        )
        return corpus

    monkeypatch.setattr(selection, "_generate_snapshot", generate_with_canaries)
    evidence_dir = tmp_path / "profile-alice-secret" / "evidence"
    data_root = tmp_path / "profile-alice-secret" / "paired"
    report = run_selection(
        EvaluationConfig(
            size=12,
            evidence_dir=evidence_dir,
            data_root=data_root,
            candidates=("field-channel-rrf-k60",),
            git_state=GitState(source_revision="abc123", git_dirty=False),
        )
    )

    retained = (evidence_dir / "selection-12.json").read_text(encoding="utf-8")
    prohibited = (
        memory_canary,
        credential_canary,
        query_canary,
        stack_canary,
        str(tmp_path),
        str(Path.home()),
        getpass.getuser(),
        platform.node(),
    )
    assert report.report_path is not None
    assert all(value not in retained for value in prohibited if value)


def _fake_corpus(size: int) -> CorpusResult:
    return CorpusResult(
        memories_written=size,
        queries=[QuerySpec("hard query", ["target"], "hard", family="unit", corpus="realistic")],
    )


def _fake_measured(p99_ms: float) -> selection._MeasuredRun:
    hit = _recall_hit("target", snippet="hard query")
    result = HitResult("hard query", "hard", ["target"], ["target"], 1, p99_ms)
    observation = QueryContextObservation(
        query="hard query",
        difficulty="hard",
        expected_slugs=["target"],
        hits=[hit],
    )
    summary = selection.RunSummary(1, (0,), (("target",),), p99_ms, 1, 0, True)
    return selection._MeasuredRun([result], [observation], summary, {"name": "fake"})


def _patch_quality_metrics(
    monkeypatch: pytest.MonkeyPatch,
    *,
    baseline: CandidateMetrics,
    candidate: CandidateMetrics,
) -> None:
    calls = iter((baseline, candidate))

    def fake_quality_metrics(
        measured: selection._MeasuredRun,
        p99_ms: dict[int, float],
        *,
        complete: bool | None = None,
    ) -> CandidateMetrics:
        del measured, p99_ms, complete
        return next(calls)

    monkeypatch.setattr(selection, "_quality_metrics", fake_quality_metrics)


def _recall_hit(slug: str, *, snippet: str = "hard query") -> RecallHit:
    return RecallHit(
        slug=slug,
        file_path=f"docs/{slug}.md",
        title=slug.title(),
        node_type="entity",
        importance=0.5,
        score=0.0,
        rank=1,
        snippet="hard query",
        snippet_source="body",
        tags=[],
        created="2026-01-01T00:00:00Z",
        updated="2026-01-01T00:00:00Z",
        last_access=None,
        transcript_ref=None,
        links=[],
        status="active",
    )
