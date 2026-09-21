"""Frozen holdout exercises the real local recall path without a model."""

import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import cast

from eval.agent_workflow import (
    BenchmarkReport,
    Fixture,
    HumanFocusedQueryFixture,
    LinkedSummaryFixture,
    _summary_links,
    run_benchmark_for_fixture,
)
from eval.task_evidence_model import _label_blind_tasks
from memex.domain.slugs import slugify

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "eval/data/task-evidence-holdout-v2.json"
SUMMARIES_PATH = ROOT / "eval/data/task-evidence-holdout-v2-summaries.json"


def _load_holdout() -> tuple[Fixture, LinkedSummaryFixture]:
    fixture = cast(Fixture, json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))
    summaries = cast(LinkedSummaryFixture, json.loads(SUMMARIES_PATH.read_text(encoding="utf-8")))
    return fixture, summaries


def _stable_report(report: BenchmarkReport) -> dict[str, object]:
    result = asdict(report)
    for strategy in result["strategies"].values():
        strategy.pop("latency_ms")
        for task in strategy["tasks"]:
            task["cost"].pop("latency_ms")
    return cast(dict[str, object], result)


def test_holdout_sources_and_links_are_pinned() -> None:
    fixture, summaries = _load_holdout()
    assert len(fixture["tasks"]) == len(summaries["summaries"]) == 8
    assert [item["task"] for item in summaries["summaries"]] == [
        task["name"] for task in fixture["tasks"]
    ]
    assert len(fixture["memories"]) >= 48
    assert len({slugify(memory["title"]) for memory in fixture["memories"]}) == len(
        fixture["memories"]
    )
    assert {memory["source"] for memory in fixture["memories"]} == set(fixture["source_hashes"])
    assert len(fixture["source_revision"]) == 40
    assert all(character in "0123456789abcdef" for character in fixture["source_revision"])
    for source, expected_hash in fixture["source_hashes"].items():
        assert not Path(source).is_absolute()
        assert ".." not in Path(source).parts
        content = subprocess.check_output(  # noqa: S603 - validated revision and repo path
            ["git", "show", f"{fixture['source_revision']}:{source}"],  # noqa: S607
            cwd=ROOT,
        )
        assert hashlib.sha256(content).hexdigest() == expected_hash

    active = {
        slugify(memory["title"])
        for memory in fixture["memories"]
        if memory["scope"] == "project" and not memory.get("archive", False)
    }
    assert len(active) >= 40
    assert sum(memory.get("archive", False) for memory in fixture["memories"]) >= 2
    assert sum(memory["scope"] == "other_project" for memory in fixture["memories"]) >= 2
    assert all(
        len(task["required"]) >= 3 and set(task["required"]) <= active for task in fixture["tasks"]
    )
    assert all(set(_summary_links(item["body"])) <= active for item in summaries["summaries"])


def test_holdout_planner_projection_has_goals_without_labels() -> None:
    fixture, _ = _load_holdout()
    projection = _label_blind_tasks(fixture)
    rendered = json.dumps(projection)

    assert len(projection) == 8
    assert all(set(task) == {"name", "goal"} for task in projection)
    assert all(slug not in rendered for task in fixture["tasks"] for slug in task["required"])


def test_holdout_benchmark_excludes_inactive_and_other_project_on_repeat_runs() -> None:
    fixture, summaries = _load_holdout()
    first = run_benchmark_for_fixture(fixture, summaries)
    second = run_benchmark_for_fixture(fixture, summaries)

    assert first.task_count == 8
    assert first.active_memory_count >= 40
    assert first.excluded_memory_count >= 4
    assert first.linked_summary_count == 8
    assert set(first.strategies) == {"current_injection", "broad_query", "linked_summary"}
    assert _stable_report(first) == _stable_report(second)
    assert all(
        strategy.inactive_hits == strategy.other_project_hits == 0
        for strategy in first.strategies.values()
    )
    assert all(
        not task.inactive_hits and not task.other_project_hits
        for strategy in first.strategies.values()
        for task in strategy.tasks
    )


def test_optional_human_queries_add_fourth_strategy() -> None:
    fixture, summaries = _load_holdout()
    queries: HumanFocusedQueryFixture = {
        "tasks": [{"name": task["name"], "queries": [task["goal"]]} for task in fixture["tasks"]]
    }

    report = run_benchmark_for_fixture(fixture, summaries, queries)

    assert set(report.strategies) == {
        "current_injection",
        "broad_query",
        "human_focused",
        "linked_summary",
    }
    assert report.strategies["human_focused"].calls == 8
