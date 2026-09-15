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
