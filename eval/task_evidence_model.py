"""Model-backed task-evidence comparison for the held-out workflow fixture."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TypedDict, cast

from eval.agent_workflow import (
    BenchmarkReport,
    Fixture,
    StrategyReport,
    _focused_result,
    _populate,
    _strategy_report,
    _validate_fixture,
    load_fixture,
    run_benchmark,
)
from memex.application.context_injection import estimate_tokens
from memex.application.memory import Memex
from memex.infrastructure.config import MemexConfig

MODEL_WALL_LIMIT_SECONDS = 300
MODEL_SPEND_LIMIT_USD = 5.0
PROMOTION_MARGIN_POINTS = 10.0
_run_command = subprocess.run

_QUESTION_PROMPT = """\
You are choosing memory-recall questions before a coding task.
Return JSON only, with this shape: {{"queries": ["...", "..."]}}.
Use one to three focused questions. Do not include explanations.

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
) -> ModelComparisonReport:
    """Compare a label-blind model question plan with the committed baselines."""
    fixture = load_fixture()
    _validate_fixture(fixture)
    baseline = run_benchmark()
    active_planner = planner or pi_question_planner()
    active_limits = limits or ModelRunLimits()
    question_run = active_planner.plan(_label_blind_tasks(fixture), active_limits)
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
