"""Goal-shaped recall through the real Memex index in an isolated store."""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from eval import agent_workflow
from eval.agent_workflow import (
    RENDERED_FILE_SLUG,
    BenchmarkReport,
    _summary_links,
    load_fixture,
    load_human_focused_queries,
    run_benchmark,
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
