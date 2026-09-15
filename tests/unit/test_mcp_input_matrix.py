"""Regression matrix for MCP tool input handling.

Each row pins one failure mode observed in the loose-typing review:
schema violations must die at the SDK layer with a field-precise
message, domain violations must return sanitized error data, and no
input may ever escape as UnexpectedToolError.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from memex import mcp_server


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    data_dir = tmp_path / "mcp-matrix-home"
    monkeypatch.setenv("MEMEX_DATA_DIR", str(data_dir))
    mcp_server._reset()
    yield data_dir
    mcp_server._reset()


def call(server: Any, tool: str, args: dict[str, Any]) -> tuple[str, Any]:
    """Invoke a tool; classify the outcome as 'result' or 'sdk-rejected'."""
    try:
        result = asyncio.run(server.call_tool(tool, args))
    except ToolError as exc:
        assert not isinstance(exc, UnexpectedToolError), (
            f"{tool} escaped to UnexpectedToolError: {exc.__cause__!r}"
        )
        return "sdk-rejected", str(exc)
    data = result.model_dump()
    return "result", data.get("structured_content")


@pytest.fixture
def server() -> Any:
    return mcp_server.build_server()


VALID_WRITE = {"type": "entity", "title": "Matrix node", "body": "b"}


class TestSchemaChannel:
    """Wrong shapes and out-of-contract values die at the SDK layer,
    with the offending field named in the message."""

    @pytest.mark.parametrize(
        ("args", "field"),
        [
            ({"type": "folder", "title": "x", "body": "y"}, "type"),
            ({"type": "entity", "title": "x", "body": "y", "importance": 2}, "importance"),
            ({"type": "entity", "title": "x", "body": "y", "importance": "high"}, "importance"),
            ({"type": "entity", "title": "x", "body": "y", "tags": "tool"}, "tags"),
            ({"type": "entity", "title": "x"}, "body"),
        ],
    )
    def test_write_rejections_name_the_field(
        self, server: Any, args: dict[str, Any], field: str
    ) -> None:
        channel, message = call(server, "memex_write", args)
        assert channel == "sdk-rejected"
        assert field in message

    def test_recall_top_k_bounds(self, server: Any) -> None:
        for bad in (0, 101, 999):
            channel, message = call(server, "memex_recall", {"query": "x", "top_k": bad})
            assert channel == "sdk-rejected", message
            assert "top_k" in message

    def test_recall_node_type_enum(self, server: Any) -> None:
        channel, message = call(server, "memex_recall", {"query": "x", "node_type": "folder"})
        assert channel == "sdk-rejected"
        assert "node_type" in message

    def test_forget_mode_enum(self, server: Any) -> None:
        channel, message = call(server, "memex_forget", {"slug": "x", "mode": "explode"})
        assert channel == "sdk-rejected"
        assert "mode" in message

    def test_ingest_bad_turn_role_rejected_by_schema(self, server: Any) -> None:
        channel, message = call(
            server,
            "memex_ingest_transcript",
            {"session_id": "s", "turns": [{"role": "system", "content": "x", "turn": 1}]},
        )
        assert channel == "sdk-rejected"
        assert "role" in message

    def test_ingest_turn_missing_required_field(self, server: Any) -> None:
        channel, message = call(
            server,
            "memex_ingest_transcript",
            {"session_id": "s", "turns": [{"role": "user", "content": "x"}]},
        )
        assert channel == "sdk-rejected"
        assert "turn" in message


class TestDomainChannel:
    """Valid shapes with invalid semantics return sanitized error data."""

    def test_write_ok(self, server: Any) -> None:
        channel, payload = call(server, "memex_write", VALID_WRITE)
        assert channel == "result"
        assert payload["slug"] == "matrix-node"

    def test_recall_empty_query(self, server: Any) -> None:
        channel, payload = call(server, "memex_recall", {"query": "???"})
        assert channel == "result"
        assert payload == {"error": "invalid arguments for this operation"}

    def test_forget_unknown_slug(self, server: Any) -> None:
        channel, payload = call(server, "memex_forget", {"slug": "ghost"})
        assert channel == "result"
        assert payload == {"error": "memory node not found"}


class TestTheOriginalBug:
    """A turn without ts used to crash with TypeError through every layer."""

    def test_turn_without_ts_succeeds(self, server: Any) -> None:
        channel, payload = call(
            server,
            "memex_ingest_transcript",
            {"session_id": "sess-nots", "turns": [{"role": "user", "content": "hi", "turn": 1}]},
        )
        assert channel == "result"
        assert payload["episode_node"] == "sess-nots"
        assert payload["turn_count"] == 1

    def test_cli_accepts_ts_less_jsonl(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import json

        from memex import cli

        turns = tmp_path / "turns.jsonl"
        turns.write_text(json.dumps({"role": "user", "content": "no ts", "turn": 1}) + "\n")
        code = cli.main(
            [
                "--data-dir",
                str(tmp_path / "cli-home"),
                "ingest-transcript",
                "--session-id",
                "sess-cli-nots",
                "--turns-file",
                str(turns),
            ]
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["turn_count"] == 1


class TestWireSchemas:
    """The advertised schemas must carry the domain enums and bounds."""

    @staticmethod
    def schemas(server: Any) -> dict[str, Any]:
        tools = asyncio.run(server.list_tools())

        def dump(schema: Any) -> dict[str, Any]:
            data: dict[str, Any] = schema.model_dump() if hasattr(schema, "model_dump") else schema
            return data

        return {
            tool.name: {"input": dump(tool.input_schema), "output": dump(tool.output_schema)}
            for tool in tools
        }

    def test_write_input_schema(self, server: Any) -> None:
        props = self.schemas(server)["memex_write"]["input"]["properties"]
        assert props["type"]["enum"] == ["entity", "preference", "procedure", "summary", "episode"]
        assert props["importance"]["minimum"] == 0
        assert props["importance"]["maximum"] == 1

    def test_recall_input_schema(self, server: Any) -> None:
        props = self.schemas(server)["memex_recall"]["input"]["properties"]
        assert props["top_k"]["minimum"] == 1
        assert props["top_k"]["maximum"] == 100

    def test_ingest_turns_have_typed_shape(self, server: Any) -> None:
        schema = self.schemas(server)["memex_ingest_transcript"]["input"]
        assert schema["properties"]["turns"]["items"]["$ref"] == "#/$defs/TurnDict"
        turn = schema["$defs"]["TurnDict"]
        assert set(turn["properties"]) == {
            "role",
            "content",
            "turn",
            "ts",
            "tool_name",
            "result",
            "query",
            "token_usage",
        }
        assert turn["properties"]["role"]["enum"] == ["user", "agent", "tool"]
        assert set(turn["required"]) == {"role", "content", "turn"}
        assert "ts" not in turn["required"]

    def test_output_schemas_are_not_vacuous(self, server: Any) -> None:
        schemas = self.schemas(server)
        write_out = schemas["memex_write"]["output"]
        assert {"slug", "file_path", "error"} <= set(write_out["properties"])
        recall_out = schemas["memex_recall"]["output"]
        assert {"hits", "total_indexed", "error"} <= set(recall_out["properties"])

    def test_export_and_import_output_schemas(self, server: Any) -> None:
        schemas = self.schemas(server)
        assert "nodes" in schemas["memex_export"]["output"]["properties"]
        assert {"imported", "errors"} <= set(schemas["memex_import"]["output"]["properties"])
