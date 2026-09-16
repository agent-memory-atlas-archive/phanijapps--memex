"""Opt-in LLM integration: one real consolidation via local ollama.

Gated by MEMEX_TEST_OLLAMA=1 and model reachability; skipped otherwise.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from memex import Memex
from memex.domain.models import ConsolidateInput, WikiNode
from memex.infrastructure.config import MemexConfig

pytestmark = pytest.mark.ollama

MODEL = "glm-5.3-flash:cloud"
HOST, PORT = "localhost", 11434


def _ollama_up() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture
def memex(data_dir: Path) -> Memex:
    import dataclasses

    base = MemexConfig(data_dir=data_dir)
    llm = dataclasses.replace(
        base.llm,
        provider="ollama",
        model=MODEL,
        api_base="http://localhost:11434/v1",
    )
    return Memex(dataclasses.replace(base, llm=llm))


def test_real_consolidation_roundtrip(memex: Memex) -> None:
    if os.environ.get("MEMEX_TEST_OLLAMA") != "1" or not _ollama_up():
        pytest.skip("MEMEX_TEST_OLLAMA not set or ollama unreachable")

    episode = WikiNode(
        type="episode",
        title="Session integration",
        body="The user prefers uv for Python tooling and ruff for linting.",
        id="",
        session_id="sess-itest",
    )
    stored = memex.wiki_store.write(episode)
    memex.index_manager.update_record(stored)

    report = memex.consolidate(ConsolidateInput(mode="full"))
    assert report.llm_calls == 1
    # A valid node parsed and stored (quality is FakeLLM territory; this
    # covers provider plumbing end-to-end).
    assert report.nodes_created or report.nodes_updated or report.episodes_processed == 1
    memex.close()
