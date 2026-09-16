"""Viz dashboard route tests (T1 + T2)."""

from __future__ import annotations

import http.client
import json
import threading
import time
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from memex import Memex
from memex.domain.models import WikiNode, WriteInput
from memex.infrastructure.config import MemexConfig as Config
from memex.infrastructure.viz import VizHandler


@pytest.fixture(scope="module")
def viz_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[int, Path]]:
    """Seed a store and start a real HTTP server for the module."""
    data_dir = tmp_path_factory.mktemp("viz")
    memex = Memex(Config(data_dir=data_dir))
    memex.write(WriteInput(type="entity", title="Alpha entity", body="alpha search content"))
    memex.write(WriteInput(type="preference", title="Beta pref", body="beta preference body"))
    node = WikiNode(
        type="entity",
        title="Gamma pending",
        body="gamma content",
        id="g1",
        status="pending",
        source="consolidation",
        harness="codex",
    )
    stored = memex.wiki_store.write(node)
    memex.index_manager.update_record(stored)
    # Seed a transcript with token usage
    meta = {
        "session_id": "sess-viz",
        "started_at": "2026-09-16T10:00:00Z",
        "turn_count": 2,
        "token_usage": {"total_tokens": 1234},
    }
    (data_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    (data_dir / "transcripts/sess-viz.meta.json").write_text(json.dumps(meta))
    # Seed an episode page for the sessions list
    ep = WikiNode(
        type="episode",
        title="Session sess-viz",
        body="test session",
        id="e1",
        session_id="sess-viz",
        transcript_ref="transcripts/sess-viz.jsonl",
    )
    memex.wiki_store.write(ep)
    memex.index_manager.update_record(ep)
    memex.close()

    class BoundVizHandler(VizHandler):
        memex: Memex | None = Memex(Config(data_dir=data_dir))

    server = ThreadingHTTPServer(("127.0.0.1", 0), BoundVizHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    yield port, data_dir
    server.shutdown()
    server.server_close()


def _get(port: int, path: str) -> tuple[int, str]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read().decode()
    conn.close()
    return resp.status, body


class TestShellPage:
    def test_shell_renders(self, viz_server: tuple[int, Path]) -> None:
        port, _ = viz_server
        code, body = _get(port, "/")
        assert code == 200
        assert "memex" in body
        assert 'src="/htmx.js"' in body
        assert 'href="/style.css"' in body


class TestHTMXServed:  # AC-0007
    def test_real_htmx(self, viz_server: tuple[int, Path]) -> None:
        port, _ = viz_server
        code, body = _get(port, "/htmx.js")
        assert code == 200
        assert len(body) > 10000
        assert "htmx" in body


class TestOverview:  # AC-0001
    def test_stat_cards(self, viz_server: tuple[int, Path]) -> None:
        port, _ = viz_server
        code, body = _get(port, "/overview")
        assert code == 200
        assert "memory pages" in body
        assert "pending approval" in body


class TestPagesFilter:  # AC-0002
    def test_entity_filter(self, viz_server: tuple[int, Path]) -> None:
        port, _ = viz_server
        code, body = _get(port, "/pages?type=entity")
        assert code == 200
        assert "Alpha entity" in body
        assert "Beta pref" not in body

    def test_preference_filter(self, viz_server: tuple[int, Path]) -> None:
        port, _ = viz_server
        code, body = _get(port, "/pages?type=preference")
        assert code == 200
        assert "Beta pref" in body
        assert "Alpha entity" not in body


class TestSearch:  # AC-0003
    def test_search_returns_results(self, viz_server: tuple[int, Path]) -> None:
        port, _ = viz_server
        code, body = _get(port, "/search?q=alpha")
        assert code == 200
        assert "Alpha entity" in body


class TestHealth:  # AC-0004
    def test_health_fragment(self, viz_server: tuple[int, Path]) -> None:
        port, _ = viz_server
        code, body = _get(port, "/health")
        assert code == 200
        assert "Index:" in body
        assert "Pending:" in body


class TestSessions:  # AC-0005
    def test_sessions_table(self, viz_server: tuple[int, Path]) -> None:
        port, _ = viz_server
        code, body = _get(port, "/sessions")
        assert code == 200
        assert "sess-viz" in body
        assert "<table" in body


class TestTokens:  # AC-0006
    def test_token_chart(self, viz_server: tuple[int, Path]) -> None:
        port, _ = viz_server
        code, body = _get(port, "/tokens")
        assert code == 200
        assert "<svg" in body
        assert "<rect" in body
        assert "1,234" in body
