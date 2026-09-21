"""Measure task-level recall from a sourced coding-agent memory fixture.

Run with ``uv run python -m eval.agent_workflow``. The store is temporary.
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NotRequired, TypedDict, cast

from memex.application.context_injection import (
    DEFAULT_INJECTION_TOP_K,
    build_injection,
    estimate_tokens,
)
from memex.application.memory import Memex
from memex.domain.models import RecallHit, WriteInput
from memex.infrastructure.config import MemexConfig

DATA_DIR = Path(__file__).resolve().parent / "data"
FIXTURE = DATA_DIR / "coding-agent-workflow.json"
LINKED_SUMMARIES = DATA_DIR / "task-linked-summaries.json"
HUMAN_FOCUSED_QUERIES = DATA_DIR / "human-focused-queries.json"
MAX_TASK_HITS = 36  # mirrors the product task-recall page cap
FOCUSED_HITS_PER_QUERY = 12  # mirrors the product per-question retrieval depth
SUMMARY_LINK = re.compile(r"memex://([a-z0-9][a-z0-9-]+)|\[\[([a-z0-9][a-z0-9-]+)\]\]")
RENDERED_FILE_SLUG = re.compile(
    r"^[ \t]*File: [^\r\n]*/([a-z0-9][a-z0-9-]+)\.md[ \t]*$",
    re.MULTILINE,
)


def _summary_links(body: str) -> list[str]:
    matches = list(SUMMARY_LINK.finditer(body))
    wiki_spans = [match.span() for match in matches if match.group(0).startswith("[[")]
    for start in (match.start() for match in re.finditer(r"\[\[", body)):
        if not any(span_start <= start < span_end for span_start, span_end in wiki_spans):
            raise ValueError("summary contains a malformed wiki link")
    return [match.group(1) or match.group(2) for match in matches]


class MemorySpec(TypedDict):
    title: str
    type: str
    body: str
    source: str
    scope: str
    archive: NotRequired[bool]


class TaskSpec(TypedDict):
    name: str
    goal: str
    required: list[str]


class Fixture(TypedDict):
    source_revision: str
    source_hashes: dict[str, str]
    project_id: str
    other_project_id: str
    memories: list[MemorySpec]
    tasks: list[TaskSpec]


class LinkedSummarySpec(TypedDict):
    task: str
    body: str


class LinkedSummaryFixture(TypedDict):
    summaries: list[LinkedSummarySpec]


class HumanFocusedQuerySpec(TypedDict):
    name: str
    queries: list[str]


class HumanFocusedQueryFixture(TypedDict):
    tasks: list[HumanFocusedQuerySpec]


@dataclass(frozen=True, slots=True)
class RecallCost:
    calls: int
    rendered_tokens: int
    latency_ms: float


@dataclass(frozen=True, slots=True)
class TaskStrategyResult:
    name: str
    hits: list[str]
    missing: list[str]
    cost: RecallCost
    inactive_hits: list[str]
    other_project_hits: list[str]

    @property
    def complete(self) -> bool:
        return not self.missing


@dataclass(frozen=True, slots=True)
class StrategyReport:
    task_complete: int
    fact_recall: float
    calls: int
    rendered_tokens: int
    latency_ms: float
    inactive_hits: int
    other_project_hits: int
    tasks: list[TaskStrategyResult]


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    source_revision: str
    memory_count: int
    active_memory_count: int
    excluded_memory_count: int
    task_count: int
    linked_summary_count: int
    strategies: dict[str, StrategyReport]


def load_fixture() -> Fixture:
    """Load the committed, manually labeled workflow fixture."""
    return cast(Fixture, json.loads(FIXTURE.read_text(encoding="utf-8")))


def load_linked_summaries(path: Path = LINKED_SUMMARIES) -> LinkedSummaryFixture:
    """Load the independently authored linked-summary baseline fixture."""
    if not path.exists():
        return {"summaries": []}
    return cast(LinkedSummaryFixture, json.loads(path.read_text(encoding="utf-8")))


def load_human_focused_queries(path: Path = HUMAN_FOCUSED_QUERIES) -> HumanFocusedQueryFixture:
    """Load the independently authored human-focused query fixture."""
    return cast(HumanFocusedQueryFixture, json.loads(path.read_text(encoding="utf-8")))


def _validate_fixture(fixture: Fixture) -> None:
    task_names = [task["name"] for task in fixture["tasks"]]
    if len(task_names) != len(set(task_names)):
        raise ValueError("task names must be unique")


def _populate(memex: Memex, fixture: Fixture) -> tuple[set[str], set[str], set[str]]:
    active: set[str] = set()
    inactive: set[str] = set()
    other_project: set[str] = set()
    for memory in fixture["memories"]:
        is_other = memory["scope"] == "other_project"
        project_id = fixture["other_project_id"] if is_other else fixture["project_id"]
        node = memex.write(
            WriteInput(
                type=memory["type"],
                title=memory["title"],
                body=memory["body"],
                description=str(memory.get("description", "")),
                scope="project",
                project_id=project_id,
            )
        )
        if memory.get("archive", False):
            memex.forget(node.slug, mode="archive")
            inactive.add(node.slug)
        elif is_other:
            other_project.add(node.slug)
        else:
            active.add(node.slug)
    return active, inactive, other_project


def _populate_linked_summaries(
    memex: Memex,
    fixture: Fixture,
    linked_summaries: LinkedSummaryFixture,
    active: set[str],
) -> dict[str, str]:
    summary_bodies: dict[str, str] = {}
    task_names = [task["name"] for task in fixture["tasks"]]
    summary_task_names = [summary["task"] for summary in linked_summaries["summaries"]]
    if summary_task_names != task_names:
        raise ValueError("linked summaries must appear once per task in fixture task order")
    for summary in linked_summaries["summaries"]:
        linked_slugs = set(_summary_links(summary["body"]))
        unknown_links = linked_slugs - active
        if unknown_links:
            raise ValueError(
                f"linked summary for {summary['task']} names unknown links: {sorted(unknown_links)}"
            )
        node = memex.write(
            WriteInput(
                type="summary",
                title=f"Linked task summary: {summary['task']}",
                body=summary["body"],
                scope="project",
                project_id=fixture["project_id"],
            )
        )
        summary_bodies[node.slug] = summary["body"]
    return summary_bodies


def _human_query_plan(
    fixture: Fixture,
    human_queries: HumanFocusedQueryFixture,
) -> dict[str, list[str]]:
    task_names = [task["name"] for task in fixture["tasks"]]
    query_task_names = [task["name"] for task in human_queries["tasks"]]
    if query_task_names != task_names:
        raise ValueError("human-focused queries must appear once per task in fixture task order")
    plan: dict[str, list[str]] = {}
    for task in human_queries["tasks"]:
        queries = task["queries"]
        if not queries or len(queries) > 3:
            raise ValueError(f"human-focused query count must be 1..3 for {task['name']}")
        plan[task["name"]] = queries
    return plan


def _rendered_tokens(hits: list[RecallHit]) -> int:
    rendered = "\n".join(
        f"{hit.rank}. {hit.title}\nFile: {hit.file_path}\n{hit.snippet}" for hit in hits
    )
    return estimate_tokens(rendered) if rendered else 0


def _summary_rendered_tokens(hits: list[RecallHit], summary_bodies: dict[str, str]) -> int:
    rendered = "\n".join(
        f"{hit.rank}. {hit.title}\nFile: {hit.file_path}\n{summary_bodies[hit.slug]}"
        for hit in hits
    )
    return estimate_tokens(rendered) if rendered else 0


def _recall(
    memex: Memex,
    query: str,
    project_id: str,
    top_k: int,
    *,
    node_type: str | None = None,
) -> tuple[list[RecallHit], float]:
    started = time.perf_counter()
    result = memex.recall(
        query,
        top_k=top_k,
        node_type=node_type,
        scope="project",
        project_id=project_id,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    if any(hit.scope != "project" or hit.project_id != project_id for hit in result.hits):
        raise AssertionError("project recall leaked another namespace")
    return result.hits, latency_ms


def _distinct_slugs(hits: list[RecallHit]) -> list[str]:
    slugs: list[str] = []
    for hit in hits:
        if hit.slug not in slugs:
            slugs.append(hit.slug)
    return slugs[:MAX_TASK_HITS]


def _leaked_hits(
    hits: list[str],
    inactive: set[str],
    other_project: set[str],
) -> tuple[list[str], list[str]]:
    inactive_hits = [slug for slug in hits if slug in inactive]
    other_project_hits = [slug for slug in hits if slug in other_project]
    return inactive_hits, other_project_hits


def _task_result(
    task: TaskSpec,
    hits: list[str],
    cost: RecallCost,
    inactive: set[str],
    other_project: set[str],
) -> TaskStrategyResult:
    inactive_hits, other_project_hits = _leaked_hits(hits, inactive, other_project)
    return TaskStrategyResult(
        name=task["name"],
        hits=hits,
        missing=[slug for slug in task["required"] if slug not in hits],
        cost=cost,
        inactive_hits=inactive_hits,
        other_project_hits=other_project_hits,
    )


def _current_injection_result(
    memex: Memex,
    task: TaskSpec,
    project_id: str,
    inactive: set[str],
    other_project: set[str],
) -> TaskStrategyResult:
    del project_id
    started = time.perf_counter()
    block = build_injection(memex, task["goal"], top_k=DEFAULT_INJECTION_TOP_K)
    latency_ms = (time.perf_counter() - started) * 1000
    hits = RENDERED_FILE_SLUG.findall(block)
    return _task_result(
        task,
        hits[:MAX_TASK_HITS],
        RecallCost(
            calls=1,
            rendered_tokens=estimate_tokens(block) if block else 0,
            latency_ms=latency_ms,
        ),
        inactive,
        other_project,
    )


def _broad_query_result(
    memex: Memex,
    task: TaskSpec,
    project_id: str,
    inactive: set[str],
    other_project: set[str],
) -> TaskStrategyResult:
    hits, latency_ms = _recall(memex, task["goal"], project_id, MAX_TASK_HITS)
    return _task_result(
        task,
        _distinct_slugs(hits),
        RecallCost(calls=1, rendered_tokens=_rendered_tokens(hits), latency_ms=latency_ms),
        inactive,
        other_project,
    )


def _focused_result(
    memex: Memex,
    task: TaskSpec,
    focused_queries: list[str],
    project_id: str,
    inactive: set[str],
    other_project: set[str],
) -> TaskStrategyResult:
    hits: list[RecallHit] = []
    latency_ms = 0.0
    for query in focused_queries:
        query_hits, query_latency_ms = _recall(memex, query, project_id, FOCUSED_HITS_PER_QUERY)
        latency_ms += query_latency_ms
        known = {hit.slug for hit in hits}
        hits.extend(hit for hit in query_hits if hit.slug not in known)
    hits = hits[:MAX_TASK_HITS]
    return _task_result(
        task,
        _distinct_slugs(hits),
        RecallCost(
            calls=len(focused_queries),
            rendered_tokens=_rendered_tokens(hits),
            latency_ms=latency_ms,
        ),
        inactive,
        other_project,
    )


def _linked_summary_result(
    memex: Memex,
    task: TaskSpec,
    project_id: str,
    summary_bodies: dict[str, str],
    inactive: set[str],
    other_project: set[str],
) -> TaskStrategyResult:
    hits, latency_ms = _recall(
        memex,
        task["goal"],
        project_id,
        1,
        node_type="summary",
    )
    summary_hits = [hit for hit in hits if hit.slug in summary_bodies][:1]
    linked_slugs: list[str] = []
    for hit in summary_hits:
        for slug in _summary_links(summary_bodies[hit.slug]):
            if slug not in linked_slugs:
                linked_slugs.append(slug)
    return _task_result(
        task,
        linked_slugs[:MAX_TASK_HITS],
        RecallCost(
            calls=1,
            rendered_tokens=_summary_rendered_tokens(summary_hits, summary_bodies),
            latency_ms=latency_ms,
        ),
        inactive,
        other_project,
    )


def _strategy_report(tasks: list[TaskSpec], results: list[TaskStrategyResult]) -> StrategyReport:
    too_large = [result.name for result in results if result.cost.rendered_tokens > 4096]
    if too_large:
        raise ValueError(f"task rendered context exceeds 4096 tokens: {too_large}")
    required_count = sum(len(task["required"]) for task in tasks)
    found_count = sum(
        len(task["required"]) - len(result.missing)
        for task, result in zip(tasks, results, strict=True)
    )
    return StrategyReport(
        task_complete=sum(result.complete for result in results),
        fact_recall=found_count / required_count,
        calls=sum(result.cost.calls for result in results),
        rendered_tokens=sum(result.cost.rendered_tokens for result in results),
        latency_ms=sum(result.cost.latency_ms for result in results),
        inactive_hits=sum(len(result.inactive_hits) for result in results),
        other_project_hits=sum(len(result.other_project_hits) for result in results),
        tasks=results,
    )


def _evaluate_strategies(
    memex: Memex,
    fixture: Fixture,
    query_plan: dict[str, list[str]] | None,
    inactive: set[str],
    other_project: set[str],
) -> dict[str, StrategyReport]:
    tasks = fixture["tasks"]
    project_id = fixture["project_id"]
    strategies = {
        "current_injection": _strategy_report(
            tasks,
            [
                _current_injection_result(memex, task, project_id, inactive, other_project)
                for task in tasks
            ],
        ),
        "broad_query": _strategy_report(
            tasks,
            [
                _broad_query_result(memex, task, project_id, inactive, other_project)
                for task in tasks
            ],
        ),
    }
    if query_plan is not None:
        strategies["human_focused"] = _strategy_report(
            tasks,
            [
                _focused_result(
                    memex,
                    task,
                    query_plan[task["name"]],
                    project_id,
                    inactive,
                    other_project,
                )
                for task in tasks
            ],
        )
    return strategies


def run_benchmark() -> BenchmarkReport:
    """Recall task evidence from a fresh isolated store and report all misses."""
    return run_benchmark_for_fixture(
        load_fixture(), load_linked_summaries(), load_human_focused_queries()
    )


def run_benchmark_for_fixture(
    fixture: Fixture,
    linked_summaries: LinkedSummaryFixture,
    human_queries: HumanFocusedQueryFixture | None = None,
) -> BenchmarkReport:
    """Measure a supplied workflow corpus in a fresh isolated store."""
    _validate_fixture(fixture)
    query_plan = _human_query_plan(fixture, human_queries) if human_queries is not None else None
    with tempfile.TemporaryDirectory(prefix="memex-agent-workflow-") as directory:
        memex = Memex(MemexConfig(data_dir=Path(directory)))
        try:
            active, inactive, other_project = _populate(memex, fixture)
            strategies = _evaluate_strategies(
                memex,
                fixture,
                query_plan,
                inactive,
                other_project,
            )
            summary_bodies = _populate_linked_summaries(
                memex,
                fixture,
                linked_summaries,
                active,
            )
            strategies["linked_summary"] = _strategy_report(
                fixture["tasks"],
                [
                    _linked_summary_result(
                        memex,
                        task,
                        fixture["project_id"],
                        summary_bodies,
                        inactive,
                        other_project,
                    )
                    for task in fixture["tasks"]
                ],
            )
        finally:
            memex.close()
    required = {slug for task in fixture["tasks"] for slug in task["required"]}
    if not required <= active:
        raise ValueError(f"task labels name missing active memories: {sorted(required - active)}")
    return BenchmarkReport(
        source_revision=fixture["source_revision"],
        memory_count=len(fixture["memories"]),
        active_memory_count=len(active),
        excluded_memory_count=len(inactive | other_project),
        task_count=len(fixture["tasks"]),
        linked_summary_count=len(linked_summaries["summaries"]),
        strategies=strategies,
    )


if __name__ == "__main__":
    print(json.dumps(asdict(run_benchmark()), indent=2))
