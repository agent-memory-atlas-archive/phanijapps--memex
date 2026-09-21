"""Model-backed task-evidence comparison for the held-out workflow fixture."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Protocol, TypedDict, cast

from eval.agent_workflow import (
    BenchmarkReport,
    Fixture,
    LinkedSummaryFixture,
    StrategyReport,
    _focused_result,
    _populate,
    _strategy_report,
    _validate_fixture,
    load_fixture,
    run_benchmark,
    run_benchmark_for_fixture,
)
from memex.application.context_injection import estimate_tokens
from memex.application.memory import Memex
from memex.infrastructure.config import MemexConfig

MODEL_WALL_LIMIT_SECONDS = 300
MODEL_SPEND_LIMIT_USD = 5.0
PROMOTION_MARGIN_POINTS = 10.0
_run_command = subprocess.run

_QUESTION_PROMPT = """\
You are choosing memory-recall questions before a coding task. You cannot see
the memory pages and must not answer the task.
Return JSON only, with this shape: {{"queries": ["...", "..."]}}.
Use one to three short, distinct search questions. Together they should look
for the current behavior and owner, prerequisites or scope constraints that
could change the implementation, and relevant verification or recovery rules.
Ground each question in nouns from the task and plausible adjacent concepts.
Do not repeat the broad goal, invent exact code symbols, or include explanations.

