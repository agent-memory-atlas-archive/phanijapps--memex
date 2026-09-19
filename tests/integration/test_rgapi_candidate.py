from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from eval.rgapi_candidate import (
    MAX_PATTERN_BYTES,
    MAX_RESULTS,
    SEARCH_TIMEOUT_MS,
    RgapiCandidateResult,
    rank_rgapi_candidate,
    safe_rgapi_pattern,
)
from eval.selection import _hydrate_rgapi_hits
from memex.domain.models import WikiNode
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.wiki_store import WikiStore


def test_base_install_recalls_without_rgapi_or_rg_executable(tmp_path: Path) -> None:
    script = """
import os
from pathlib import Path

from memex.application.memory import Memex
from memex.domain.models import WriteInput
from memex.infrastructure.config import ConfigLoader

data_dir = Path(os.environ["MEMEX_DATA_DIR"])
memex = Memex(ConfigLoader().load())
try:
    memex.write(WriteInput(type="preference", title="Needle", body="alpha needle"))
    memex.rebuild_index(force=True)
    result = memex.recall("needle", top_k=1)
    assert result.hits and result.hits[0].slug == "needle"
finally:
    memex.close()
"""
    executable_dir = tmp_path / "bin"
    executable_dir.mkdir()
    uv_bin = shutil.which("uv")
    assert uv_bin is not None
    (executable_dir / "uv").symlink_to(uv_bin)
    completed = subprocess.run(  # noqa: S603 - fixture verifies no rg executable on PATH.
        [
            str(executable_dir / "uv"),
            "run",
            "--no-extra",
            "eval-rgapi",
            "python",
            "-c",
            script,
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={"MEMEX_DATA_DIR": str(tmp_path / "memex-home"), "PATH": str(executable_dir)},
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(
    importlib.util.find_spec("rgapi") is None,
    reason="optional eval-rgapi extra is not installed",
)
def test_rgapi_candidate_uses_in_process_structured_rows_without_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "alpha.md").write_text("needle in a page", encoding="utf-8")

    spawn_attempts: list[object] = []

    def record_spawn(*args: object, **kwargs: object) -> None:
        spawn_attempts.append((args, kwargs))
        raise AssertionError("rgapi candidate must not spawn a subprocess")

    monkeypatch.setattr(subprocess, "Popen", record_spawn)

    result = rank_rgapi_candidate("needle", docs_dir)

    assert result == RgapiCandidateResult(
        ranked=result.ranked,
        complete=True,
        stop_reason=None,
    )
    assert result.actual_slugs == ["alpha"]
    assert spawn_attempts == []


@pytest.mark.skipif(
    importlib.util.find_spec("rgapi") is None,
    reason="optional eval-rgapi extra is not installed",
)
def test_rgapi_candidate_does_not_follow_symlink_outside_docs(tmp_path: Path) -> None:
    docs_dir = tmp_path / "store" / "docs"
    docs_dir.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("outside-root-canary", encoding="utf-8")
    (docs_dir / "inside.md").write_text("ordinary page", encoding="utf-8")
    (docs_dir / "linked.md").symlink_to(outside)

    result = rank_rgapi_candidate("outside-root-canary", docs_dir)

    assert result.complete is True
    assert result.actual_slugs == []


def test_rgapi_candidate_hands_native_walker_non_following_symlink_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_dir = tmp_path / "store" / "docs"
    docs_dir.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("outside-root-canary", encoding="utf-8")
    (docs_dir / "linked.md").symlink_to(outside)
    outside_open_attempts: list[Path] = []

    def open_outside_canary(path: Path) -> None:
        outside_open_attempts.append(path)
        raise AssertionError("outside-root canary must not be opened")

    _install_fake_rgapi(
        monkeypatch,
        [],
        walker=_symlink_walker_canary(docs_dir, outside, open_outside_canary),
    )

    result = rank_rgapi_candidate("outside-root-canary", docs_dir)

    assert result.complete is True
    assert result.actual_slugs == []
    assert outside_open_attempts == []


@pytest.mark.parametrize(
    ("rows", "prepare"),
    [
        pytest.param(["/secret.md"], lambda _docs_dir: None, id="absolute"),
        pytest.param(["../secret.md"], lambda _docs_dir: None, id="traversal"),
        pytest.param(["missing.md"], lambda _docs_dir: None, id="resolve-error"),
        pytest.param(
            ["nonregular.md"],
            lambda docs_dir: (docs_dir / "nonregular.md").mkdir(),
            id="non-regular",
        ),
    ],
)
def test_rgapi_candidate_rejects_bad_returned_paths_without_exposing_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rows: list[str],
    prepare: Callable[[Path], None],
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    prepare(docs_dir)
    _install_fake_rgapi(monkeypatch, rows)

    result = rank_rgapi_candidate("needle", docs_dir)

    assert result.complete is False
    assert result.stop_reason == "path_rejected"


def test_rgapi_candidate_rejects_returned_junction_before_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    candidate = docs_dir / "junction.md"
    candidate.write_text("needle", encoding="utf-8")
    _install_fake_rgapi(monkeypatch, ["junction.md"])

    original_is_junction = Path.is_junction

    def fake_is_junction(path: Path) -> bool:
        if path == candidate:
            return True
        return original_is_junction(path)

    monkeypatch.setattr(Path, "is_junction", fake_is_junction)

    result = rank_rgapi_candidate("needle", docs_dir)

    assert result.complete is False
    assert result.stop_reason == "path_rejected"


@pytest.mark.parametrize("stop_reason", ["timeout", "max_results"])
def test_rgapi_candidate_marks_timeout_or_max_results_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stop_reason: str,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    _install_fake_rgapi(monkeypatch, [], complete=False, stop_reason=stop_reason)

    result = rank_rgapi_candidate("needle", docs_dir)

    assert result.complete is False
    assert result.stop_reason == "incomplete_search"
    assert result.ranker_metadata()["stop_reason"] == "incomplete_search"


def test_rgapi_candidate_passes_bounded_literal_pattern_and_work_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "alpha.md").write_text("c++ needle", encoding="utf-8")
    calls: list[dict[str, object]] = []
    _install_fake_rgapi(monkeypatch, ["alpha.md"], calls=calls)

    result = rank_rgapi_candidate("C++ needle.*", docs_dir)

    assert result.actual_slugs == ["alpha"]
    assert calls == [
        {
            "pattern": "c|needle",
            "root": docs_dir.resolve(strict=True),
            "paths": True,
            "include": "*.md",
            "follow_links": False,
            "same_file_system": True,
            "max_results": MAX_RESULTS,
            "timeout_ms": SEARCH_TIMEOUT_MS,
            "case_sensitive": False,
        }
    ]


