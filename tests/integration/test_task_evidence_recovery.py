"""One shared model ceiling across prior and fresh task-evidence cohorts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from eval import task_evidence_model
from eval.agent_workflow import BenchmarkReport, Fixture, LinkedSummaryFixture, StrategyReport
from eval.task_evidence_model import (
    ModelRunLimits,
    ModelUsage,
    QuestionPlan,
    QuestionRun,
    RecoveryHoldout,
    TaskQuestionInput,
    run_recovery_comparison,
)

HOLDOUT = Path("eval/data/task-evidence-holdout-v2.json")
SUMMARIES = Path("eval/data/task-evidence-holdout-v2-summaries.json")


def test_recovery_comparison_uses_one_label_blind_model_run(tmp_path: Path) -> None:
    received: list[list[TaskQuestionInput]] = []
    approved_limits = ModelRunLimits(wall_seconds=300, spend_limit_usd=5.0)

    class FakePlanner:
        def plan(self, tasks: list[TaskQuestionInput], limits: ModelRunLimits) -> QuestionRun:
            assert 0 < limits.wall_seconds <= approved_limits.wall_seconds
            assert limits.spend_limit_usd == approved_limits.spend_limit_usd
            received.append(tasks)
            return QuestionRun(
                status="complete",
                harness="fake",
                model_id="fake/model",
                billing_mode="usd",
                cost_source="test",
                wall_limit_seconds=limits.wall_seconds,
                spend_limit_usd=limits.spend_limit_usd,
                elapsed_seconds=1.0,
                usage=ModelUsage(prompt_tokens=len(tasks), completion_tokens=len(tasks)),
                plans=[
                    QuestionPlan(
                        task=task["name"],
                        queries=[task["goal"]],
                        usage=ModelUsage(prompt_tokens=1, completion_tokens=1),
                    )
                    for task in tasks
                ],
            )

    holdout = RecoveryHoldout(
        fixture=cast(Fixture, json.loads(HOLDOUT.read_text(encoding="utf-8"))),
        linked_summaries=cast(
            LinkedSummaryFixture, json.loads(SUMMARIES.read_text(encoding="utf-8"))
        ),
        evidence_dir=tmp_path,
    )
    report = run_recovery_comparison(FakePlanner(), approved_limits, holdout)

    assert len(received) == 1
    assert len(received[0]) == 32
    assert all(set(task) == {"name", "goal"} for task in received[0])
    assert report.question_run.status == "complete"
    assert report.previous.baseline.task_count == 24
    assert report.holdout.baseline.task_count == 8
    assert report.previous.candidate is not None
    assert report.holdout.candidate is not None
    assert report.previous.question_run.usage.prompt_tokens == 24
    assert report.holdout.question_run.usage.prompt_tokens == 8
    for filename, expected_count in (("previous-tasks.json", 24), ("fresh-tasks.json", 8)):
        path = tmp_path / filename
        export = json.loads(path.read_text(encoding="utf-8"))
        assert export["status"] == "complete"
        assert len(export["tasks"]) == expected_count
        assert "goal" not in path.read_text(encoding="utf-8")
        assert "queries" not in path.read_text(encoding="utf-8")
    for filename, expected_strategies, expected_count in (
        (
            "previous-baselines.json",
            {"current_injection", "broad_query", "linked_summary", "human_focused"},
            24,
        ),
        ("fresh-baselines.json", {"current_injection", "broad_query", "linked_summary"}, 8),
    ):
        path = tmp_path / filename
        export = json.loads(path.read_text(encoding="utf-8"))
        assert set(export["strategies"]) == expected_strategies
        assert all(len(rows) == expected_count for rows in export["strategies"].values())
        assert "goal" not in path.read_text(encoding="utf-8")
        assert "queries" not in path.read_text(encoding="utf-8")
    assert json.loads((tmp_path / "budget.json").read_text(encoding="utf-8"))["status"] == "closed"
    with pytest.raises(ValueError, match="closed"):
        run_recovery_comparison(FakePlanner(), approved_limits, holdout)


def test_recovery_blocks_model_when_baselines_use_wall_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_strategy = StrategyReport(0, 0.0, 0, 0, 0.0, 0, 0, [])
    baseline = BenchmarkReport(
        source_revision="test",
        memory_count=0,
        active_memory_count=0,
        excluded_memory_count=0,
        task_count=0,
        linked_summary_count=0,
        strategies={"broad_query": empty_strategy, "linked_summary": empty_strategy},
    )
    monkeypatch.setattr(task_evidence_model, "run_benchmark", lambda: baseline)
    monkeypatch.setattr(
        task_evidence_model, "run_benchmark_for_fixture", lambda fixture, summaries: baseline
    )
    clock = iter((0.0, 301.0, 302.0))
    monkeypatch.setattr(
        task_evidence_model, "time", SimpleNamespace(monotonic=lambda: next(clock, 303.0))
    )

    class UnexpectedPlanner:
        def plan(self, tasks: list[TaskQuestionInput], limits: ModelRunLimits) -> QuestionRun:
            raise AssertionError("model must not start after the wall limit")

    holdout = RecoveryHoldout(
        fixture=cast(Fixture, json.loads(HOLDOUT.read_text(encoding="utf-8"))),
        linked_summaries=cast(
            LinkedSummaryFixture, json.loads(SUMMARIES.read_text(encoding="utf-8"))
        ),
        evidence_dir=tmp_path,
    )
    report = run_recovery_comparison(UnexpectedPlanner(), ModelRunLimits(), holdout)

    assert report.question_run.status == "blocked"
    assert report.question_run.blocked_reason == "comparison time"
    assert report.previous.candidate is None
    assert report.holdout.candidate is None
    assert json.loads((tmp_path / "fresh-tasks.json").read_text(encoding="utf-8"))["tasks"] == []
    assert (tmp_path / "fresh-baselines.json").exists()


def test_recovery_retry_uses_remaining_approved_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_strategy = StrategyReport(0, 0.0, 0, 0, 0.0, 0, 0, [])
    baseline = BenchmarkReport(
        "test", 0, 0, 0, 0, 0, {"broad_query": empty_strategy, "linked_summary": empty_strategy}
    )
    monkeypatch.setattr(task_evidence_model, "run_benchmark", lambda: baseline)
    monkeypatch.setattr(
        task_evidence_model, "run_benchmark_for_fixture", lambda fixture, summaries: baseline
    )
    received: list[ModelRunLimits] = []

    class PartialPlanner:
        def plan(self, tasks: list[TaskQuestionInput], limits: ModelRunLimits) -> QuestionRun:
            received.append(limits)
            return QuestionRun(
                status="incomplete",
                harness="fake",
                model_id="fake/model",
                billing_mode="usd",
                cost_source="test",
                wall_limit_seconds=limits.wall_seconds,
                spend_limit_usd=limits.spend_limit_usd,
                elapsed_seconds=0.0,
                usage=ModelUsage(spend_usd=1.0),
                plans=[],
                blocked_reason="prompt bound",
            )

    holdout = RecoveryHoldout(
        fixture=cast(Fixture, json.loads(HOLDOUT.read_text(encoding="utf-8"))),
        linked_summaries=cast(
            LinkedSummaryFixture, json.loads(SUMMARIES.read_text(encoding="utf-8"))
        ),
        evidence_dir=tmp_path,
    )
    limits = ModelRunLimits(wall_seconds=300, spend_limit_usd=5.0)
    run_recovery_comparison(PartialPlanner(), limits, holdout)
    run_recovery_comparison(PartialPlanner(), limits, holdout)

    assert len(received) == 2
    assert received[1].wall_seconds < limits.wall_seconds
    assert received[1].spend_limit_usd == 4.0
    budget = json.loads((tmp_path / "budget.json").read_text(encoding="utf-8"))
    assert budget["spend_used"] == 2.0
    assert budget["status"] == "ready"


def test_recovery_crash_keeps_budget_reserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_strategy = StrategyReport(0, 0.0, 0, 0, 0.0, 0, 0, [])
    baseline = BenchmarkReport(
        "test", 0, 0, 0, 0, 0, {"broad_query": empty_strategy, "linked_summary": empty_strategy}
    )
    monkeypatch.setattr(task_evidence_model, "run_benchmark", lambda: baseline)
    monkeypatch.setattr(
        task_evidence_model, "run_benchmark_for_fixture", lambda fixture, summaries: baseline
    )

    class CrashingPlanner:
        def plan(self, tasks: list[TaskQuestionInput], limits: ModelRunLimits) -> QuestionRun:
            raise RuntimeError("simulated interruption")

    holdout = RecoveryHoldout(
        fixture=cast(Fixture, json.loads(HOLDOUT.read_text(encoding="utf-8"))),
        linked_summaries=cast(
            LinkedSummaryFixture, json.loads(SUMMARIES.read_text(encoding="utf-8"))
        ),
        evidence_dir=tmp_path,
    )
    limits = ModelRunLimits(wall_seconds=300, spend_limit_usd=5.0)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_recovery_comparison(CrashingPlanner(), limits, holdout)
    with pytest.raises(ValueError, match="unresolved reservation"):
        run_recovery_comparison(CrashingPlanner(), limits, holdout)
