"""Goal-shaped recall through the real Memex index in an isolated store."""

import hashlib
from pathlib import Path

from eval.agent_workflow import load_fixture, run_benchmark


def test_workflow_fixture_has_traceable_and_complete_labels() -> None:
    fixture = load_fixture()
    root = Path(__file__).resolve().parents[2]
    current = [memory for memory in fixture["memories"] if memory["scope"] == "project"]

    assert len(fixture["source_revision"]) == 40
    assert all(
        not memory.get("archive") or memory["source"].startswith("simulated") for memory in current
    )
    for source, expected_hash in fixture["source_hashes"].items():
        assert hashlib.sha256((root / source).read_bytes()).hexdigest() == expected_hash
    for memory in current:
        if memory.get("archive"):
            continue
        assert memory["source"] in fixture["source_hashes"]
        source_text = " ".join((root / memory["source"]).read_text(encoding="utf-8").split())
        assert " ".join(memory["evidence"].split()) in source_text
    assert len({memory["title"] for memory in fixture["memories"]}) == len(fixture["memories"])
    assert len(fixture["tasks"]) >= 6
    assert all(len(task["required"]) >= 3 for task in fixture["tasks"])


def test_real_workflow_recall_keeps_scopes_and_recovers_task_evidence() -> None:
    report = run_benchmark()

    assert report.memory_count >= 20
    assert report.excluded_memory_count >= 4
    assert report.focused_evidence_recall >= 0.9
    assert report.focused_complete >= 4
    assert all(len(task.one_shot_hits) <= 8 for task in report.tasks)
    assert all(len(task.focused_hits) <= 8 for task in report.tasks)