def test_rgapi_selection_filters_eligibility_before_top_k(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "store"
    docs_dir = data_dir / "docs"
    docs_dir.mkdir(parents=True)
    index = _rgapi_index(
        data_dir,
        [
            WikiNode(type="entity", title="Alpha expired", body="needle", id="alpha-expired"),
            WikiNode(type="entity", title="Beta inactive", body="needle", id="beta-inactive"),
            WikiNode(type="entity", title="Gamma active", body="needle", id="gamma-active"),
        ],
    )
    index.connection.execute(
        "UPDATE wiki_index SET expires_at = ? WHERE slug = ?",
        ("2000-01-01T00:00:00Z", "alpha-expired"),
    )
    index.connection.execute(
        "UPDATE wiki_index SET status = ? WHERE slug = ?",
        ("archived", "beta-inactive"),
    )
    index.connection.commit()
    for slug in ("alpha-expired", "beta-inactive", "gamma-active"):
        (docs_dir / f"{slug}.md").write_text("needle", encoding="utf-8")
    _install_fake_rgapi(
        monkeypatch,
        ["alpha-expired.md", "beta-inactive.md", "gamma-active.md"],
    )

    ranking = rank_rgapi_candidate("needle", docs_dir)
    hits = _hydrate_rgapi_hits(index.connection, "needle", ranking.actual_slugs, top_k=1)

    assert ranking.actual_slugs[:3] == ["alpha-expired", "beta-inactive", "gamma-active"]
    assert [hit.slug for hit in hits] == ["gamma-active"]
    assert [hit.rank for hit in hits] == [1]
    index.close()


def test_rgapi_pattern_refuses_empty_or_oversized_queries() -> None:
    assert safe_rgapi_pattern("deploy.*now") == "deploy|now"
    with pytest.raises(ValueError, match="no searchable"):
        safe_rgapi_pattern(".*")

    oversized = " ".join(["a" * 50] * ((MAX_PATTERN_BYTES // 50) + 2))
    with pytest.raises(ValueError, match="1024 bytes"):
        safe_rgapi_pattern(oversized)


def _install_fake_rgapi(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[str],
    *,
    complete: bool = True,
    stop_reason: str | None = None,
    calls: list[dict[str, object]] | None = None,
    walker: Callable[[dict[str, object]], None] | None = None,
) -> None:
    module = ModuleType("rgapi")

    def rg(pattern: str, **kwargs: object) -> object:
        if calls is not None:
            calls.append({"pattern": pattern, **kwargs})
        if walker is not None:
            walker(kwargs)
        return _FakeRgapiRows(rows, complete=complete, stop_reason=stop_reason)

    module.rg = rg  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "rgapi", module)


class _FakeRgapiRows(list[str]):
    def __init__(self, rows: list[str], *, complete: bool, stop_reason: str | None) -> None:
        super().__init__(rows)
        self.complete = complete
        self.stop_reason = stop_reason


def _symlink_walker_canary(
    docs_dir: Path,
    outside: Path,
    open_outside_canary: Callable[[Path], None],
) -> Callable[[dict[str, object]], None]:
    def walk(kwargs: dict[str, object]) -> None:
        assert kwargs["root"] == docs_dir.resolve(strict=True)
        follow_links = kwargs["follow_links"]
        if follow_links is not False:
            open_outside_canary(outside)
        assert follow_links is False

    return walk


def _rgapi_index(data_dir: Path, nodes: list[WikiNode]) -> IndexManager:
    store = WikiStore(data_dir)
    index = IndexManager(data_dir / "mem.db")
    for node in nodes:
        index.update_record(store.write(node))
    return index