Task name: {name}
Goal: {goal}
"""


class TaskQuestionInput(TypedDict):
    name: str
    goal: str


class TaskEvidenceSnapshot(TypedDict):
    task: str
    complete: bool
    hits: list[str]
    missing: list[str]
    calls: int
    rendered_tokens: int
    latency_ms: float
    inactive_hits: int
    other_project_hits: int
    model_prompt_tokens: int
    model_completion_tokens: int
    model_catalog_estimate_usd: float


class BaselineTaskEvidenceSnapshot(TypedDict):
    task: str
    complete: bool
    hits: list[str]
    missing: list[str]
    calls: int
    rendered_tokens: int
    latency_ms: float
    inactive_hits: int
    other_project_hits: int


class RecoveryBudget(TypedDict):
    wall_limit: int
    spend_limit: float
    wall_used: float
    spend_used: float
    status: str


@dataclass(frozen=True, slots=True)
class ModelRunLimits:
    wall_seconds: int = MODEL_WALL_LIMIT_SECONDS
    spend_limit_usd: float = MODEL_SPEND_LIMIT_USD


def _finite_positive_number(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


@dataclass(frozen=True, slots=True)
class ModelUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    spend_usd: float = 0.0
    catalog_estimate_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class QuestionPlan:
    task: str
    queries: list[str]
    usage: ModelUsage = ModelUsage()


@dataclass(frozen=True, slots=True)
class QuestionRun:
    status: str
    harness: str
    model_id: str | None
    billing_mode: str
    cost_source: str | None
    wall_limit_seconds: int
    spend_limit_usd: float
    elapsed_seconds: float
    usage: ModelUsage
    plans: list[QuestionPlan]
    blocked_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PromotionGate:
    passed: bool
    promoted: bool
    recall_gate_passed: bool
    eligible_for_further_validation: bool
    candidate_task_complete: int | None
    broad_query_task_complete: int
    linked_summary_task_complete: int
    required_margin_points: float
    failed_conditions: list[str]
    verdict: str


@dataclass(frozen=True, slots=True)
class ModelComparisonReport:
    baseline: BenchmarkReport
    question_run: QuestionRun
    candidate: StrategyReport | None
    promotion_gate: PromotionGate


@dataclass(frozen=True, slots=True)
class RecoveryHoldout:
    fixture: Fixture
    linked_summaries: LinkedSummaryFixture
    evidence_dir: Path


@dataclass(frozen=True, slots=True)
class RecoveryComparisonReport:
    question_run: QuestionRun
    previous: ModelComparisonReport
    holdout: ModelComparisonReport


class QuestionPlanner(Protocol):
    """Label-blind source of task-focused questions."""

    def plan(self, tasks: list[TaskQuestionInput], limits: ModelRunLimits) -> QuestionRun: ...


@dataclass(frozen=True, slots=True)
class HarnessQuestionPlanner:
    """Run a harness print-mode command only when spend can be bounded."""

    harness: str
    argv: tuple[str, ...]
    prompt_template: str
    model_id: str | None = None
    price_per_1k_prompt_tokens_usd: float | None = None
    price_per_1k_completion_tokens_usd: float | None = None
    max_prompt_tokens: int | None = None
    max_completion_tokens: int | None = None
    cost_source: str | None = None
    billing_mode: Literal["usd", "plan_credits"] = "usd"

    def plan(self, tasks: list[TaskQuestionInput], limits: ModelRunLimits) -> QuestionRun:
        if (
            not isinstance(limits.wall_seconds, int)
            or isinstance(limits.wall_seconds, bool)
            or limits.wall_seconds <= 0
        ):
            return _blocked_question_run(
                self.harness, self, limits, "model run has no positive integer wall limit"
            )
        if not _finite_positive_number(limits.spend_limit_usd):
            return _blocked_question_run(
                self.harness, self, limits, "model run has no finite positive spend limit"
            )
        executable = self.argv[0] if self.argv else ""
        if not executable or shutil.which(executable) is None:
            return _blocked_question_run(
                self.harness,
                self,
                limits,
                f"{self.harness} command is not available on PATH",
            )
        if not self.model_id:
            return _blocked_question_run(
                self.harness,
                self,
                limits,
                f"{self.harness} run has no pinned model id",
            )
        if not self.cost_source:
            return _blocked_question_run(
                self.harness,
                self,
                limits,
                f"{self.harness} run has no verified billing source",
            )
        if (
            not _finite_positive_number(self.price_per_1k_prompt_tokens_usd)
            or not _finite_positive_number(self.price_per_1k_completion_tokens_usd)
            or not isinstance(self.max_prompt_tokens, int)
            or isinstance(self.max_prompt_tokens, bool)
            or self.max_prompt_tokens <= 0
            or not isinstance(self.max_completion_tokens, int)
            or isinstance(self.max_completion_tokens, bool)
            or self.max_completion_tokens <= 0
        ):
            return _blocked_question_run(
                self.harness,
                self,
                limits,
                f"{self.harness} run has no verified worst-case dollar bound",
            )
        return _run_harness_questions(self, tasks, limits)


def pi_question_planner(
    *,
    price_per_1k_prompt_tokens_usd: float | None = None,
    price_per_1k_completion_tokens_usd: float | None = None,
    max_prompt_tokens: int | None = None,
    max_completion_tokens: int | None = None,
    cost_source: str | None = None,
    billing_mode: Literal["usd", "plan_credits"] = "usd",
    model_id: str | None = None,
) -> HarnessQuestionPlanner:
    """Build the reusable pi print-mode planner for model-backed T2 runs."""
    return HarnessQuestionPlanner(
        harness="pi",
        argv=(
            "pi",
            "--mode",
            "json",
            "--print",
            *(("--model", model_id) if model_id else ()),
            "--no-tools",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-context-files",
            "--no-approve",
            "--offline",
            "--no-session",
        ),
        prompt_template=_QUESTION_PROMPT,
        model_id=model_id,
        price_per_1k_prompt_tokens_usd=price_per_1k_prompt_tokens_usd,
        price_per_1k_completion_tokens_usd=price_per_1k_completion_tokens_usd,
        max_prompt_tokens=max_prompt_tokens,
        max_completion_tokens=max_completion_tokens,
        cost_source=cost_source,
        billing_mode=billing_mode,
    )


def run_model_comparison(
    planner: QuestionPlanner | None = None,
    limits: ModelRunLimits | None = None,
    *,
    evidence_path: Path | None = None,
) -> ModelComparisonReport:
    """Compare a label-blind model question plan with the committed baselines."""
    fixture = load_fixture()
    _validate_fixture(fixture)
    baseline = run_benchmark()
    active_planner = planner or pi_question_planner()
    active_limits = limits or ModelRunLimits()
    question_run = active_planner.plan(_label_blind_tasks(fixture), active_limits)
    report = _comparison_report(fixture, baseline, question_run)
    if evidence_path is not None:
        _write_task_evidence(evidence_path, report)
    return report


def run_recovery_comparison(
    planner: QuestionPlanner,
    limits: ModelRunLimits,
    holdout: RecoveryHoldout,
) -> RecoveryComparisonReport:
    """Score prior and fresh tasks after one bounded, label-blind model run."""
    holdout.evidence_dir.mkdir(parents=True, exist_ok=True)
    lock_path = holdout.evidence_dir / ".budget.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        return _run_recovery_under_budget(planner, limits, holdout)
    finally:
        lock_path.unlink(missing_ok=True)


def _run_recovery_under_budget(
    planner: QuestionPlanner, limits: ModelRunLimits, holdout: RecoveryHoldout
) -> RecoveryComparisonReport:
    budget_path = holdout.evidence_dir / "budget.json"
    budget = _load_budget(budget_path, limits)
    budget["status"] = "reserved"
    _write_json(budget_path, budget)
    started = time.monotonic()
    previous_fixture = load_fixture()
    _validate_fixture(previous_fixture)
    _validate_fixture(holdout.fixture)
    previous_tasks = _label_blind_tasks(previous_fixture)
    holdout_tasks = _label_blind_tasks(holdout.fixture)
    if {task["name"] for task in previous_tasks} & {task["name"] for task in holdout_tasks}:
        raise ValueError("recovery task names must be distinct across cohorts")
    previous_baseline = run_benchmark()
    holdout_baseline = run_benchmark_for_fixture(holdout.fixture, holdout.linked_summaries)
    _write_baseline_evidence(holdout.evidence_dir / "previous-baselines.json", previous_baseline)
    _write_baseline_evidence(holdout.evidence_dir / "fresh-baselines.json", holdout_baseline)
    remaining_seconds = math.floor(
        limits.wall_seconds - budget["wall_used"] - (time.monotonic() - started)
    )
    remaining_spend = limits.spend_limit_usd - budget["spend_used"]
    if remaining_seconds <= 0 or remaining_spend <= 0:
        question_run = QuestionRun(
            status="blocked",
            harness="not-started",
            model_id=None,
            billing_mode="unknown",
            cost_source=None,
            wall_limit_seconds=limits.wall_seconds,
            spend_limit_usd=limits.spend_limit_usd,
            elapsed_seconds=time.monotonic() - started,
            usage=ModelUsage(),
            plans=[],
            blocked_reason="comparison time" if remaining_seconds <= 0 else "comparison spend",
        )
    else:
        question_run = planner.plan(
            previous_tasks + holdout_tasks,
            ModelRunLimits(wall_seconds=remaining_seconds, spend_limit_usd=remaining_spend),
        )
        question_run = replace(
            question_run,
            wall_limit_seconds=limits.wall_seconds,
            elapsed_seconds=time.monotonic() - started,
        )
    previous_plans: list[QuestionPlan] = []
    holdout_plans: list[QuestionPlan] = []
    if question_run.status == "complete":
        previous_plans = question_run.plans[: len(previous_tasks)]
        holdout_plans = question_run.plans[len(previous_tasks) :]
    previous_run = replace(
        question_run,
        plans=previous_plans,
        usage=_plan_usage(previous_plans),
    )
    holdout_run = replace(
        question_run,
        plans=holdout_plans,
        usage=_plan_usage(holdout_plans),
    )
    previous_report = _comparison_report(previous_fixture, previous_baseline, previous_run)
    holdout_report = _comparison_report(holdout.fixture, holdout_baseline, holdout_run)
    _write_task_evidence(holdout.evidence_dir / "previous-tasks.json", previous_report)
    _write_task_evidence(holdout.evidence_dir / "fresh-tasks.json", holdout_report)
    if question_run.status in {"complete", "blocked"} or question_run.blocked_reason in {
        "prompt bound",
        "time",
        "spend reserve",
        "usage bound",
        "spend",
    }:
        _settle_budget(
            budget_path,
            budget,
            replace(question_run, elapsed_seconds=time.monotonic() - started),
        )
    return RecoveryComparisonReport(
        question_run=question_run,
        previous=previous_report,
        holdout=holdout_report,
    )


def _load_budget(path: Path, limits: ModelRunLimits) -> RecoveryBudget:
    if (
        not isinstance(limits.wall_seconds, int)
        or isinstance(limits.wall_seconds, bool)
        or limits.wall_seconds <= 0
        or not _finite_positive_number(limits.spend_limit_usd)
    ):
        raise ValueError("recovery comparison requires finite positive limits")
    if not path.exists():
        return {
            "wall_limit": limits.wall_seconds,
            "spend_limit": limits.spend_limit_usd,
            "wall_used": 0.0,
            "spend_used": 0.0,
            "status": "ready",
        }
    budget = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(budget, dict)
        or budget.get("wall_limit") != limits.wall_seconds
        or budget.get("spend_limit") != limits.spend_limit_usd
        or budget.get("status") != "ready"
        or not _finite_nonnegative_number(budget.get("wall_used"))
        or not _finite_nonnegative_number(budget.get("spend_used"))
    ):
        raise ValueError(
            "recovery budget is changed, invalid, closed, or has an unresolved reservation"
        )
    return cast(RecoveryBudget, budget)


def _finite_nonnegative_number(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _settle_budget(path: Path, budget: RecoveryBudget, question_run: QuestionRun) -> None:
    spend = max(question_run.usage.spend_usd, question_run.usage.catalog_estimate_usd)
    elapsed = question_run.elapsed_seconds
    if not _finite_nonnegative_number(elapsed) or not _finite_nonnegative_number(spend):
        raise ValueError("recovery run returned invalid budget usage")
    budget["wall_used"] += elapsed
    budget["spend_used"] += spend
    budget["status"] = "closed" if question_run.status == "complete" else "ready"
    _write_json(path, budget)


def _plan_usage(plans: list[QuestionPlan]) -> ModelUsage:
    return ModelUsage(
        prompt_tokens=sum(plan.usage.prompt_tokens for plan in plans),
        completion_tokens=sum(plan.usage.completion_tokens for plan in plans),
        spend_usd=sum(plan.usage.spend_usd for plan in plans),
        catalog_estimate_usd=sum(plan.usage.catalog_estimate_usd for plan in plans),
    )


def _comparison_report(
    fixture: Fixture,
    baseline: BenchmarkReport,
    question_run: QuestionRun,
) -> ModelComparisonReport:
    candidate: StrategyReport | None = None
    if question_run.status == "complete":
        candidate = _evaluate_query_plan(fixture, _candidate_query_plan(question_run, fixture))
    return ModelComparisonReport(
        baseline=baseline,
        question_run=question_run,
        candidate=candidate,
        promotion_gate=_promotion_gate(baseline, candidate, question_run),
    )


def sanitized_task_evidence(report: ModelComparisonReport) -> list[TaskEvidenceSnapshot]:
    """Expose scored task evidence without prompts, questions, or memory text."""
    if report.candidate is None:
        return []
    usage_by_task = {plan.task: plan.usage for plan in report.question_run.plans}
    rows: list[TaskEvidenceSnapshot] = []
    for task in report.candidate.tasks:
        usage = usage_by_task[task.name]
        rows.append(
            {
                "task": task.name,
                "complete": task.complete,
                "hits": task.hits,
                "missing": task.missing,
                "calls": task.cost.calls,
                "rendered_tokens": task.cost.rendered_tokens,
                "latency_ms": task.cost.latency_ms,
                "inactive_hits": len(task.inactive_hits),
                "other_project_hits": len(task.other_project_hits),
                "model_prompt_tokens": usage.prompt_tokens,
                "model_completion_tokens": usage.completion_tokens,
                "model_catalog_estimate_usd": usage.catalog_estimate_usd,
            }
        )
    return rows


def _write_baseline_evidence(path: Path, baseline: BenchmarkReport) -> None:
    strategies: dict[str, list[BaselineTaskEvidenceSnapshot]] = {}
    for name, report in baseline.strategies.items():
        strategies[name] = [
            {
                "task": task.name,
                "complete": task.complete,
                "hits": task.hits,
                "missing": task.missing,
                "calls": task.cost.calls,
                "rendered_tokens": task.cost.rendered_tokens,
                "latency_ms": task.cost.latency_ms,
                "inactive_hits": len(task.inactive_hits),
                "other_project_hits": len(task.other_project_hits),
            }
            for task in report.tasks
        ]
    _write_json(path, {"source_revision": baseline.source_revision, "strategies": strategies})


def _write_task_evidence(path: Path, report: ModelComparisonReport) -> None:
    """Replace a previous task trace, including when the new run is blocked."""
    export = {
        "source_revision": report.baseline.source_revision,
        "status": report.question_run.status,
        "model_id": report.question_run.model_id,
        "blocked_reason": report.question_run.blocked_reason,
        "tasks": sanitized_task_evidence(report),
    }
    _write_json(path, export)


def _write_json(path: Path, value: object) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(value, temporary, indent=2)
            temporary.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _label_blind_tasks(fixture: Fixture) -> list[TaskQuestionInput]:
    return [{"name": task["name"], "goal": task["goal"]} for task in fixture["tasks"]]


def _evaluate_query_plan(
    fixture: Fixture,
    query_plan: dict[str, list[str]],
) -> StrategyReport:
    with tempfile.TemporaryDirectory(prefix="memex-agent-workflow-candidate-") as directory:
        memex = Memex(MemexConfig(data_dir=Path(directory)))
        try:
            active, inactive, other_project = _populate(memex, fixture)
            required = {slug for task in fixture["tasks"] for slug in task["required"]}
            if not required <= active:
                raise ValueError(
                    f"task labels name missing active memories: {sorted(required - active)}"
                )
            return _strategy_report(
                fixture["tasks"],
                [
                    _focused_result(
                        memex,
                        task,
                        query_plan[task["name"]],
                        fixture["project_id"],
                        inactive,
                        other_project,
                    )
                    for task in fixture["tasks"]
                ],
            )
        finally:
            memex.close()


def _candidate_query_plan(question_run: QuestionRun, fixture: Fixture) -> dict[str, list[str]]:
    task_names = [task["name"] for task in fixture["tasks"]]
    plan_names = [plan.task for plan in question_run.plans]
    if plan_names != task_names:
        raise ValueError("candidate questions must appear once per task in fixture task order")
    query_plan: dict[str, list[str]] = {}
    for plan in question_run.plans:
        if not plan.queries or len(plan.queries) > 3:
            raise ValueError(f"candidate query count must be 1..3 for {plan.task}")
        query_plan[plan.task] = plan.queries
    return query_plan


def _promotion_gate(
    baseline: BenchmarkReport,
    candidate: StrategyReport | None,
    question_run: QuestionRun,
) -> PromotionGate:
    broad_strategy = baseline.strategies["broad_query"]
    linked_strategy = baseline.strategies["linked_summary"]
    broad = broad_strategy.task_complete
    linked = linked_strategy.task_complete
    if candidate is None:
        return PromotionGate(
            passed=False,
            promoted=False,
            recall_gate_passed=False,
            eligible_for_further_validation=False,
            candidate_task_complete=None,
            broad_query_task_complete=broad,
            linked_summary_task_complete=linked,
            required_margin_points=PROMOTION_MARGIN_POINTS,
            failed_conditions=["model-run-incomplete"],
            verdict=f"unpromoted: {question_run.blocked_reason or 'model run incomplete'}",
        )
    task_count = baseline.task_count
    required_margin_tasks = (PROMOTION_MARGIN_POINTS / 100) * task_count
    failed_conditions: list[str] = []
    if candidate.task_complete - broad < required_margin_tasks:
        failed_conditions.append("broad-query-margin")
    if candidate.task_complete - linked < required_margin_tasks:
        failed_conditions.append("linked-summary-margin")
    if candidate.inactive_hits != 0:
        failed_conditions.append("inactive-hits")
    if candidate.other_project_hits != 0:
        failed_conditions.append("other-project-hits")
    if _strategy_p95_latency(candidate) > _strategy_p95_latency(broad_strategy) * 3:
        failed_conditions.append("p95-latency-bound")
    if question_run.usage.prompt_tokens + question_run.usage.completion_tokens:
        failed_conditions.append("model-token-baseline-unavailable")
    failed_conditions.append("completed-code-check-not-run")
    failed_conditions.append("poison-memory-trace-not-run")
    recall_gate_passed = not failed_conditions[:-2]
    return PromotionGate(
        passed=False,
        promoted=False,
        recall_gate_passed=recall_gate_passed,
        eligible_for_further_validation=recall_gate_passed,
        candidate_task_complete=candidate.task_complete,
        broad_query_task_complete=broad,
        linked_summary_task_complete=linked,
        required_margin_points=PROMOTION_MARGIN_POINTS,
        failed_conditions=failed_conditions,
        verdict="unpromoted: recall-only result cannot change guidance",
    )


def _strategy_p95_latency(strategy: StrategyReport) -> float:
    latencies = sorted(task.cost.latency_ms for task in strategy.tasks)
    if not latencies:
        return 0.0
    index = max(0, math.ceil(len(latencies) * 0.95) - 1)
    return latencies[index]


def _blocked_question_run(
    harness: str,
    planner: HarnessQuestionPlanner,
    limits: ModelRunLimits,
    reason: str,
) -> QuestionRun:
    return QuestionRun(
        status="blocked",
        harness=harness,
        model_id=planner.model_id,
        billing_mode=planner.billing_mode,
        cost_source=planner.cost_source,
        wall_limit_seconds=limits.wall_seconds,
        spend_limit_usd=limits.spend_limit_usd,
        elapsed_seconds=0.0,
        usage=ModelUsage(),
        plans=[],
        blocked_reason=reason,
    )


def _run_harness_questions(
    planner: HarnessQuestionPlanner,
    tasks: list[TaskQuestionInput],
    limits: ModelRunLimits,
) -> QuestionRun:
    plans: list[QuestionPlan] = []
    usage = ModelUsage()
    started = time.monotonic()
    for task in tasks:
        prompt = planner.prompt_template.format(name=task["name"], goal=task["goal"])
        if estimate_tokens(prompt) > (planner.max_prompt_tokens or 0):
            return _incomplete_question_run(
                planner.harness, planner, limits, started, usage, plans, "prompt bound"
            )
        task_usage = ModelUsage()
        for attempt in range(2):
            remaining = limits.wall_seconds - (time.monotonic() - started)
            reserve = _worst_case_call_spend(planner)
            catalog_reserve = _worst_case_catalog_estimate(planner)
            if remaining <= 0:
                reason = "time"
                break
            if (
                usage.spend_usd + reserve > limits.spend_limit_usd
                or usage.catalog_estimate_usd + catalog_reserve > limits.spend_limit_usd
            ):
                reason = "spend reserve"
                break
            try:
                completed = _run_command(
                    [*planner.argv, prompt],
                    capture_output=True,
                    text=True,
                    timeout=remaining,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                reason = f"harness error: {type(exc).__name__}"
                break
            if completed.returncode != 0:
                reason = f"harness exit {completed.returncode}"
                break
            try:
                parsed = _parse_harness_json(completed.stdout)
            except (json.JSONDecodeError, ValueError):
                reason = "harness output"
                break
            latest_usage = parsed["usage"]
            if not _has_billable_usage(latest_usage):
                reason = "missing usage"
                break
            usage_record = cast(ModelUsage, latest_usage)
            usage = _add_usage(usage, usage_record, planner)
            task_usage = _add_usage(task_usage, usage_record, planner)
            if usage_record.prompt_tokens > (
                planner.max_prompt_tokens or 0
            ) or usage_record.completion_tokens > (planner.max_completion_tokens or 0):
                reason = "usage bound"
                break
            if (
                usage.spend_usd > limits.spend_limit_usd
                or usage.catalog_estimate_usd > limits.spend_limit_usd
            ):
                reason = "spend"
                break
            queries = cast(list[str], parsed["queries"])
            if queries:
                plans.append(
                    QuestionPlan(
                        task=task["name"],
                        queries=queries,
                        usage=task_usage,
                    )
                )
                break
            reason = "harness output"
            if attempt == 1:
                break
        if not plans or plans[-1].task != task["name"]:
            return _incomplete_question_run(
                planner.harness, planner, limits, started, usage, plans, reason
            )
    return QuestionRun(
        status="complete",
        harness=planner.harness,
        model_id=planner.model_id,
        billing_mode=planner.billing_mode,
        cost_source=planner.cost_source,
        wall_limit_seconds=limits.wall_seconds,
        spend_limit_usd=limits.spend_limit_usd,
        elapsed_seconds=time.monotonic() - started,
        usage=usage,
        plans=plans,
    )


def _incomplete_question_run(
    harness: str,
    planner: HarnessQuestionPlanner,
    limits: ModelRunLimits,
    started: float,
    usage: ModelUsage,
    plans: list[QuestionPlan],
    reason: str,
) -> QuestionRun:
    return QuestionRun(
        status="incomplete",
        harness=harness,
        model_id=planner.model_id,
        billing_mode=planner.billing_mode,
        cost_source=planner.cost_source,
        wall_limit_seconds=limits.wall_seconds,
        spend_limit_usd=limits.spend_limit_usd,
        elapsed_seconds=time.monotonic() - started,
        usage=usage,
        plans=plans,
        blocked_reason=reason,
    )


def _parse_harness_json(output: str) -> dict[str, object]:
    """Read pi-style JSON events and return queries plus token usage."""
    queries: list[str] = []
    usage = ModelUsage()
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            continue
        queries = _queries_from_event(event) or queries
        usage = _usage_from_event(event) or usage
    return {"queries": queries, "usage": usage}


def _queries_from_event(event: dict[str, object]) -> list[str] | None:
    raw: object = event.get("queries")
    if raw is None:
        text = _assistant_text_from_event(event)
        if text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return None
            if isinstance(parsed, dict):
                raw = parsed.get("queries")
    if not isinstance(raw, list):
        return None
    queries = [query.strip() for query in raw if isinstance(query, str) and query.strip()]
    if not queries or len(queries) > 3:
        return None
    return queries


def _usage_from_event(event: dict[str, object]) -> ModelUsage | None:
    raw = event.get("usage")
    if raw is None and isinstance(event.get("message"), dict):
        raw = cast(dict[str, object], event["message"]).get("usage")
    if not isinstance(raw, dict):
        return None
    token_usage = cast(dict[str, object], raw)
    prompt = _usage_int(token_usage, ("prompt_tokens", "input_tokens", "input"))
    if (
        "input" in token_usage
        and "prompt_tokens" not in token_usage
        and "input_tokens" not in token_usage
    ):
        cache_read = _usage_int(token_usage, ("cacheRead",))
        cache_write = _usage_int(token_usage, ("cacheWrite",))
        if min(prompt, cache_read, cache_write) < 0:
            prompt = -1
        else:
            prompt += cache_read + cache_write
    completion = _usage_int(token_usage, ("completion_tokens", "output_tokens", "output"))
    spend = _usage_cost(token_usage)
    return ModelUsage(prompt_tokens=prompt, completion_tokens=completion, spend_usd=spend)


def _usage_int(usage: dict[str, object], names: tuple[str, ...]) -> int:
    for name in names:
        if name in usage:
            value = usage[name]
            return value if isinstance(value, int) and not isinstance(value, bool) else -1
    return 0


def _add_usage(
    current: ModelUsage,
    latest: object,
    planner: HarnessQuestionPlanner,
) -> ModelUsage:
    if not isinstance(latest, ModelUsage):
        return current
    prompt_tokens = current.prompt_tokens + latest.prompt_tokens
    completion_tokens = current.completion_tokens + latest.completion_tokens
    observed_cost = max(latest.spend_usd, _estimated_spend(latest, planner))
    if planner.billing_mode == "plan_credits":
        spend = current.spend_usd
        catalog_estimate = current.catalog_estimate_usd + observed_cost
    else:
        spend = current.spend_usd + observed_cost
        catalog_estimate = current.catalog_estimate_usd
    return ModelUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        spend_usd=spend,
        catalog_estimate_usd=catalog_estimate,
    )


def _assistant_text_from_event(event: dict[str, object]) -> str | None:
    message = event.get("message")
    if event.get("type") != "message_end" or not isinstance(message, dict):
        return None
    if message.get("role") != "assistant":
        return None
    content = message.get("content")
    if not isinstance(content, list):
        return None
    parts = [
        block["text"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    return "\n".join(parts).strip() or None


def _usage_cost(usage: dict[str, object]) -> float:
    cost = usage.get("cost")
    if isinstance(cost, dict):
        total = cost.get("total")
        if isinstance(total, int | float) and not isinstance(total, bool):
            return float(total)
        if "total" in cost:
            return float("nan")
    return 0.0


def _has_billable_usage(value: object) -> bool:
    if not isinstance(value, ModelUsage):
        return False
    if (
        value.prompt_tokens < 0
        or value.completion_tokens < 0
        or not math.isfinite(value.spend_usd)
        or value.spend_usd < 0
    ):
        return False
    return bool(value.spend_usd or value.prompt_tokens or value.completion_tokens)


def _estimated_spend(usage: ModelUsage, planner: HarnessQuestionPlanner) -> float:
    prompt_rate = planner.price_per_1k_prompt_tokens_usd or 0.0
    completion_rate = planner.price_per_1k_completion_tokens_usd or 0.0
    return (usage.prompt_tokens / 1000 * prompt_rate) + (
        usage.completion_tokens / 1000 * completion_rate
    )


def _worst_case_call_spend(planner: HarnessQuestionPlanner) -> float:
    if planner.billing_mode == "plan_credits":
        return 0.0
    return _worst_case_catalog_estimate(planner)


def _worst_case_catalog_estimate(planner: HarnessQuestionPlanner) -> float:
    usage = ModelUsage(
        prompt_tokens=planner.max_prompt_tokens or 0,
        completion_tokens=planner.max_completion_tokens or 0,
    )
    return _estimated_spend(usage, planner)
