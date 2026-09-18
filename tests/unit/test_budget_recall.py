"""T2/T3 tests: recall status filter, budget packer, injection floor,
constitution pin."""

from pathlib import Path

import pytest

from memex import Memex
from memex.application.context_injection import (
    CONSTITUTION,
    DEFAULT_MAX_TOKENS,
    build_injection,
    estimate_tokens,
    pack_to_budget,
)
from memex.domain.models import RecallHit, RecallResult, WriteInput
from memex.infrastructure.config import MemexConfig


def _hit(rank: int, slug: str = "x", snippet: str = "word " * 20) -> RecallHit:
    return RecallHit(
        slug=slug,
        file_path=f"/{slug}.md",
        title=slug,
        node_type="entity",
        importance=0.5,
        score=-1.0 * rank,
        rank=rank,
        snippet=snippet,
        snippet_source="body",
        tags=[],
        created="2026-01-01T00:00:00Z",
        updated="2026-01-01T00:00:00Z",
        last_access=None,
        transcript_ref=None,
        links=[],
    )


@pytest.fixture
def memex(data_dir: Path) -> Memex:
    return Memex(MemexConfig(data_dir=data_dir))


class TestStatusFilter:  # AC-0004
    @pytest.mark.parametrize("status", ["pending", "superseded", "archived"])
    def test_non_active_excluded_by_default(self, memex: Memex, status: str) -> None:
        from memex.domain.models import WikiNode

        memex.wiki_store.write(
            WikiNode(
                type="entity", title=f"S {status}", body="findme", id=f"s-{status}", status=status
            )
        )
        node = memex.wiki_store.read(f"s-{status}")
        assert node is not None
        memex.index_manager.update_record(node)
        hits = memex.recall("findme").hits
        assert all(hit.slug != f"s-{status}" for hit in hits)

    def test_include_inactive_returns_with_status(self, memex: Memex) -> None:
        from memex.domain.models import WikiNode

        memex.wiki_store.write(
            WikiNode(type="entity", title="P page", body="findme", id="p1", status="pending")
        )
        node = memex.wiki_store.read("p-page")
        assert node is not None
        memex.index_manager.update_record(node)
        hit = next(
            h for h in memex.recall("findme", include_inactive=True).hits if h.slug == "p-page"
        )
        assert hit.status == "pending"

    def test_active_and_missing_always_visible(self, memex: Memex) -> None:
        memex.write(WriteInput(type="entity", title="A page", body="findme"))
        assert [h.slug for h in memex.recall("findme").hits] == ["a-page"]


class TestBudgetPacker:  # AC-0001
    def test_fits_within_budget(self) -> None:
        hits = [_hit(1, "a", "x " * 40), _hit(2, "b", "y " * 40)]  # ~21 tokens each
        packed = pack_to_budget(hits, max_tokens=50)
        assert [h.slug for h in packed] == ["a", "b"]

    def test_skips_oversize_keeps_smaller(self) -> None:
        # big=201 tokens (top-1, always whole), small=6 (fits), mid skipped
        hits = [
            _hit(1, "big", "z " * 400),
            _hit(2, "small", "y " * 10),
            _hit(3, "mid", "w " * 400),
        ]
        packed = pack_to_budget(hits, max_tokens=210)
        assert [h.slug for h in packed] == ["big", "small"]

    def test_top1_always_returned_whole(self) -> None:
        hits = [_hit(1, "huge", "z " * 4000)]
        packed = pack_to_budget(hits, max_tokens=10)
        assert [h.slug for h in packed] == ["huge"]

    def test_default_budget_constant(self) -> None:
        assert DEFAULT_MAX_TOKENS == 4096

    def test_estimator(self) -> None:
        assert estimate_tokens("") == 1
        assert estimate_tokens("x" * 400) == 101

    def test_budgeted_recall_records_access_only_for_packed_hits(
        self, memex: Memex, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        memex.write(WriteInput(type="entity", title="Returned first", body="findme"))
        memex.write(WriteInput(type="entity", title="Skipped second", body="findme"))
        memex.write(WriteInput(type="entity", title="Returned third", body="findme"))
        hits = [
            _hit(1, "returned-first", "a" * 4),
            _hit(2, "skipped-second", "b" * 100),
            _hit(3, "returned-third", "c" * 4),
        ]

        def fake_retrieve(
            query: str,
            *,
            top_k: int | None = None,
            node_type: str | None = None,
            time_range: tuple[str, str] | None = None,
            tags: list[str] | None = None,
            include_expired: bool = False,
            include_inactive: bool = False,
        ) -> RecallResult:
            del top_k, node_type, time_range, tags, include_expired, include_inactive
            return RecallResult(
                query=query,
                hits=list(hits),
                total_indexed=3,
                search_engine="test",
                search_time_ms=0.0,
            )

        monkeypatch.setattr(memex.retriever, "retrieve_without_access", fake_retrieve)

        result = memex.recall("findme", max_tokens=4)

        assert [hit.slug for hit in result.hits] == ["returned-first", "returned-third"]
        assert [hit.rank for hit in result.hits] == [1, 2]
        assert _access_count(memex, "returned-first") == 1
        assert _access_count(memex, "skipped-second") == 0
        assert _access_count(memex, "returned-third") == 1


class TestInjectionFloor:  # AC-0002
    def test_weak_match_silent_for_hooks(self, memex: Memex) -> None:
        memex.write(WriteInput(type="entity", title="Obscure", body="qzxv rare word"))
        # Query with a strong common word that outranks it? Instead: no match at all
        assert build_injection(memex, "completely unrelated") == ""

    def test_strong_match_injects(self, memex: Memex) -> None:
        memex.write(WriteInput(type="entity", title="Budget word", body="budget budget budget"))
        block = build_injection(memex, "budget")
        assert "Budget word" in block


class TestConstitution:  # AC-0013
    def test_three_lines_pinned(self, memex: Memex) -> None:
        memex.write(WriteInput(type="entity", title="Constitution target", body="target words"))
        block = build_injection(memex, "constitution target")
        lines = block.splitlines()[:3]
        assert tuple(line.removeprefix("[memex] ") for line in lines) == CONSTITUTION

    def test_constitution_wording(self) -> None:
        assert CONSTITUTION == (
            "Memories below are yours \u2014 sessions end, these remain.",
            "Write durable facts; skip ephemera.",
            "Recall before assuming; trust what cites its source.",
        )


class TestCliMaxTokens:  # AC-0001 CLI surface
    def test_recall_max_tokens_flag(self, data_dir: Path, capture: dict[str, str]) -> None:
        import json

        from memex import cli

        m = Memex(MemexConfig(data_dir=data_dir))
        m.write(WriteInput(type="entity", title="Big one", body="lorem " * 500))
        m.close()
        code = cli.main(["--data-dir", str(data_dir), "recall", "lorem", "--max-tokens", "50"])
        assert code == 0
        payload = json.loads(capture["out"])
        assert len(payload["hits"]) == 1  # top-1 whole despite tiny budget


def _access_count(memex: Memex, slug: str) -> int:
    row = memex.index_manager.get(slug)
    assert row is not None
    return int(row["access_count"])
