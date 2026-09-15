"""Shared fixtures: isolated data directories per test."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "memex-home"


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Capture print() output so JSON stdout can be asserted."""
    holder: dict[str, str] = {}

    def fake_print(*values: object, **kwargs: object) -> None:
        holder["out"] = "".join(str(v) for v in values)

    monkeypatch.setattr("builtins.print", fake_print)
    return holder


@pytest.fixture(autouse=True)
def _isolated_memex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with a clean memex environment.

    Developer shells frequently carry MEMEX_* exports from manual runs;
    without this, config tests silently read the developer's real
    ~/.memex instead of isolated fixtures.
    """
    for var in (
        "MEMEX_DATA_DIR",
        "MEMEX_API_KEY",
        "MEMEX_LLM_PROVIDER",
        "MEMEX_LLM_MODEL",
        "MEMEX_CONSOLIDATE_PROVIDER",
        "MEMEX_CONSOLIDATE_MODEL",
        "MEMEX_CONSOLIDATE_API_KEY",
        "MEMEX_AUTO_CONSOLIDATE",
    ):
        monkeypatch.delenv(var, raising=False)
