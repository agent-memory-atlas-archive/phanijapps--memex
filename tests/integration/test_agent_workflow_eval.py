"""Goal-shaped recall through the real Memex index in an isolated store."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Literal, cast

import pytest

from eval import agent_workflow, task_evidence_model
from eval.agent_workflow import (
    RENDERED_FILE_SLUG,
    BenchmarkReport,
    RecallCost,
    StrategyReport,
    TaskStrategyResult,
    _summary_links,
    load_fixture,
    load_human_focused_queries,
    run_benchmark,
)
from eval.task_evidence_model import (
    HarnessQuestionPlanner,
    ModelRunLimits,
    ModelUsage,
    QuestionPlan,
    QuestionRun,
    pi_question_planner,
    run_model_comparison,
)
from memex.application.memory import Memex
from memex.domain.models import RecallHit
from memex.domain.slugs import slugify

SUMMARY_SOURCE = Path("eval/data/coding-agent-workflow-summary-source.json")
BASELINE_REPORT = Path("docs/research/2026-09-20-task-evidence-baseline.md")


def _recall_hit(slug: str, rank: int) -> RecallHit:
    return RecallHit(
        slug=slug,
        file_path=f"docs/projects/current/summaries/{slug}.md",
        title=slug.title(),
        node_type="summary",
        importance=0.5,
        score=0.0,
        rank=rank,
        snippet="summary",
        snippet_source="body",
        tags=[],
        created="2026-01-01T00:00:00Z",
        updated="2026-01-01T00:00:00Z",
        last_access=None,
        transcript_ref=None,
        links=[],
        status="active",
        scope="project",
        project_id="project-1",
    )


def _strategy_label(name: str) -> str:
    return {
        "current_injection": "Current hook injection",
        "broad_query": "One broad query",
        "human_focused": "Human-written focused queries",
        "linked_summary": "Linked task summary",
    }[name]


def _report_strategy_metrics(markdown: str) -> dict[str, tuple[int, str, int, int, int, int]]:
    metrics: dict[str, tuple[int, str, int, int, int, int]] = {}
    for line in markdown.splitlines():
        if not line.startswith("|") or "/24" not in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 8:
            continue
        complete, total = cells[1].split("/")
        assert total == "24"
        metrics[cells[0]] = (
            int(complete),
            cells[2],
            int(cells[3]),
            int(cells[4].replace(",", "")),
            int(cells[6]),
            int(cells[7]),
        )
    return metrics


def _benchmark_strategy_metrics(
    report: BenchmarkReport,
) -> dict[str, tuple[int, str, int, int, int, int]]:
    return {
        _strategy_label(name): (
            strategy.task_complete,
            f"{strategy.fact_recall:.2%}",
            strategy.calls,
            strategy.rendered_tokens,
            strategy.inactive_hits,
            strategy.other_project_hits,
        )
        for name, strategy in report.strategies.items()
    }


def _pinned_source_text(revision: str, source: str, root: Path) -> str:
    return subprocess.check_output(  # noqa: S603
        ["git", "show", f"{revision}:{source}"],  # noqa: S607
        cwd=root,
        text=True,
    )


def _json_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for item in value.values():
            keys.update(_json_keys(item))
        return keys
    if isinstance(value, list):
        nested_keys: set[str] = set()
        for item in value:
            nested_keys.update(_json_keys(item))
        return nested_keys
    return set()


def test_workflow_fixture_has_traceable_and_complete_labels() -> None:
    fixture = load_fixture()
    root = Path(__file__).resolve().parents[2]
    current = [memory for memory in fixture["memories"] if memory["scope"] == "project"]

    assert len(fixture["source_revision"]) == 40
    assert all(
        not memory.get("archive") or memory["source"].startswith("simulated") for memory in current
    )
    for source, expected_hash in fixture["source_hashes"].items():
        assert not source.startswith("eval/data/")
        source_text = _pinned_source_text(fixture["source_revision"], source, root)
        assert hashlib.sha256(source_text.encode()).hexdigest() == expected_hash
    for memory in current:
        if memory.get("archive"):
            continue
        assert not memory["source"].startswith("eval/data/")
        assert memory["source"] in fixture["source_hashes"]
        source_text = " ".join(
            _pinned_source_text(
                fixture["source_revision"],
                memory["source"],
                root,
            ).split()
        )
        assert " ".join(memory["body"].split()) in source_text
    assert len({memory["title"] for memory in fixture["memories"]}) == len(fixture["memories"])
    assert len({slugify(memory["title"]) for memory in fixture["memories"]}) == len(
        fixture["memories"]
    )
    assert len(fixture["tasks"]) >= 24
    assert len(fixture["memories"]) >= 100
    assert all(task["required"] for task in fixture["tasks"])
    active_slugs = {slugify(memory["title"]) for memory in current if not memory.get("archive")}
    assert all(set(task["required"]) <= active_slugs for task in fixture["tasks"])


def test_summary_source_hides_labels_and_query_plans() -> None:
    fixture = load_fixture()
    root = Path(__file__).resolve().parents[2]
    projection = json.loads((root / SUMMARY_SOURCE).read_text(encoding="utf-8"))

    assert [task["name"] for task in projection["tasks"]] == [
        task["name"] for task in fixture["tasks"]
    ]
    assert all(set(task) == {"name", "goal"} for task in projection["tasks"])
    assert "required" not in _json_keys(projection)
    assert "focused_queries" not in _json_keys(projection)
    assert len(projection["eligible_pages"]) >= 80


def test_linked_summary_fixture_has_parseable_source_links() -> None:
    fixture = load_fixture()
    root = Path(__file__).resolve().parents[2]
    summaries = json.loads((root / "eval/data/task-linked-summaries.json").read_text())

    assert [summary["task"] for summary in summaries["summaries"]] == [
        task["name"] for task in fixture["tasks"]
    ]
    assert all(_summary_links(summary["body"]) for summary in summaries["summaries"])


def test_summary_links_reject_malformed_wiki_link_start() -> None:
    with pytest.raises(ValueError, match="malformed wiki link"):
        _summary_links("Valid [[source-card]] and broken [[missing-close")


def test_human_focused_queries_are_label_blind_and_ordered() -> None:
    fixture = load_fixture()
    queries = load_human_focused_queries()
    serialized_queries = json.dumps(queries)

    assert [task["name"] for task in queries["tasks"]] == [
        task["name"] for task in fixture["tasks"]
    ]
    assert all(0 < len(task["queries"]) <= 3 for task in queries["tasks"])
    assert "required" not in _json_keys(queries)
    assert "focused_queries" not in _json_keys(queries)
    for task in fixture["tasks"]:
        for required_slug in task["required"]:
            assert required_slug not in serialized_queries


def test_hook_hit_scoring_ignores_paths_inside_memory_text() -> None:
    block = (
        "   File: /tmp/docs/projects/current/entities/actual.md\n"
        "   See /tmp/docs/projects/other/entities/mentioned.md in a note."
    )

    assert RENDERED_FILE_SLUG.findall(block) == ["actual"]


def test_real_workflow_recall_keeps_scopes_and_recovers_task_evidence() -> None:
    report = run_benchmark()

    assert report.memory_count >= 100
    assert report.task_count >= 24
    assert report.excluded_memory_count >= 12
    assert set(report.strategies) == {
        "current_injection",
        "broad_query",
        "linked_summary",
        "human_focused",
    }
    expected_metrics = {
        "current_injection": (5, 0.4375, 24, 14988, 0, 0),
        "broad_query": (7, 0.546875, 24, 16362, 0, 0),
        "human_focused": (12, 0.734375, 72, 14559, 0, 0),
        "linked_summary": (11, 0.703125, 24, 4485, 0, 0),
    }
    for name, strategy in report.strategies.items():
        assert (
            strategy.task_complete,
            strategy.fact_recall,
            strategy.calls,
            strategy.rendered_tokens,
            strategy.inactive_hits,
            strategy.other_project_hits,
        ) == expected_metrics[name]
        assert strategy.latency_ms > 0
        assert all(len(task.hits) <= 8 for task in strategy.tasks)
    root = Path(__file__).resolve().parents[2]
    report_markdown = (root / BASELINE_REPORT).read_text(encoding="utf-8")
    assert _report_strategy_metrics(report_markdown) == _benchmark_strategy_metrics(report)


def test_linked_summary_result_credits_only_first_retrieved_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int, str | None]] = []

    def fake_recall(
        memex: Memex,
        query: str,
        project_id: str,
        top_k: int,
        *,
        node_type: str | None = None,
    ) -> tuple[list[RecallHit], float]:
        del memex, project_id
        calls.append((query, top_k, node_type))
        return [_recall_hit("first-summary", 1), _recall_hit("second-summary", 2)], 7.0

    monkeypatch.setattr(agent_workflow, "_recall", fake_recall)

    result = agent_workflow._linked_summary_result(
        memex=cast(Memex, object()),
        task={"name": "Task", "goal": "find the task summary", "required": ["needed"]},
        project_id="project-1",
        summary_bodies={
            "first-summary": "Use [[needed]] only.",
            "second-summary": "Do not credit [[leaked]].",
        },
        inactive=set(),
        other_project=set(),
    )

    assert calls == [("find the task summary", 1, "summary")]
    assert result.hits == ["needed"]
    assert result.missing == []
    assert result.cost.calls == 1


def test_model_comparison_blocks_harness_without_cost_observable_path() -> None:
    report = run_model_comparison(
        HarnessQuestionPlanner(
            harness="missing-harness",
            argv=(sys.executable,),
            prompt_template="{name}\n{goal}",
            model_id="fake/model",
        ),
        ModelRunLimits(wall_seconds=300, spend_limit_usd=5.0),
    )

    assert report.question_run.status == "blocked"
    assert report.question_run.wall_limit_seconds == 300
    assert report.question_run.spend_limit_usd == 5.0
    assert report.candidate is None
    assert report.promotion_gate.promoted is False
    assert report.promotion_gate.recall_gate_passed is False
    assert report.promotion_gate.verdict.startswith("unpromoted:")


def test_harness_run_reserves_worst_case_spend_before_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("subprocess must not run without remaining spend reserve")

    monkeypatch.setattr(task_evidence_model, "_run_command", fail_run)

    planner = HarnessQuestionPlanner(
        harness="fake",
        argv=(sys.executable,),
        prompt_template="{goal}",
        model_id="fake/model",
        price_per_1k_prompt_tokens_usd=1.0,
        price_per_1k_completion_tokens_usd=1.0,
        max_completion_tokens=10_000,
        cost_source="test upper bound",
    )
    run = planner.plan(
        [{"name": "Task", "goal": "tiny goal"}],
        ModelRunLimits(wall_seconds=300, spend_limit_usd=5.0),
    )

    assert run.status == "incomplete"
    assert run.blocked_reason == "spend reserve"
    assert run.plans == []


def test_pi_planner_isolated_question_selection_flags() -> None:
    planner = pi_question_planner(
        billing_mode="plan_credits",
        cost_source="ZCode coding plan",
        model_id="zai-coding-cn/glm-5.3-flash",
    )

    assert planner.argv == (
        "pi",
        "--mode",
        "json",
        "--print",
        "--model",
        "zai-coding-cn/glm-5.3-flash",
        "--no-tools",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-context-files",
        "--no-approve",
        "--offline",
        "--no-session",
    )
    assert planner.prompt_template.format(name="Task", goal="Goal").count('"queries"') == 1


def test_plan_credit_billing_mode_allows_zero_usd_dollar_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = json.dumps(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": json.dumps({"queries": ["first"]})}],
                "usage": {"input": 5, "output": 3, "cost": {"total": 0.7}},
            },
        }
    )

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["fake"], returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(task_evidence_model, "_run_command", fake_run)
    planner = HarnessQuestionPlanner(
        harness="fake",
        argv=(sys.executable,),
        prompt_template="{goal}",
        model_id="fake/model",
        cost_source="verified coding-plan credit mode",
        billing_mode="plan_credits",
        price_per_1k_prompt_tokens_usd=0.001,
        price_per_1k_completion_tokens_usd=0.001,
        max_completion_tokens=100,
    )

    run = planner.plan(
        [{"name": "Task", "goal": "tiny goal"}],
        ModelRunLimits(wall_seconds=300, spend_limit_usd=5.0),
    )

    assert run.status == "complete"
    assert run.model_id == "fake/model"
    assert run.billing_mode == "plan_credits"
    assert run.usage.spend_usd == 0
    assert run.usage.catalog_estimate_usd == 0.7
    assert len(run.plans) == 1
    assert run.plans[0].task == "Task"
    assert run.plans[0].queries == ["first"]
    assert run.plans[0].usage.prompt_tokens == 5
    assert run.plans[0].usage.completion_tokens == 3
    assert run.plans[0].usage.catalog_estimate_usd == 0.7


def test_plan_credit_billing_mode_still_enforces_catalog_equivalent_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("subprocess must not run beyond catalog-equivalent reserve")

    monkeypatch.setattr(task_evidence_model, "_run_command", fail_run)
    planner = HarnessQuestionPlanner(
        harness="fake",
        argv=(sys.executable,),
        prompt_template="{goal}",
        model_id="fake/model",
        price_per_1k_prompt_tokens_usd=1.0,
        price_per_1k_completion_tokens_usd=1.0,
        max_completion_tokens=10_000,
        cost_source="verified coding-plan catalog estimate",
        billing_mode="plan_credits",
    )

    run = planner.plan(
        [{"name": "Task", "goal": "tiny goal"}],
        ModelRunLimits(wall_seconds=300, spend_limit_usd=5.0),
    )

    assert run.status == "incomplete"
    assert run.blocked_reason == "spend reserve"
    assert run.usage.spend_usd == 0


def test_harness_malformed_output_is_incomplete_without_promotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["fake"], returncode=0, stdout="not-json", stderr=""
        )

    monkeypatch.setattr(task_evidence_model, "_run_command", fake_run)
    planner = HarnessQuestionPlanner(
        harness="fake",
        argv=(sys.executable,),
        prompt_template="{goal}",
        model_id="fake/model",
        price_per_1k_prompt_tokens_usd=0.001,
        price_per_1k_completion_tokens_usd=0.001,
        max_completion_tokens=1,
        cost_source="verified billing",
    )

    run = planner.plan(
        [{"name": "Task", "goal": "tiny goal"}],
        ModelRunLimits(wall_seconds=300, spend_limit_usd=5.0),
    )

    assert run.status == "incomplete"
    assert run.blocked_reason == "harness output"
    assert run.plans == []


def test_harness_retries_invalid_questions_and_counts_both_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        answer = "not a question plan" if calls == 1 else json.dumps({"queries": ["first"]})
        output = json.dumps(
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": answer}],
                    "usage": {"input": 10, "output": 20, "cost": {"total": 0.01}},
                },
            }
        )
        return subprocess.CompletedProcess(args=["fake"], returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(task_evidence_model, "_run_command", fake_run)
    planner = HarnessQuestionPlanner(
        harness="fake",
        argv=(sys.executable,),
        prompt_template="{goal}",
        model_id="fake/model",
        price_per_1k_prompt_tokens_usd=0.001,
        price_per_1k_completion_tokens_usd=0.001,
        max_completion_tokens=100,
        cost_source="verified catalog estimate",
    )

    run = planner.plan(
        [{"name": "Task", "goal": "tiny goal"}],
        ModelRunLimits(wall_seconds=300, spend_limit_usd=5.0),
    )

    assert calls == 2
    assert run.status == "complete"
    assert run.usage.prompt_tokens == 20
    assert run.usage.completion_tokens == 40
    assert run.usage.spend_usd == 0.02
    assert run.plans[0].usage == run.usage


@pytest.mark.parametrize("billing_mode", ["usd", "plan_credits"])
def test_billing_modes_require_usage_telemetry_before_next_call(
    monkeypatch: pytest.MonkeyPatch,
    billing_mode: Literal["usd", "plan_credits"],
) -> None:
    output = json.dumps(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": json.dumps({"queries": ["first"]})}],
            },
        }
    )

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["fake"], returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(task_evidence_model, "_run_command", fake_run)
    planner = HarnessQuestionPlanner(
        harness="fake",
        argv=(sys.executable,),
        prompt_template="{goal}",
        model_id="fake/model",
        price_per_1k_prompt_tokens_usd=0.001,
        price_per_1k_completion_tokens_usd=0.001,
        max_completion_tokens=1,
        cost_source="verified billing",
        billing_mode=billing_mode,
    )

    run = planner.plan(
        [{"name": "Task", "goal": "tiny goal"}],
        ModelRunLimits(wall_seconds=300, spend_limit_usd=5.0),
    )

    assert run.status == "incomplete"
    assert run.blocked_reason == "missing usage"
    assert run.plans == []


def test_model_comparison_passes_only_label_blind_task_inputs_to_planner() -> None:
    human_queries = load_human_focused_queries()
    seen_tasks: list[dict[str, str]] = []

    class FakePlanner:
        def plan(
            self, tasks: list[task_evidence_model.TaskQuestionInput], limits: ModelRunLimits
        ) -> QuestionRun:
            del limits
            seen_tasks.extend(cast(list[dict[str, str]], tasks))
            return QuestionRun(
                status="complete",
                harness="fake",
                model_id="fake/model",
                billing_mode="usd",
                cost_source="test",
                wall_limit_seconds=300,
                spend_limit_usd=5.0,
                elapsed_seconds=1.0,
                usage=ModelUsage(prompt_tokens=10, completion_tokens=5, spend_usd=0.01),
                plans=[
                    QuestionPlan(task=task["name"], queries=task["queries"])
                    for task in human_queries["tasks"]
                ],
            )

    report = run_model_comparison(FakePlanner())

    assert seen_tasks
    assert all(set(task) == {"name", "goal"} for task in seen_tasks)
    assert report.candidate is not None
    human_focused_complete = report.baseline.strategies["human_focused"].task_complete
    assert report.candidate.task_complete == human_focused_complete
    assert report.promotion_gate.promoted is False
    assert "completed-code-check-not-run" in report.promotion_gate.failed_conditions
    assert report.promotion_gate.candidate_task_complete == 12


def test_pi_style_json_output_yields_questions_and_usage() -> None:
    output = "\n".join(
        [
            json.dumps(
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {"queries": ["first question", "second question"]}
                                ),
                            }
                        ],
                        "usage": {
                            "input": 1200,
                            "output": 300,
                            "cost": {"total": 0.004},
                        },
                    },
                }
            ),
        ]
    )

    parsed = task_evidence_model._parse_harness_json(output)

    assert parsed["queries"] == ["first question", "second question"]
    usage = parsed["usage"]
    assert isinstance(usage, ModelUsage)
    assert usage.prompt_tokens == 1200
    assert usage.completion_tokens == 300
    assert usage.spend_usd == 0.004


def test_p95_latency_uses_nearest_rank_for_24_tasks() -> None:
    latencies = [1.0] * 22 + [100.0, 200.0]
    tasks = [
        TaskStrategyResult(
            name=str(index),
            hits=[],
            missing=[],
            cost=RecallCost(calls=1, rendered_tokens=1, latency_ms=latency),
            inactive_hits=[],
            other_project_hits=[],
        )
        for index, latency in enumerate(latencies)
    ]
    strategy = StrategyReport(0, 0.0, 24, 24, 0.0, 0, 0, tasks)

    assert task_evidence_model._strategy_p95_latency(strategy) == 100.0
