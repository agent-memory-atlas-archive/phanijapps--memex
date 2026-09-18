import json
import subprocess
import sys
from pathlib import Path

import pytest

from memex.application.memory import Memex
from memex.domain.models import WriteInput
from memex.infrastructure.config import MemexConfig
from memex.infrastructure.index_manager import IndexManager

WINNER_QUERY = "atlas risk integration"
WINNER_SLUG = "atlas-risk-integration"


def _memex(data_dir: Path) -> Memex:
    return Memex(MemexConfig(data_dir=data_dir))


def _write(
    memex: Memex,
    *,
    title: str,
    body: str,
    node_type: str = "entity",
    tags: list[str] | None = None,
    expires_at: str | None = None,
    valid_to: str | None = None,
    status: str = "active",
) -> str:
    node = memex.write(
        WriteInput(
            type=node_type,
            title=title,
            body=body,
            tags=tags or [],
            expires_at=expires_at,
            valid_to=valid_to,
        )
    )
    if status != "active":
        memex.forget(node.slug, mode="archive")
    return node.slug


def _winner_store(data_dir: Path) -> Memex:
    memex = _memex(data_dir)
    _write(
        memex,
        title="Atlas risk integration",
        body=" ".join(["noise"] * 30) + " atlas risk integration atlas risk integration",
        tags=["winner", "risk"],
    )
    _write(
        memex,
        title="Atlas risk integration decoy",
        body="short title-only match",
        tags=["legacy"],
    )
    _write(
        memex,
        title="Atlas risk",
        body=" ".join(["atlas", "risk"] * 20),
        tags=["legacy"],
    )
    _write(
        memex,
        title="Integration unrelated",
        body="integration release notes without atlas or risk context",
    )
    return memex


def _access_counts(data_dir: Path) -> dict[str, int]:
    index = IndexManager(data_dir / "mem.db")
    rows = index.connection.execute("SELECT slug, access_count FROM wiki_index").fetchall()
    index.close()
    return {str(row["slug"]): int(row["access_count"]) for row in rows}


def test_selected_ranker_wins_through_memex_and_cli(data_dir: Path) -> None:
    memex = _winner_store(data_dir)

    legacy_first = memex.retriever.search_fts(WINNER_QUERY, 1)[0][0]
    result = memex.recall(WINNER_QUERY)

    assert legacy_first != WINNER_SLUG
    assert result.search_engine == "semantic-and-fallback-fts5"
    assert result.hits[0].slug == WINNER_SLUG

    completed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "memex.cli",
            "--data-dir",
            str(data_dir),
            "recall",
            WINNER_QUERY,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["search_engine"] == "semantic-and-fallback-fts5"
    assert payload["hits"][0]["slug"] == WINNER_SLUG


def test_recall_help_exposes_no_experimental_selector() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "memex.cli", "recall", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    help_text = completed.stdout.casefold()
    assert completed.returncode == 0
    assert "backend" not in help_text
    assert "ranker" not in help_text
    assert "experimental" not in help_text


def test_selected_ranker_filter_matrix_matches_eligibility(data_dir: Path) -> None:
    memex = _memex(data_dir)
    _write(memex, title="Atlas entity", body="atlas risk integration", tags=["tool"])
    _write(
        memex,
        title="Atlas preference",
        body="atlas risk integration",
        node_type="preference",
        tags=["style"],
    )
    _write(
        memex,
        title="Atlas expired",
        body="atlas risk integration",
        expires_at="2000-01-01T00:00:00Z",
    )
    _write(
        memex,
        title="Atlas inactive",
        body="atlas risk integration",
        status="archived",
    )

    assert [hit.slug for hit in memex.recall(WINNER_QUERY, node_type="preference").hits] == [
        "atlas-preference"
    ]
    assert [hit.slug for hit in memex.recall(WINNER_QUERY, tags=["tool"]).hits] == ["atlas-entity"]
    assert (
        memex.recall(
            WINNER_QUERY,
            time_range=("2100-01-01T00:00:00Z", "2101-01-01T00:00:00Z"),
        ).hits
        == []
    )
    assert "atlas-expired" not in [hit.slug for hit in memex.recall(WINNER_QUERY).hits]
    assert "atlas-expired" in [
        hit.slug for hit in memex.recall(WINNER_QUERY, include_expired=True).hits
    ]
    assert "atlas-inactive" not in [hit.slug for hit in memex.recall(WINNER_QUERY).hits]
    assert "atlas-inactive" in [
        hit.slug for hit in memex.recall(WINNER_QUERY, include_inactive=True).hits
    ]


def test_selected_ranker_access_top_k_and_tie_stability(data_dir: Path) -> None:
    memex = _memex(data_dir)
    _write(memex, title="Beta tie", body=WINNER_QUERY)
    _write(memex, title="Alpha tie", body=WINNER_QUERY)
    _write(memex, title="Atlas decoy", body="atlas risk")

    for bad_top_k in (0, 101):
        with pytest.raises(ValueError, match="top_k"):
            memex.recall(WINNER_QUERY, top_k=bad_top_k)

    assert memex.recall(WINNER_QUERY, top_k=1).hits[0].slug == "alpha-tie"
    assert len(memex.recall(WINNER_QUERY, top_k=100).hits) == 2

    orders = {tuple(hit.slug for hit in memex.recall(WINNER_QUERY).hits) for _ in range(100)}
    assert orders == {("alpha-tie", "beta-tie")}
    assert [hit.rank for hit in memex.recall(WINNER_QUERY).hits] == [1, 2]

    counts = _access_counts(data_dir)
    assert counts["alpha-tie"] == 103
    assert counts["beta-tie"] == 102
    assert counts["atlas-decoy"] == 0
