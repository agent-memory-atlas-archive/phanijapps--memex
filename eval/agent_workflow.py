"""Measure task-level recall from a sourced coding-agent memory fixture.

Run with ``uv run python -m eval.agent_workflow``. The store is temporary.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NotRequired, TypedDict, cast

from memex.application.memory import Memex
from memex.domain.models import WriteInput
from memex.infrastructure.config import MemexConfig

FIXTURE = Path(__file__).resolve().parent / "data" / "coding-agent-workflow.json"
MAX_TASK_HITS = 8
FOCUSED_HITS_PER_QUERY = 3


class MemorySpec(TypedDict):
    title: str
    type: str
    body: str
    source: str
    evidence: NotRequired[str]
    scope: str
    archive: NotRequired[bool]


class TaskSpec(TypedDict):
    name: str
    goal: str
    focused_queries: list[str]
    required: list[str]


class Fixture(TypedDict):
    source_revision: str
    source_hashes: dict[str, str]
    project_id: str
    other_project_id: str
    memories: list[MemorySpec]
    tasks: list[TaskSpec]


@dataclass(frozen=True, slots=True)
class TaskResult:
    name: str
    required: list[str]
    one_shot_hits: list[str]
    focused_hits: list[str]
    one_shot_missing: list[str]
    focused_missing: list[str]

    @property
    def one_shot_complete(self) -> bool:
        return not self.one_shot_missing

    @property
    def focused_complete(self) -> bool:
        return not self.focused_missing


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    source_revision: str
    memory_count: int
    active_memory_count: int
    excluded_memory_count: int
    task_count: int
    one_shot_complete: int
    focused_complete: int
    one_shot_evidence_recall: float
    focused_evidence_recall: float
    tasks: list[TaskResult]


def load_fixture() -> Fixture:
    """Load the committed, manually labeled workflow fixture."""
    return cast(Fixture, json.loads(FIXTURE.read_text(encoding="utf-8")))


def _populate(memex: Memex, fixture: Fixture) -> tuple[set[str], set[str]]:
    active: set[str] = set()
    excluded: set[str] = set()
    for memory in fixture["memories"]:
        is_other = memory["scope"] == "other_project"
        project_id = fixture["other_project_id"] if is_other else fixture["project_id"]
        node = memex.write(
            WriteInput(
                type=memory["type"],
                title=memory["title"],
                body=memory["body"],
                scope="project",
                project_id=project_id,
            )
        )
        if memory.get("archive", False):
            memex.forget(node.slug, mode="archive")
        if is_other or memory.get("archive", False):
            excluded.add(node.slug)
        else:
            active.add(node.slug)
    return active, excluded


def _recall(memex: Memex, query: str, project_id: str, top_k: int) -> list[str]:
    result = memex.recall(query, top_k=top_k, scope="project", project_id=project_id)
    if any(hit.scope != "project" or hit.project_id != project_id for hit in result.hits):
        raise AssertionError("project recall leaked another namespace")
    return [hit.slug for hit in result.hits]


def _focused_hits(memex: Memex, task: TaskSpec, project_id: str) -> list[str]:
    hits: list[str] = []
    for query in task["focused_queries"]:
        for slug in _recall(memex, query, project_id, FOCUSED_HITS_PER_QUERY):
            if slug not in hits:
                hits.append(slug)
    return hits[:MAX_TASK_HITS]


def _evaluate_task(memex: Memex, task: TaskSpec, project_id: str) -> TaskResult:
    one_shot = _recall(memex, task["goal"], project_id, MAX_TASK_HITS)
    focused = _focused_hits(memex, task, project_id)
    return TaskResult(
        name=task["name"],
        required=task["required"],
        one_shot_hits=one_shot,
        focused_hits=focused,
        one_shot_missing=[slug for slug in task["required"] if slug not in one_shot],
        focused_missing=[slug for slug in task["required"] if slug not in focused],
    )


def run_benchmark() -> BenchmarkReport:
    """Recall task evidence from a fresh isolated store and report all misses."""
    fixture = load_fixture()
    with tempfile.TemporaryDirectory(prefix="memex-agent-workflow-") as directory:
        memex = Memex(MemexConfig(data_dir=Path(directory)))
        try:
            active, excluded = _populate(memex, fixture)
            tasks = [
                _evaluate_task(memex, task, fixture["project_id"]) for task in fixture["tasks"]
            ]
        finally:
            memex.close()
    required = {slug for task in fixture["tasks"] for slug in task["required"]}
    if not required <= active:
        raise ValueError(f"task labels name missing active memories: {sorted(required - active)}")
    if any(set(task.one_shot_hits + task.focused_hits) & excluded for task in tasks):
        raise AssertionError("inactive or other-project memory appeared in project recall")
    return BenchmarkReport(
        source_revision=fixture["source_revision"],
        memory_count=len(fixture["memories"]),
        active_memory_count=len(active),
        excluded_memory_count=len(excluded),
        task_count=len(tasks),
        one_shot_complete=sum(task.one_shot_complete for task in tasks),
        focused_complete=sum(task.focused_complete for task in tasks),
        one_shot_evidence_recall=sum(
            len(task.required) - len(task.one_shot_missing) for task in tasks
        )
        / sum(len(task.required) for task in tasks),
        focused_evidence_recall=sum(
            len(task.required) - len(task.focused_missing) for task in tasks
        )
        / sum(len(task.required) for task in tasks),
        tasks=tasks,
    )


if __name__ == "__main__":
    print(json.dumps(asdict(run_benchmark()), indent=2))
