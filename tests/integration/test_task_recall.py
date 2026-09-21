"""Task recall gathers distinct project evidence through existing search."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from memex.application.memory import Memex
from memex.application.task_recall import assemble_task_recall
from memex.domain.models import RecallHit, TaskRecallInput, WikiNode, WriteInput, new_id
from memex.infrastructure.config import MemexConfig

PROJECT = "a" * 24
OTHER_PROJECT = "b" * 24


def _write(memex: Memex, title: str, body: str, project_id: str = PROJECT) -> str:
    return memex.write(
        WriteInput(
            type="entity",
            title=title,
            body=body,
            scope="project",
            project_id=project_id,
        )
    ).slug


def _access_count(memex: Memex, slug: str, project_id: str = PROJECT) -> int:
    row = memex.index_manager.connection.execute(
        "SELECT access_count FROM wiki_index "
        "WHERE scope = 'project' AND project_id = ? AND slug = ?",
        (project_id, slug),
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_task_recall_combines_sources_and_names_unanswered_question(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        shared = _write(memex, "Project layout", "Project layout uses opaque identity and folders")
        prerequisite = _write(memex, "Rebuild rule", "Rebuild the disposable index from pages")
        archived = _write(memex, "Old rebuild rule", "Rebuild obsolete archive method")
        memex.forget(archived, mode="archive")
        expired = _write(memex, "Expired rebuild rule", "Rebuild expired rule")
        memex.forget(expired, mode="soft")
        pending_page = memex.wiki_store.write(
            WikiNode(
                type="entity",
                id=new_id(),
                title="Pending rebuild rule",
                body="Rebuild pending rule",
                scope="project",
                project_id=PROJECT,
                status="pending",
            )
        )
        memex.index_manager.update_record(pending_page)
        superseded_page = memex.wiki_store.write(
            WikiNode(
                type="entity",
                id=new_id(),
                title="Superseded rebuild rule",
                body="Rebuild superseded rule",
                scope="project",
                project_id=PROJECT,
                status="superseded",
            )
        )
        memex.index_manager.update_record(superseded_page)
        _write(memex, "Project layout", "wrong project secret", OTHER_PROJECT)

        result = memex.recall_task(
            TaskRecallInput(
                goal="Repair project memory lookup",
                questions=["project layout", "rebuild index", "unmentioned concern"],
                project_id=PROJECT,
            )
        )

        shared_page = memex.wiki_store.read(shared, scope="project", project_id=PROJECT)
        prerequisite_page = memex.wiki_store.read(prerequisite, scope="project", project_id=PROJECT)
        assert shared_page is not None
        assert prerequisite_page is not None
        assert set(result.sources) == {shared_page.file_path, prerequisite_page.file_path}
        assert result.unanswered_questions == ["unmentioned concern"]
        assert result.omitted_questions == []
        assert "wrong project secret" not in result.context
        assert archived not in result.context
        assert expired not in result.context
        assert pending_page.slug not in result.context
        assert superseded_page.slug not in result.context
        assert "Unanswered questions" in result.context
        assert "Questions:" in result.context
        assert result.rendered_tokens <= 4096
        assert _access_count(memex, shared) == 1
        assert _access_count(memex, prerequisite) == 1
        assert _access_count(memex, archived) == 0
        assert _access_count(memex, expired) == 0
        assert _access_count(memex, pending_page.slug) == 0
        assert _access_count(memex, superseded_page.slug) == 0
    finally:
        memex.close()


def test_task_recall_distributes_pages_across_questions_and_reports_budget(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        for number in range(6):
            _write(memex, f"Alpha page {number}", "alpha keyword " * 12)
        beta = _write(memex, "Beta prerequisite", "beta keyword for prerequisite")

        result = memex.recall_task(
            TaskRecallInput(
                goal="Explain alpha and beta",
                questions=["alpha", "beta"],
                project_id=PROJECT,
                max_hits=3,
            )
        )

        assert len(result.sources) == 3
        beta_page = memex.wiki_store.read(beta, scope="project", project_id=PROJECT)
        assert beta_page is not None
        assert beta_page.file_path in result.sources
        assert "alpha" in result.omitted_questions
        assert result.rendered_tokens <= 4096
    finally:
        memex.close()


def test_task_recall_reports_ninth_eligible_page_without_accessing_it(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        slugs = [_write(memex, f"Alpha page {number}", "alpha evidence") for number in range(9)]
        result = memex.recall_task(
            TaskRecallInput(goal="Inspect alpha", questions=["alpha"], project_id=PROJECT)
        )
        counts = [_access_count(memex, slug) for slug in slugs]
        assert len(result.sources) == 8
        assert result.omitted_questions == ["alpha"]
        assert sorted(counts) == [0] + [1] * 8
    finally:
        memex.close()


def test_task_recall_invalid_question_has_no_access_side_effect(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        slug = _write(memex, "Valid memory", "valid search term")

        with pytest.raises(ValueError, match="question"):
            memex.recall_task(
                TaskRecallInput(
                    goal="Check memory",
                    questions=["valid", "!!!"],
                    project_id=PROJECT,
                )
            )

        assert _access_count(memex, slug) == 0
    finally:
        memex.close()


def test_task_recall_excludes_just_soft_forgotten_page(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        slug = _write(memex, "Recent secret", "recent marker for recall")
        memex.forget(slug, mode="soft")
        result = memex.recall_task(
            TaskRecallInput(goal="Find recent marker", questions=["recent"], project_id=PROJECT)
        )
        assert result.sources == []
        assert result.unanswered_questions == ["recent"]
        assert _access_count(memex, slug) == 0
    finally:
        memex.close()


def test_task_recall_too_small_budget_has_no_access_side_effect(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        slug = _write(memex, "Valid memory", "valid search term")
        with pytest.raises(ValueError, match="max_tokens"):
            memex.recall_task(
                TaskRecallInput(
                    goal="Check memory",
                    questions=["valid"],
                    project_id=PROJECT,
                    max_tokens=1,
                )
            )
        assert _access_count(memex, slug) == 0
    finally:
        memex.close()


def test_task_recall_revalidates_mutated_request_before_search(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        slug = _write(memex, "Valid memory", "valid search term")
        request = TaskRecallInput(goal="Check memory", questions=["valid"], project_id=PROJECT)
        request.questions.extend(["second", "third", "fourth"])
        with pytest.raises(ValueError, match="questions"):
            memex.recall_task(request)
        assert _access_count(memex, slug) == 0
        request.questions = "abc"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="questions"):
            memex.recall_task(request)
        assert _access_count(memex, slug) == 0
    finally:
        memex.close()


def test_task_recall_rejects_malformed_question_container() -> None:
    with pytest.raises(ValueError, match="questions"):
        TaskRecallInput(
            goal="Check memory",
            questions=cast(Any, "abc"),
            project_id=PROJECT,
        )


def test_task_recall_charges_rendered_context_to_token_budget(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    try:
        first = _write(memex, "First alpha", "alpha evidence for the first page")
        second = _write(memex, "Second alpha", "alpha evidence for the second page")
        full = memex.recall_task(
            TaskRecallInput(goal="Check alpha", questions=["alpha"], project_id=PROJECT)
        )
        first_before = _access_count(memex, first)
        second_before = _access_count(memex, second)
        bounded = memex.recall_task(
            TaskRecallInput(
                goal="Check alpha",
                questions=["alpha"],
                project_id=PROJECT,
                max_tokens=full.rendered_tokens - 1,
            )
        )
        assert len(full.sources) == 2
        assert len(bounded.sources) < 2
        assert bounded.rendered_tokens <= full.rendered_tokens - 1
        assert bounded.omitted_questions == ["alpha"]
        first_page = memex.wiki_store.read(first, scope="project", project_id=PROJECT)
        second_page = memex.wiki_store.read(second, scope="project", project_id=PROJECT)
        assert first_page is not None
        assert second_page is not None
        assert _access_count(memex, first) == first_before + (
            first_page.file_path in bounded.sources
        )
        assert _access_count(memex, second) == second_before + (
            second_page.file_path in bounded.sources
        )
    finally:
        memex.close()


def test_task_assembler_can_use_later_unique_hit_after_duplicates() -> None:
    def hit(slug: str) -> RecallHit:
        return RecallHit(
            slug=slug,
            file_path=f"/{slug}.md",
            title=slug,
            node_type="entity",
            importance=0.5,
            score=0.0,
            rank=1,
            snippet=slug,
            snippet_source="body",
            tags=[],
            created="2026-01-01T00:00:00Z",
            updated="2026-01-01T00:00:00Z",
            last_access=None,
            transcript_ref=None,
            links=[],
            scope="project",
            project_id=PROJECT,
        )

    first, second = hit("first"), hit("second")
    request = TaskRecallInput(
        goal="Inspect duplicate results",
        questions=["first", "second"],
        project_id=PROJECT,
        max_hits=2,
    )
    result, selected = assemble_task_recall(request, [[first] * 8 + [second], [first]])
    assert [page.slug for page in selected] == ["first", "second"]
    assert result.sources == ["/first.md", "/second.md"]
    assert result.omitted_questions == []
