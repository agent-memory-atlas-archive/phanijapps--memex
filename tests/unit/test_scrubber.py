"""T4: secret scrubber at every write boundary (AC-0009)."""

from pathlib import Path

import pytest

from memex import Memex
from memex.domain.models import WriteInput
from memex.domain.scrub import scrub
from memex.infrastructure.config import MemexConfig

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
        page = next((data_dir / "docs/entities").glob("*.md"))
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
