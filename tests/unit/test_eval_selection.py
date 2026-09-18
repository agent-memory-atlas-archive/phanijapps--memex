from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import eval.selection as selection
from eval.comparison import QueryContextObservation
from eval.corpus import CorpusResult, QuerySpec
from eval.runner import HitResult
from eval.selection import (
    CLOSED_FAILURE_CATEGORIES,
    EvaluationConfig,
    GitState,
    run_selection,
    stable_selection_payload,
)
from memex.domain.models import RecallHit


def test_selection_refuses_nonempty_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "evidence"
    output_dir.mkdir()
    (output_dir / "keep.txt").write_text("leave me alone", encoding="utf-8")

    with pytest.raises(ValueError, match="must be empty"):
        run_selection(
            EvaluationConfig(size=12, evidence_dir=output_dir, candidates=("weighted-lexical-rrf",))
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
                candidates=("weighted-lexical-rrf",),
            )
        )

    assert marker.read_text(encoding="utf-8") == "leave me alone"
    assert not evidence_dir.exists()


def test_selection_writes_sanitized_schema_and_blocks_dirty_promotion(tmp_path: Path) -> None:
    output_dir = tmp_path / "evidence"

    report = run_selection(
        EvaluationConfig(
            size=12,
            evidence_dir=output_dir,
            candidates=("weighted-lexical-rrf",),
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
        candidates=("weighted-lexical-rrf",),
        git_state=GitState(source_revision="abc123", git_dirty=False),
    )

    first = run_selection(config)
    second = run_selection(config)

    assert stable_selection_payload(first) == stable_selection_payload(second)


def test_selection_uses_independent_paired_stores(tmp_path: Path) -> None:
    report = run_selection(
        EvaluationConfig(
            size=12,
            candidates=("weighted-lexical-rrf",),
            git_state=GitState(source_revision="abc123", git_dirty=False),
        )
    )
    weighted = report.candidates["weighted-lexical-rrf"]

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
        name="weighted-lexical-rrf",
        snapshot_dir=snapshot_dir,
        data_dir=tmp_path / "candidate-paired",
        corpus=corpus,
        top_k=10,
    )
    clean = selection._run_candidate_pair(
        name="weighted-lexical-rrf",
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
            candidates=("weighted-lexical-rrf",),
            git_state=GitState(source_revision="abc123", git_dirty=False),
        )
    )

    assert setup_sizes == [10_000, 100_000]
    assert candidate_sizes == [10_000, 100_000]
    comparison = report.candidates["weighted-lexical-rrf"].comparison
    baseline = cast(dict[str, selection.JsonValue], comparison["baseline"])
    candidate = cast(dict[str, selection.JsonValue], comparison["candidate"])
    assert baseline["p99_ms"] == {"10000": 1.0, "100000": 10.0}
    assert candidate["p99_ms"] == {"10000": 1.25, "100000": 10.25}


def test_diagnostic_run_can_never_select_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(selection, "_select_candidate", lambda candidates: "weighted-lexical-rrf")

    report = run_selection(
        EvaluationConfig(
            size=12,
            candidates=("weighted-lexical-rrf",),
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
            candidates=("weighted-lexical-rrf",),
            git_state=GitState(source_revision="abc123", git_dirty=False),
        )
    )

    assert setup_sizes == [10_000]
    assert report.selected_candidate is None
    assert report.metadata["requested_corpus_sizes"] == [10_000]


@pytest.mark.parametrize(("seed", "top_k"), [(7, 10), (42, 5)])
def test_promotion_rejects_noncanonical_seed_or_top_k(seed: int, top_k: int) -> None:
    with pytest.raises(ValueError, match="requires seed=42 and top_k=10"):
        run_selection(
            EvaluationConfig(
                promotion_mode=True,
                seed=seed,
                top_k=top_k,
                candidates=("weighted-lexical-rrf",),
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


def _fake_corpus(size: int) -> CorpusResult:
    return CorpusResult(
        memories_written=size,
        queries=[QuerySpec("hard query", ["target"], "hard")],
    )


def _fake_measured(p99_ms: float) -> selection._MeasuredRun:
    hit = RecallHit(
        slug="target",
        file_path="docs/target.md",
        title="Target",
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
    result = HitResult("hard query", "hard", ["target"], ["target"], 1, p99_ms)
    observation = QueryContextObservation(
        query="hard query",
        difficulty="hard",
        expected_slugs=["target"],
        hits=[hit],
    )
    summary = selection.RunSummary(1, (0,), (("target",),), p99_ms, 1, 0, True)
    return selection._MeasuredRun([result], [observation], summary, {"name": "fake"})
