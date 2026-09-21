"""T2: one description contract across every adapter and interchange path.

AC-0008 (Python/CLI/MCP parity), AC-0003 (backup/restore and export/import
round trips), AC-0009 (consolidation emission and validation).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from memex import cli
from memex.application.memory import Memex as MemexFacade
from memex.application.ports import LLMResponse
from memex.domain.models import ConsolidateInput, WikiNode, WriteInput
from memex.domain.operations import RecallResultDict
from memex.infrastructure.config import ConfigLoader, MemexConfig
from memex.infrastructure.consolidator import WikiConsolidator
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.link_manager import LinkManager
from memex.infrastructure.wiki_store import WikiStore
from memex.mcp_server import memex_recall, memex_write

VALID_DESCRIPTION = "signpost sentence for the adapter matrix"
OVER_512_BYTES = "x" * 513
LEGACY_HIT_KEYS = {
    "slug",
    "file_path",
    "title",
    "node_type",
    "importance",
    "score",
    "rank",
    "snippet",
    "snippet_source",
    "tags",
    "created",
    "updated",
    "last_access",
    "transcript_ref",
    "links",
    "status",
    "scope",
}


def _facade_write(data_dir: Path, description: str) -> str:
    memex = MemexFacade(MemexConfig(data_dir=data_dir))
    try:
        return memex.write(
            WriteInput(
                type="entity",
                title="Adapter target",
                body="plain body text",
                description=description,
            )
        ).slug
    finally:
        memex.close()


def _cli_write(data_dir: Path, description: str) -> int:
    return cli.main(
        [
            "--data-dir",
            str(data_dir),
            "write",
            "--type",
            "entity",
            "--title",
            "Adapter target",
            "--body",
            "plain body text",
            "--description",
            description,
        ]
    )


def _mcp_write(description: str) -> dict[str, object]:
    result = memex_write(
        type="entity",
        title="Adapter target",
        body="plain body text",
        scope="global",
        description=description,
    )
    return cast(dict[str, object], result)


@pytest.fixture
def mcp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from memex import mcp_server

    data_dir = tmp_path / "mcp-desc-home"
    monkeypatch.setenv("MEMEX_DATA_DIR", str(data_dir))
    mcp_server._reset()
    yield data_dir
    mcp_server._reset()


class TestAdapterParity:
    """AC-0008: same description contract in Python, CLI, and MCP."""

    def test_valid_description_accepted_everywhere(self, tmp_path: Path) -> None:
        _facade_write(tmp_path / "facade-home", VALID_DESCRIPTION)
        page = next((tmp_path / "facade-home/docs/global/entities").glob("*.md"))
        assert f'description: "{VALID_DESCRIPTION}"' in page.read_text(encoding="utf-8")

    def test_valid_description_accepted_by_cli(
        self, tmp_path: Path, capture: dict[str, str]
    ) -> None:
        assert _cli_write(tmp_path / "cli-home", VALID_DESCRIPTION) == 0
        payload = json.loads(capture["out"])
        page = Path(str(payload["file_path"]))
        assert f'description: "{VALID_DESCRIPTION}"' in page.read_text(encoding="utf-8")

    def test_valid_description_accepted_by_mcp(self, mcp_env: Path) -> None:
        result = _mcp_write(VALID_DESCRIPTION)
        assert "error" not in result
        page = Path(str(result["file_path"]))
        assert page.is_relative_to(mcp_env)
        assert f'description: "{VALID_DESCRIPTION}"' in page.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "invalid",
        [
            "two\nlines",
            OVER_512_BYTES,
            "control\x00char",
            "carriage\rreturn",
        ],
        ids=["newline", "over-512-bytes", "nul", "carriage-return"],
    )
    def test_invalid_description_rejected_by_facade(self, tmp_path: Path, invalid: str) -> None:
        with pytest.raises(ValueError):
            _facade_write(tmp_path / "facade-home", invalid)
        assert not list((tmp_path / "facade-home/docs/global/entities").glob("*.md"))

    @pytest.mark.parametrize(
        "invalid",
        [
            "two\nlines",
            OVER_512_BYTES,
            "control\x00char",
            "carriage\rreturn",
        ],
        ids=["newline", "over-512-bytes", "nul", "carriage-return"],
    )
    def test_invalid_description_rejected_by_cli(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], invalid: str
    ) -> None:
        data_dir = tmp_path / "cli-home"
        assert _cli_write(data_dir, invalid) == 1
        assert "description" in capsys.readouterr().err
        assert not list((data_dir / "docs/global/entities").glob("*.md"))

    @pytest.mark.parametrize(
        "invalid",
        [
            "two\nlines",
            OVER_512_BYTES,
            "control\x00char",
            "carriage\rreturn",
        ],
        ids=["newline", "over-512-bytes", "nul", "carriage-return"],
    )
    def test_invalid_description_rejected_by_mcp(self, mcp_env: Path, invalid: str) -> None:
        assert _mcp_write(invalid) == {"error": "invalid arguments for this operation"}
        assert not list((mcp_env / "docs/global/entities").glob("*.md"))

    def test_cli_recall_serializes_description_and_legacy_fields(
        self, tmp_path: Path, capture: dict[str, str]
    ) -> None:
        data_dir = tmp_path / "cli-home"
        assert _cli_write(data_dir, VALID_DESCRIPTION) == 0
        assert cli.main(["--data-dir", str(data_dir), "recall", "signpost"]) == 0
        hit = json.loads(capture["out"])["hits"][0]
        assert hit["description"] == VALID_DESCRIPTION
        assert set(hit) >= LEGACY_HIT_KEYS

    def test_mcp_recall_serializes_description_and_legacy_fields(self, mcp_env: Path) -> None:
        assert "error" not in _mcp_write(VALID_DESCRIPTION)
        result = cast(RecallResultDict, memex_recall("signpost"))
        assert result["hits"]
        hit = cast(dict[str, object], result["hits"][0])
        assert hit["description"] == VALID_DESCRIPTION
        assert set(hit) >= LEGACY_HIT_KEYS


class TestInterchangeRoundTrips:
    """AC-0003: description survives export/import and backup/restore."""

    def test_description_survives_export_import(self, tmp_path: Path) -> None:
        source = MemexFacade(MemexConfig(data_dir=tmp_path / "src-home"))
        source.write(
            WriteInput(
                type="entity",
                title="Roundtrip node",
                body="body without the signpost words",
                description="zephyr gradient tuning notes",
            )
        )
        export_path = tmp_path / "nodes.json"
        document = source.import_export.export(export_path)
        source.close()
        exported_nodes = cast(list[dict[str, object]], document["nodes"])
        assert exported_nodes[0]["description"] == "zephyr gradient tuning notes"
        assert "zephyr gradient tuning notes" in export_path.read_text(encoding="utf-8")

        target = MemexFacade(MemexConfig(data_dir=tmp_path / "dst-home"))
        report = target.import_export.import_file(export_path)
        assert report["imported"] == 1 and report["errors"] == []
        node = target.wiki_store.read("roundtrip-node")
        assert node is not None and node.description == "zephyr gradient tuning notes"
        result = target.recall("zephyr")
        assert result.hits[0].description == "zephyr gradient tuning notes"
        target.close()

    def test_description_survives_backup_restore(self, tmp_path: Path) -> None:
        import shutil

        data_dir = tmp_path / "backup-home"
        memex = MemexFacade(MemexConfig(data_dir=data_dir))
        memex.write(
            WriteInput(
                type="entity",
                title="Archived node",
                body="body without the signpost words",
                description="aurora scheduler settings",
            )
        )
        archive = tmp_path / "backup.tar.gz"
        memex.backup(archive)
        memex.close()

        shutil.rmtree(data_dir / "docs")
        for sidecar in data_dir.glob("mem.db-*"):
            sidecar.unlink()
        (data_dir / "mem.db").unlink()

        restored = MemexFacade(MemexConfig(data_dir=data_dir))
        report = restored.restore(archive)
        assert report.restored is True and report.index_rebuilt is True
        node = restored.wiki_store.read("archived-node")
        assert node is not None and node.description == "aurora scheduler settings"
        result = restored.recall("aurora")
        assert result.hits[0].description == "aurora scheduler settings"
        restored.close()


class TestConsolidationDescription:
    """AC-0009: consolidation may emit a validated one-sentence description."""

    @staticmethod
    def _node_payload(**overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": "entity",
            "title": "consolidated-fact",
            "body": "A durable fact from the episode.",
            "tags": ["fact"],
            "importance": 0.8,
        }
        payload.update(overrides)
        return payload

    @pytest.fixture
    def harness(self, data_dir: Path) -> tuple[WikiConsolidator, WikiStore, IndexManager, _FakeLLM]:
        store = WikiStore(data_dir)
        index = IndexManager(data_dir / "mem.db")
        links = LinkManager(index.connection, store.wiki_dir)
        config = ConfigLoader().load(data_dir=data_dir)
        fake = _FakeLLM()
        consolidator = WikiConsolidator(store, index, links, fake, config)
        store.write(
            WikiNode(
                type="episode",
                title="Session desc",
                body="The user prefers ruff over flake8.",
                id="",
                session_id="sess-desc",
            )
        )
        return consolidator, store, index, fake

    def test_emitted_description_is_persisted_and_indexed(
        self, harness: tuple[WikiConsolidator, WikiStore, IndexManager, _FakeLLM]
    ) -> None:
        consolidator, store, index, fake = harness
        fake.text = json.dumps([self._node_payload(description="one durable tooling fact")])

        consolidator.consolidate(ConsolidateInput(mode="full"))

        node = store.read("consolidated-fact")
        assert node is not None and node.description == "one durable tooling fact"
        row = index.get("consolidated-fact")
        assert row is not None and row["description"] == "one durable tooling fact"

    def test_omitted_description_still_writes_a_valid_page(
        self, harness: tuple[WikiConsolidator, WikiStore, IndexManager, _FakeLLM]
    ) -> None:
        consolidator, store, _, fake = harness
        fake.text = json.dumps([self._node_payload()])

        report = consolidator.consolidate(ConsolidateInput(mode="full"))

        assert len(report.nodes_created) == 1
        node = store.read("consolidated-fact")
        assert node is not None and node.description == ""

    @pytest.mark.parametrize(
        "invalid",
        [
            "line one\nline two",
            "y" * 600,
            17,
        ],
        ids=["newline", "over-512-bytes", "non-string"],
    )
    def test_invalid_description_skips_node_through_validation(
        self,
        harness: tuple[WikiConsolidator, WikiStore, IndexManager, _FakeLLM],
        invalid: object,
    ) -> None:
        consolidator, store, _, fake = harness
        fake.text = json.dumps(
            [
                self._node_payload(description=invalid),
                {**self._node_payload(title="healthy-sibling"), "description": "valid sibling"},
            ]
        )

        report = consolidator.consolidate(ConsolidateInput(mode="full"))

        assert [node.title for node in report.nodes_created] == ["healthy-sibling"]
        assert store.read("consolidated-fact") is None
        sibling = store.read("healthy-sibling")
        assert sibling is not None and sibling.description == "valid sibling"

    def test_prompt_requests_a_short_description(
        self, harness: tuple[WikiConsolidator, WikiStore, IndexManager, _FakeLLM]
    ) -> None:
        consolidator, _, _, fake = harness
        consolidator.consolidate(ConsolidateInput(mode="dry-run"))
        assert fake.last_prompt is not None
        assert '"description"' in fake.last_prompt


class _FakeLLM:
    def __init__(self, text: str = "[]") -> None:
        self.text = text
        self.last_prompt: str | None = None

    def complete(self, system: str, user: str, *, max_tokens: int) -> LLMResponse:
        self.last_prompt = user
        return LLMResponse(text=self.text, prompt_tokens=10, completion_tokens=10)
