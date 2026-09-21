"""T4: secret scrubber at every write boundary (AC-0009)."""

import io
import json
from pathlib import Path

import pytest

from memex import Memex
from memex.domain.models import ConsolidateInput, WikiNode, WriteInput
from memex.domain.scrub import scrub
from memex.infrastructure.config import ConfigLoader, MemexConfig
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.link_manager import LinkManager
from memex.infrastructure.wiki_store import WikiStore

SECRETS = [
    "sk-proj-abcdefghijklmnopqrstuv0123456789abcdefghijklmnopqrstuv",  # OpenAI
    "sk-ant-api03-abcdefghijklmnopqrstuv0123456789abcdefghijklmnopqrstu",  # Anthropic
    "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghij",  # GitHub PAT
    "AKIAIOSFODNN7EXAMPLE",  # AWS key id
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc123def456",  # JWT
    "postgres://user:secret@localhost:5432/db",  # DB URL
]

CLEAN = ["The deploy uses blue-green", "remember ruff over flake8", "port 8080"]


class TestScrubFunction:
    @pytest.mark.parametrize("secret", SECRETS)
    def test_each_secret_redacted(self, secret: str) -> None:
        clean, kinds = scrub(f"config: {secret} end")
        assert secret not in clean
        assert kinds and all(kind for kind in kinds)
        assert "[REDACTED:" in clean

    @pytest.mark.parametrize("text", CLEAN)
    def test_clean_text_untouched(self, text: str) -> None:
        clean, kinds = scrub(text)
        assert clean == text
        assert kinds == []

    def test_pem_block(self) -> None:
        pem = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----"
        clean, _ = scrub(f"key: {pem}")
        assert "MIIEvQIBADANBg" not in clean
        assert "[REDACTED:" in clean


class TestBoundaryIntegration:
    def test_cli_write_redacts(self, data_dir: Path, capture: dict[str, str]) -> None:
        from memex import cli

        secret = SECRETS[0]
        code = cli.main(
            [
                "--data-dir",
                str(data_dir),
                "write",
                "--type",
                "entity",
                "--title",
                "Leaky",
                "--body",
                f"key was {secret}",
            ]
        )
        assert code == 0
        page = next((data_dir / "docs/global/entities").glob("*.md"))
        assert secret not in page.read_text(encoding="utf-8")
        assert "[REDACTED:" in page.read_text(encoding="utf-8")

    def test_facade_write_redacts(self, data_dir: Path) -> None:
        memex = Memex(MemexConfig(data_dir=data_dir))
        stored = memex.write(WriteInput(type="entity", title="MCP leak", body=f"tok {SECRETS[2]}"))
        read_back = memex.wiki_store.read(stored.slug)
        assert read_back is not None
        assert SECRETS[2] not in read_back.body
        assert "[REDACTED:" in read_back.body
        memex.close()

    def test_fs_grep_canary(self, data_dir: Path) -> None:
        memex = Memex(MemexConfig(data_dir=data_dir))
        for i, secret in enumerate(SECRETS):
            memex.write(WriteInput(type="entity", title=f"Canary {i}", body=f"s={secret}"))
        memex.close()
        for path in data_dir.rglob("*"):
            if path.is_file():
                content = path.read_text(encoding="utf-8", errors="replace")
                for secret in SECRETS:
                    assert secret not in content, f"{secret} leaked into {path}"


DESCRIPTION_SECRET = SECRETS[0]


