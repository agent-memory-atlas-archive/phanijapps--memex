import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from memex import mcp_server
from memex.mcp_server import (
    memex_export,
    memex_forget,
    memex_import,
    memex_ingest_transcript,
    memex_provenance,
    memex_recall,
    memex_write,
)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    data_dir = tmp_path / "mcp-home"
    monkeypatch.setenv("MEMEX_DATA_DIR", str(data_dir))
    mcp_server._reset()
    yield data_dir
    mcp_server._reset()


def test_all_eight_tools_registered() -> None:
    import asyncio

    server = mcp_server.build_server()
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    expected = {
        "memex_write",
        "memex_recall",
        "memex_consolidate",
        "memex_forget",
        "memex_ingest_transcript",
        "memex_provenance",
        "memex_export",
        "memex_import",
    }
    assert names == expected


EXPECTED_HINTS = {
    "memex_write": {"read_only": False, "destructive": False, "idempotent": True},
    "memex_recall": {"read_only": True, "destructive": False, "idempotent": False},
    "memex_consolidate": {"read_only": False, "destructive": False, "idempotent": False},
    "memex_forget": {"read_only": False, "destructive": True, "idempotent": False},
    "memex_ingest_transcript": {"read_only": False, "destructive": False, "idempotent": False},
    "memex_provenance": {"read_only": True, "destructive": False, "idempotent": True},
    "memex_export": {"read_only": True, "destructive": False, "idempotent": True},
    "memex_import": {"read_only": False, "destructive": False, "idempotent": True},
}


def test_wire_descriptions_are_call_contracts() -> None:
    """The description an agent client sees must be a usable contract:
    non-trivial, dedented, and explicit about the error-result shape."""
    import asyncio

    server = mcp_server.build_server()
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert set(tools) == set(EXPECTED_HINTS)

    for name, tool in tools.items():
        assert len(tool.description or "") >= 250, f"{name}: description too light"
        assert '"error"' in tool.description, f"{name}: error contract not documented"
        assert "    " not in tool.description, f"{name}: indentation leaked onto the wire"
        assert "Args:" not in tool.description, f"{name}: maintainer pyguide header on wire"
        assert (tool.title or "").startswith("Memex:"), f"{name}: missing display title"

        annotations = tool.annotations
        assert annotations is not None, f"{name}: no annotations"
        expected = EXPECTED_HINTS[name]
        assert annotations.read_only_hint == expected["read_only"], name
        assert annotations.destructive_hint == expected["destructive"], name
        assert annotations.idempotent_hint == expected["idempotent"], name
        assert annotations.open_world_hint is False, name


def test_ingest_description_documents_turn_format() -> None:
    """The one tool whose input shape models cannot guess needs an example."""
    from memex.domain.operations import OPERATION_DESCRIPTIONS

    description = OPERATION_DESCRIPTIONS["memex_ingest_transcript"]
    assert '"role"' in description
    assert '"turn"' in description


def test_wire_registry_matches_registered_tools() -> None:
    """Drift guard: every tool has a wire entry, and no orphans."""
    import asyncio

    from memex.domain.operations import OPERATION_DESCRIPTIONS

    server = mcp_server.build_server()
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert set(OPERATION_DESCRIPTIONS) == names


def test_tool_docstrings_follow_pyguide() -> None:
    """Source docstrings are maintainer docs (pyguide), not wire text."""
    functions = [
        mcp_server.memex_write,
        mcp_server.memex_recall,
        mcp_server.memex_consolidate,
        mcp_server.memex_forget,
        mcp_server.memex_ingest_transcript,
        mcp_server.memex_provenance,
        mcp_server.memex_export,
        mcp_server.memex_import,
    ]
    for fn in functions:
        assert fn.__doc__ and "Returns:" in fn.__doc__, fn.__name__
        assert "When to use:" not in fn.__doc__, f"{fn.__name__}: wire text leaked into source"
        if fn.__name__ != "memex_export":  # zero-arg function: an Args section would be filler
            assert "Args:" in fn.__doc__, fn.__name__


def test_write_recall_forget_flow() -> None:
    written = memex_write(type="entity", title="MCP entity", body="via mcp tool")
    assert written["slug"] == "mcp-entity"

    recalled = memex_recall("mcp")
    assert [hit["slug"] for hit in recalled["hits"]] == ["mcp-entity"]

    forgotten = memex_forget("mcp-entity")
    assert forgotten["forgotten"] is True


def test_errors_are_sanitized() -> None:
    from typing import cast

    from memex.domain.models import NodeType

    assert memex_forget("totally-unknown-slug") == {"error": "memory node not found"}
    assert memex_write(type=cast(NodeType, "bogus"), title="x", body="y") == {
        "error": "invalid arguments for this operation"
    }
    assert memex_recall("???") == {"error": "invalid arguments for this operation"}


def test_transcript_and_provenance_tools() -> None:
    report = memex_ingest_transcript(
        session_id="sess-mcp",
        turns=[{"role": "user", "content": "hello", "ts": "2026-09-15T10:00:00Z", "turn": 1}],
    )
    assert report["episode_node"] == "sess-mcp"

    provenance = memex_provenance("sess-mcp")
    assert provenance["confidence"] == "direct"
    assert provenance["transcript_files"][0].endswith("sess-mcp.jsonl")

    assert memex_provenance("ghost") == {"error": "memory node not found"}


def test_export_import_tools() -> None:
    memex_write(type="entity", title="Export", body="b")
    exported = memex_export()
    assert exported["version"] == "1.0"
    assert len(exported["nodes"]) == 1

    result = memex_import(exported["nodes"])
    assert result["imported"] == 1


def test_tool_exception_fallbacks_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Internal failures surface as sanitized errors, never raw traces."""
    import memex.mcp_server as srv

    class _Boom:
        def __getattr__(self, name: str) -> object:
            raise RuntimeError("secret path /root/x in store")

    monkeypatch.setattr(srv, "_get_memex", lambda: _Boom())

    assert "error" in memex_recall("anything")
    assert "error" in memex_export()
    assert "error" in memex_import([])
    assert "error" in srv.memex_consolidate(mode="full")
    assert "error" in srv.memex_ingest_transcript(
        session_id="s", turns=[{"role": "user", "content": "hi", "turn": 1}]
    )
    assert "error" in srv.memex_provenance("ghost")
    # The sanitized error must not leak the internal exception message
    assert "secret path" not in json.dumps(srv.memex_export())
