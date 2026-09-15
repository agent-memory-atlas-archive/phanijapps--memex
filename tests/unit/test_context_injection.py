from pathlib import Path

import pytest

from memex.application.context_injection import build_injection, format_context_block
from memex.application.memory import Memex
from memex.domain.models import WriteInput
from memex.infrastructure.config import MemexConfig
from memex.infrastructure.workspace_context import session_query


@pytest.fixture
def memex(data_dir: Path) -> Memex:
    instance = Memex(MemexConfig(data_dir=data_dir))
    instance.write(
        WriteInput(
            type="preference",
            title="User prefers ruff",
            body="Always lint Python with ruff, never flake8.",
            tags=["tooling"],
        )
    )
    return instance


def test_format_matches_spec_5_4(memex: Memex) -> None:
    result = memex.recall("lint")
    block = format_context_block(result)

    lines = block.splitlines()
    assert lines[0] == "=== memex MEMORY ==="
    assert lines[1] == '[Search: "lint"]'
    assert lines[-1] == "=== END memex MEMORY ==="
    assert lines[2] == "---"
    assert "1. User prefers ruff (preference) | importance:" in lines[3]
    assert lines[4].startswith("   File: ")
    assert "Tags: tooling" in lines[6]


def test_build_injection_empty_when_no_hits(memex: Memex) -> None:
    assert build_injection(memex, "kubernetes cluster policies") == ""


def test_build_injection_recalls(memex: Memex) -> None:
    block = build_injection(memex, "ruff")
    assert "ruff" in block


def test_session_query_best_effort(tmp_path: Path) -> None:
    # Not a git repo: directory name only, never raises.
    query = session_query(tmp_path)
    assert query == tmp_path.name