class TestDescriptionScrub:
    """AC-0013: secret-shaped descriptions are scrubbed at every persisting
    write boundary before any file, index, backup, or export can hold them."""

    def test_facade_scrubs_description(self, data_dir: Path) -> None:
        memex = Memex(MemexConfig(data_dir=data_dir))
        stored = memex.write(
            WriteInput(
                type="entity",
                title="Desc leak",
                body="clean body",
                description=f"key was {DESCRIPTION_SECRET}",
            )
        )
        read_back = memex.wiki_store.read(stored.slug)
        assert read_back is not None
        assert DESCRIPTION_SECRET not in read_back.description
        assert "[REDACTED:openai_key]" in read_back.description
        memex.close()

    def test_cli_scrubs_description(self, data_dir: Path) -> None:
        from memex import cli

        code = cli.main(
            [
                "--data-dir",
                str(data_dir),
                "write",
                "--type",
                "entity",
                "--title",
                "Desc leak",
                "--body",
                "clean body",
                "--description",
                f"key was {DESCRIPTION_SECRET}",
            ]
        )
        assert code == 0
        page = next((data_dir / "docs/global/entities").glob("*.md"))
        text = page.read_text(encoding="utf-8")
        assert DESCRIPTION_SECRET not in text
        assert "[REDACTED:openai_key]" in text

    def test_mcp_scrubs_description(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from memex import mcp_server
        from memex.mcp_server import memex_write

        monkeypatch.setenv("MEMEX_DATA_DIR", str(tmp_path / "mcp-scrub-home"))
        mcp_server._reset()
        try:
            result = memex_write(
                type="entity",
                title="MCP desc leak",
                body="clean body",
                scope="global",
                description=f"tok {DESCRIPTION_SECRET}",
            )
        finally:
            mcp_server._reset()
        assert "error" not in result
        page = Path(str(result["file_path"]))
        text = page.read_text(encoding="utf-8")
        assert DESCRIPTION_SECRET not in text
        assert "[REDACTED:openai_key]" in text

    def test_consolidation_scrubs_description(self, data_dir: Path) -> None:
        import json

        from memex.application.ports import LLMResponse
        from memex.infrastructure.consolidator import WikiConsolidator

        store = WikiStore(data_dir)
        index = IndexManager(data_dir / "mem.db")
        links = LinkManager(index.connection, store.wiki_dir)
        store.write(
            WikiNode(
                type="episode",
                title="Session scrub",
                body="The user prefers ruff over flake8.",
                id="",
                session_id="sess-scrub",
            )
        )

        class SecretLLM:
            def complete(self, system: str, user: str, *, max_tokens: int) -> LLMResponse:
                return LLMResponse(
                    text=json.dumps(
                        [
                            {
                                "type": "entity",
                                "title": "Scrubbed fact",
                                "body": "clean consolidated body",
                                "description": f"deploy token {DESCRIPTION_SECRET}",
                                "importance": 0.8,
                            }
                        ]
                    ),
                    prompt_tokens=1,
                    completion_tokens=1,
                )

        consolidator = WikiConsolidator(
            store, index, links, SecretLLM(), ConfigLoader().load(data_dir=data_dir)
        )
        consolidator.consolidate(ConsolidateInput(mode="full"))
        node = store.read("scrubbed-fact")
        assert node is not None
        assert DESCRIPTION_SECRET not in node.description
        assert "[REDACTED:openai_key]" in node.description

    def test_scrubbed_description_never_reaches_derived_outputs(
        self, data_dir: Path, tmp_path: Path
    ) -> None:
        import tarfile

        memex = Memex(MemexConfig(data_dir=data_dir))
        memex.write(
            WriteInput(
                type="entity",
                title="Outputs leak",
                body="clean body",
                description=f"canary {DESCRIPTION_SECRET}",
            )
        )

        result = memex.recall("canary")
        assert result.hits
        for hit in result.hits:
            assert DESCRIPTION_SECRET not in hit.description
            assert DESCRIPTION_SECRET not in hit.snippet

        export_path = tmp_path / "nodes.json"
        document = memex.import_export.export(export_path)
        assert DESCRIPTION_SECRET not in json.dumps(document)
        assert DESCRIPTION_SECRET not in export_path.read_text(encoding="utf-8")

        archive = tmp_path / "backup.tar.gz"
        memex.backup(archive)
        memex.close()
        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            assert members
            for member in members:
                if not member.isfile():
                    continue
                payload = (tar.extractfile(member) or io.BytesIO()).read()
                assert DESCRIPTION_SECRET not in payload.decode("utf-8", errors="replace"), (
                    f"{DESCRIPTION_SECRET} leaked into archive member {member.name}"
                )

        for path in data_dir.rglob("*"):
            if path.is_file():
                content = path.read_text(encoding="utf-8", errors="replace")
                assert DESCRIPTION_SECRET not in content, f"leaked into {path}"

    def test_scrub_warning_logs_categories_only(
        self, data_dir: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import logging

        memex = Memex(MemexConfig(data_dir=data_dir))
        monkeypatch.setattr(logging.getLogger("memex"), "propagate", True)
        with caplog.at_level(logging.WARNING, logger="memex"):
            memex.write(
                WriteInput(
                    type="entity",
                    title="Log check",
                    body="clean body",
                    description=f"tok {DESCRIPTION_SECRET}",
                )
            )
        memex.close()
        warning = caplog.records[-1].getMessage()
        assert "openai_key" in warning
        assert DESCRIPTION_SECRET not in warning
