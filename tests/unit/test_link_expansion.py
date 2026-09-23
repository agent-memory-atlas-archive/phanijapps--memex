"""Link-graph expansion: neighbours of recall hits packed after the hits themselves."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest

from memex.application.context_injection import (
    DEFAULT_MAX_TOKENS,
    build_injection,
    estimate_tokens,
)
from memex.application.graph_expansion import (
    ExpansionEntry,
    expand_links,
    omitted_marker,
    render_expansion,
)
from memex.application.memory import Memex
from memex.application.task_recall import assemble_task_recall, with_linked_pages
from memex.domain.models import RecallHit, TaskRecallInput, WikiNode, WriteInput, new_id
from memex.infrastructure.config import MemexConfig

PROJECT = "a" * 24
OTHER_PROJECT = "b" * 24


@pytest.fixture
def memex(data_dir: Path) -> Iterator[Memex]:
    instance = Memex(MemexConfig(data_dir=data_dir))
    yield instance
    instance.close()


def _write(
    memex: Memex,
    title: str,
    body: str,
    *,
    scope: str = "project",
    project_id: str | None = PROJECT,
    description: str = "",
    depends_on: list[str] | None = None,
) -> str:
    return memex.write(
        WriteInput(
            type="entity",
            title=title,
            body=body,
            description=description,
            scope=scope,
            project_id=project_id if scope == "project" else None,
            depends_on=depends_on or [],
        )
    ).slug


def _seeds(memex: Memex, query: str) -> list[RecallHit]:
    return memex.recall(query, scope="project", project_id=PROJECT).hits


def _slugs(items: Iterable[RecallHit | ExpansionEntry]) -> list[str]:
    return [item.slug for item in items]


def test_expansion_visits_level_by_level_with_alphabetical_tie_break(memex: Memex) -> None:
    _write(memex, "Seed", "seedword links [[cee]] then [[ay]] then [[bee]]")
    _write(memex, "Cee", "cee page")
    _write(memex, "Ay", "ay page links [[zed]] and [[why]]")
    _write(memex, "Bee", "bee page links [[ex]]")
    _write(memex, "Zed", "zed page")
    _write(memex, "Why", "why page")
    _write(memex, "Ex", "ex page")
    seeds = _seeds(memex, "seedword")

    one_hop = expand_links(memex, seeds, max_tokens=DEFAULT_MAX_TOKENS)
    two_hops = expand_links(memex, seeds, depth=2, max_tokens=DEFAULT_MAX_TOKENS)

    assert _slugs(one_hop.entries) == ["ay", "bee", "cee"]
    assert _slugs(two_hops.entries) == ["ay", "bee", "cee", "ex", "why", "zed"]
    assert [entry.depth for entry in two_hops.entries] == [1, 1, 1, 2, 2, 2]
    assert two_hops.entries[0].hops == (("mentions", "ay"),)
    assert two_hops.entries[3].hops == (("mentions", "bee"), ("mentions", "ex"))
    assert two_hops.entries[3].seed == "seed"
    assert two_hops.omitted == 0
    assert two_hops == expand_links(memex, seeds, depth=2, max_tokens=DEFAULT_MAX_TOKENS)


def test_expansion_block_names_concept_depth_and_route_without_the_body(memex: Memex) -> None:
    _write(memex, "Seed", "seedword", depends_on=["target"])
    _write(
        memex,
        "Target",
        "The long body must never be rendered in an expansion block.",
        description="Short purpose line",
    )
    seeds = _seeds(memex, "seedword")

    expansion = expand_links(memex, seeds, max_tokens=DEFAULT_MAX_TOKENS)

    (entry,) = expansion.entries
    lines = entry.block.splitlines()
    assert lines[0] == "+ Target (entity) | depth: 1 | via: seed -depends_on-> target"
    assert lines[1].startswith("   File: ") and lines[1].endswith("/target.md")
    assert lines[2] == "   Short purpose line"
    assert "long body" not in entry.block
    assert entry.tokens == estimate_tokens(entry.block)


def test_expansion_falls_back_to_a_short_body_snippet(memex: Memex) -> None:
    _write(memex, "Seed", "seedword [[target]]")
    _write(memex, "Target", "word " * 100)
    seeds = _seeds(memex, "seedword")

    (entry,) = expand_links(memex, seeds, max_tokens=DEFAULT_MAX_TOKENS).entries

    snippet = entry.block.splitlines()[2].strip()
    assert snippet.startswith("word word")
    assert len(snippet) <= 200


def test_expansion_is_cycle_safe_and_excludes_seeds(memex: Memex) -> None:
    _write(memex, "Alpha", "seedword alpha links [[beta]] and [[gamma]]")
    _write(memex, "Beta", "beta links back to [[alpha]] and on to [[gamma]]")
    _write(memex, "Gamma", "seedword gamma links [[alpha]]")
    seeds = _seeds(memex, "seedword")
    assert sorted(_slugs(seeds)) == ["alpha", "gamma"]

    expansion = expand_links(memex, seeds, depth=5, max_tokens=DEFAULT_MAX_TOKENS)

    assert _slugs(expansion.entries) == ["beta"]
    assert expansion.omitted == 0


def test_expansion_cuts_to_budget_and_counts_the_omitted(memex: Memex) -> None:
    _write(memex, "Seed", "seedword [[ay]] [[bee]] [[cee]] [[dee]]")
    for title in ("Ay", "Bee", "Cee", "Dee"):
        _write(memex, title, f"{title.lower()} page", description="x" * 120)
    seeds = _seeds(memex, "seedword")
    full = expand_links(memex, seeds, max_tokens=DEFAULT_MAX_TOKENS)
    assert len(full.entries) == 4
    budget = full.entries[0].tokens + full.entries[1].tokens + estimate_tokens(omitted_marker(2))

    cut = expand_links(memex, seeds, max_tokens=budget)

    assert _slugs(cut.entries) == ["ay", "bee"]
    assert cut.omitted == 2
    rendered = render_expansion(cut)
    assert rendered[-1] == "[memex] linked pages omitted (token budget): 2"
    assert estimate_tokens("\n".join(rendered)) <= budget
    assert render_expansion(full)[-1].startswith("   ")
    assert expand_links(memex, seeds, max_tokens=0).omitted == 4


def test_expansion_keeps_every_entry_that_fits_without_reserving_a_marker(memex: Memex) -> None:
    _write(memex, "Seed", "seedword [[ay]] [[bee]]")
    _write(memex, "Ay", "ay page", description="x" * 120)
    _write(memex, "Bee", "bee page", description="y" * 120)
    seeds = _seeds(memex, "seedword")
    full = expand_links(memex, seeds, max_tokens=DEFAULT_MAX_TOKENS)
    exact = sum(entry.tokens for entry in full.entries)

    fits = expand_links(memex, seeds, max_tokens=exact)

    assert _slugs(fits.entries) == ["ay", "bee"]
    assert fits.omitted == 0
    assert estimate_tokens("\n".join(render_expansion(fits))) <= exact
    assert expand_links(memex, seeds, max_tokens=exact - 1).omitted == 1


def test_expansion_omits_the_summary_line_when_there_is_nothing_to_show(memex: Memex) -> None:
    _write(memex, "Seed", "seedword [[target]]")
    _write(memex, "Target", " ")
    seeds = _seeds(memex, "seedword")

    (entry,) = expand_links(memex, seeds, max_tokens=DEFAULT_MAX_TOKENS).entries

    lines = entry.block.splitlines()
    assert len(lines) == 2
    assert lines[1].startswith("   File: ")


def test_expansion_never_reaches_pages_recall_would_hide(memex: Memex) -> None:
    _write(
        memex,
        "Seed",
        "seedword [[archived]] [[expired]] [[pending]] [[elsewhere]] [[shared]] [[visible]]",
    )
    memex.forget(_write(memex, "Archived", "archived page"), mode="archive")
    memex.forget(_write(memex, "Expired", "expired page"), mode="soft")
    pending = memex.wiki_store.write(
        WikiNode(
            type="entity",
            id=new_id(),
            title="Pending",
            body="pending page",
            scope="project",
            project_id=PROJECT,
            status="pending",
        )
    )
    memex.index_manager.update_record(pending)
    _write(memex, "Elsewhere", "other project page", project_id=OTHER_PROJECT)
    memex.forget(_write(memex, "Shared", "this project copy"), mode="archive")
    _write(memex, "Shared", "other project copy", project_id=OTHER_PROJECT)
    _write(memex, "Visible", "visible page")
    seeds = _seeds(memex, "seedword")

    session_start = expand_links(memex, seeds, max_tokens=DEFAULT_MAX_TOKENS)
    task_recall = expand_links(
        memex, seeds, max_tokens=DEFAULT_MAX_TOKENS, scope="project", project_id=PROJECT
    )

    assert _slugs(session_start.entries) == _slugs(task_recall.entries) == ["visible"]
    assert session_start.omitted == task_recall.omitted == 0


def test_expansion_follows_a_project_link_to_a_global_page_under_global_recall(
    memex: Memex,
) -> None:
    _write(memex, "Seed", "seedword [[shared-tool]]", depends_on=["shared-tool"])
    _write(memex, "Shared tool", "global page", scope="global", description="Everyone's tool")
    seeds = _seeds(memex, "seedword")
    assert memex.link_manager.validate_links("seed") == []

    session_start = expand_links(memex, seeds, max_tokens=DEFAULT_MAX_TOKENS)
    task_recall = expand_links(
        memex, seeds, max_tokens=DEFAULT_MAX_TOKENS, scope="project", project_id=PROJECT
    )

    (entry,) = session_start.entries
    assert (entry.slug, entry.scope, entry.project_id) == ("shared-tool", "global", None)
    assert entry.hops == (("depends_on", "shared-tool"),)
    assert task_recall.entries == [] and task_recall.omitted == 0


def test_expansion_runs_on_global_seeds_for_the_session_start_path(memex: Memex) -> None:
    _write(memex, "Seed", "seedword [[neighbour]]", scope="global")
    _write(memex, "Neighbour", "global neighbour", scope="global", description="Global page")
    _write(memex, "Neighbour", "project copy never named by a global page")
    seeds = memex.recall("seedword").hits
    assert [(hit.scope, hit.project_id) for hit in seeds] == [("global", None)]

    (entry,) = expand_links(memex, seeds, max_tokens=DEFAULT_MAX_TOKENS).entries

    assert (entry.slug, entry.scope, entry.project_id) == ("neighbour", "global", None)
    assert entry.block.splitlines()[2] == "   Global page"


def test_expansion_rejects_negative_depth(memex: Memex) -> None:
    with pytest.raises(ValueError, match="depth"):
        expand_links(memex, [], depth=-1, max_tokens=DEFAULT_MAX_TOKENS)


def test_injection_packs_direct_hits_first_and_links_after(memex: Memex) -> None:
    _write(memex, "Seed", "seedword page links [[linked]]", description="seed purpose")
    _write(memex, "Linked", "linked page never mentions the query", description="linked purpose")

    plain = build_injection(memex, "seedword", depth=0)
    expanded = build_injection(memex, "seedword")

    assert "linked.md" not in plain
    assert expanded.startswith(plain.removesuffix("=== END memex MEMORY ==="))
    assert expanded.index("/seed.md") < expanded.index("/linked.md")
    assert "+ Linked (entity) | depth: 1 | via: seed -mentions-> linked" in expanded
    assert expanded.rstrip().endswith("=== END memex MEMORY ===")
    assert estimate_tokens(expanded) <= DEFAULT_MAX_TOKENS


def test_injection_keeps_every_direct_hit_when_links_do_not_fit(memex: Memex) -> None:
    _write(memex, "Seed", "seedword page links [[linked]]")
    _write(memex, "Other", "seedword page with no links")
    _write(memex, "Linked", "linked page", description="y" * 200)
    plain = build_injection(memex, "seedword", depth=0)
    budget = estimate_tokens(plain) + 20

    expanded = build_injection(memex, "seedword", max_tokens=budget)

    assert expanded.count("File: ") == 2
    assert "/linked.md" not in expanded
    assert "[memex] linked pages omitted (token budget): 1" in expanded
    assert "/seed.md" in expanded and "/other.md" in expanded
    assert estimate_tokens(expanded) <= budget


def test_task_recall_fills_the_remaining_budget_with_linked_pages(memex: Memex) -> None:
    _write(memex, "Seed", "seedword evidence links [[linked]]")
    _write(memex, "Linked", "linked page", description="linked purpose")
    request = TaskRecallInput(goal="Check seedword", questions=["seedword"], project_id=PROJECT)
    ranked = [
        memex.retriever.retrieve_without_access(
            "seedword", top_k=12, scope="project", project_id=PROJECT
        ).hits
    ]

    plain, selected = assemble_task_recall(request, ranked)
    expanded = with_linked_pages(memex, request, plain, selected)

    assert _slugs(selected) == ["seed"]
    assert expanded.sources == plain.sources
    assert expanded.context.startswith(plain.context)
    assert "+ Linked (entity) | depth: 1 | via: seed -mentions-> linked" in expanded.context
    assert expanded.rendered_tokens == estimate_tokens(expanded.context) <= request.max_tokens


def test_task_recall_marks_cut_links_within_the_budget(memex: Memex) -> None:
    _write(memex, "Seed", "seedword evidence links [[linked]]")
    _write(memex, "Linked", "linked page", description="z" * 200)
    ranked = [
        memex.retriever.retrieve_without_access(
            "seedword", top_k=12, scope="project", project_id=PROJECT
        ).hits
    ]
    plain, _ = assemble_task_recall(
        TaskRecallInput(goal="Check seedword", questions=["seedword"], project_id=PROJECT), ranked
    )
    request = TaskRecallInput(
        goal="Check seedword",
        questions=["seedword"],
        project_id=PROJECT,
        max_tokens=plain.rendered_tokens + 13,
    )

    result, selected = assemble_task_recall(request, ranked)
    expanded = with_linked_pages(memex, request, result, selected)

    assert _slugs(selected) == ["seed"]
    assert "/linked.md" not in expanded.context
    assert expanded.context.endswith("[memex] linked pages omitted (token budget): 1")
    assert expanded.rendered_tokens <= request.max_tokens
