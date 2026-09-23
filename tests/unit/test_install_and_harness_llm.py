"""Seamless install + harness-as-LLM-provider."""

import json
import stat
from pathlib import Path

import pytest

from memex import cli
from memex.infrastructure.config import ConfigLoader, LLMConfig
from memex.infrastructure.harness.installer import default_marketplace, init_memex
from memex.infrastructure.llm_clients import HarnessLLMClient, client_from_config

MARKETPLACE = Path(__file__).parent.parent.parent / "src/memex/marketplace"


class TestMarketplaceResolution:
    """Assets ship inside the package, so one layout serves every install."""

    def test_explicit_wins(self, tmp_path: Path) -> None:
        explicit = tmp_path / "my-market"
        explicit.mkdir()
        assert default_marketplace(explicit) == explicit

    def test_resolves_inside_the_package(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import memex.infrastructure.harness.installer as installer

        package = tmp_path / "site-packages/memex"
        (package / "infrastructure/harness").mkdir(parents=True)
        (package / "marketplace").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            installer, "__file__", str(package / "infrastructure/harness/installer.py")
        )
        assert default_marketplace(None) == package / "marketplace"

    def test_missing_assets_name_the_recovery(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import memex.infrastructure.harness.installer as installer

        package = tmp_path / "site-packages/memex"
        (package / "infrastructure/harness").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            installer, "__file__", str(package / "infrastructure/harness/installer.py")
        )
        with pytest.raises(FileNotFoundError, match="Reinstall from source"):
            default_marketplace(None)

    def test_a_checkout_cwd_does_not_shadow_the_installed_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Installer assets must match the installed version, not the cwd."""
        import memex.infrastructure.harness.installer as installer

        package = tmp_path / "site-packages/memex"
        (package / "infrastructure/harness").mkdir(parents=True)
        (package / "marketplace").mkdir()
        checkout = tmp_path / "checkout"
        (checkout / "marketplace").mkdir(parents=True)
        monkeypatch.chdir(checkout)
        monkeypatch.setattr(
            installer, "__file__", str(package / "infrastructure/harness/installer.py")
        )
        assert default_marketplace(None) == package / "marketplace"


class TestInitMemex:
    def test_creates_tree_and_toml(self, tmp_path: Path) -> None:
        init_memex(tmp_path)
        assert (tmp_path / "docs").is_dir()
        assert (tmp_path / "transcripts").is_dir()
        assert (tmp_path / "memex.toml").exists()
        assert '# provider = "openai"' in (tmp_path / "memex.toml").read_text()

    def test_harness_provider_active(self, tmp_path: Path) -> None:
        init_memex(tmp_path, consolidation_provider="codex")
        config = ConfigLoader().load(tmp_path / "memex.toml")
        effective = config.consolidation_llm()
        assert effective.provider == "codex"

    def test_existing_toml_untouched(self, tmp_path: Path) -> None:
        (tmp_path / "memex.toml").write_text('[llm]\nmodel = "keep-me"\n')
        report = init_memex(tmp_path, consolidation_provider="pi")
        assert "left untouched" in report.notes[0]
        assert "keep-me" in (tmp_path / "memex.toml").read_text()


class TestInstallCommand:
    def test_custom_initializes_memex_only(
        self, tmp_path: Path, capture: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data_dir = tmp_path / "memex-home"
        home = tmp_path / "home"
        project = tmp_path / "proj"
        project.mkdir()
        monkeypatch.setenv("MEMEX_DATA_DIR", str(data_dir))
        for var in ("MEMEX_CONSOLIDATE_PROVIDER", "MEMEX_LLM_PROVIDER"):
            monkeypatch.delenv(var, raising=False)

        code = cli.main(["install", "custom", "--home", str(home)])
        assert code == 0
        payload = json.loads(capture["out"])
        assert payload["harness"] == "custom"
        assert (data_dir / "memex.toml").exists()
        # Custom touches no harness config.
        assert not (home / ".claude").exists()
        assert not (home / ".codex").exists()

    def test_harness_install_provisions_consolidation(
        self, tmp_path: Path, capture: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data_dir = tmp_path / "memex-home"
        home = tmp_path / "home"
        monkeypatch.setenv("MEMEX_DATA_DIR", str(data_dir))
        for var in ("MEMEX_CONSOLIDATE_PROVIDER", "MEMEX_LLM_PROVIDER"):
            monkeypatch.delenv(var, raising=False)

        code = cli.main(["install", "pi", "--home", str(home), "--from", str(MARKETPLACE)])
        assert code == 0
        toml = (data_dir / "memex.toml").read_text()
        assert 'provider = "pi"' in toml
        assert (home / ".pi/agent/extensions/memex.ts").exists()

    def test_interactive_picker(
        self, tmp_path: Path, capture: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data_dir = tmp_path / "memex-home"
        home = tmp_path / "home"
        monkeypatch.setenv("MEMEX_DATA_DIR", str(data_dir))
        monkeypatch.setattr("builtins.input", lambda _prompt: "5")
        code = cli.main(["install", "--home", str(home)])
        assert code == 0
        assert json.loads(capture["out"])["harness"] == "custom"
        assert (data_dir / "memex.toml").exists()

    def test_invalid_choice(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("builtins.input", lambda _prompt: "9")
        code = cli.main(["install", "--home", str(tmp_path)])
        assert code == 1
        assert "invalid choice" in capsys.readouterr().err


def _fake_cli(tmp_path: Path, stdout: str, returncode: int = 0) -> str:
    script = tmp_path / "fake-cli"
    script.write_text(
        "#!/bin/sh\ncat <<'MEMEX_EOF'\n" + stdout + "\nMEMEX_EOF\n" + f"exit {returncode}\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


class TestHarnessLLMClient:
    def test_complete_uses_cli_stdout(self, tmp_path: Path) -> None:
        client = HarnessLLMClient.__new__(HarnessLLMClient)
        client._argv = [_fake_cli(tmp_path, '[{"type": "entity"}]')]
        client._timeout = 10
        response = client.complete("system", "user", max_tokens=100)
        assert response.text == '[{"type": "entity"}]'
        assert response.prompt_tokens == 0

    def test_nonzero_exit_raises(self, tmp_path: Path) -> None:
        from memex.domain.errors import LLMError

        client = HarnessLLMClient.__new__(HarnessLLMClient)
        client._argv = [_fake_cli(tmp_path, "boom", returncode=1)]
        client._timeout = 10
        with pytest.raises(LLMError, match="exit 1"):
            client.complete("s", "u", max_tokens=10)

    def test_dispatch_by_provider(self) -> None:
        assert isinstance(
            client_from_config(LLMConfig(provider="codex", model="mini")), HarnessLLMClient
        )
        assert not isinstance(client_from_config(LLMConfig(provider="openai")), HarnessLLMClient)

    def test_unknown_harness_rejected(self) -> None:
        from memex.domain.errors import LLMError

        with pytest.raises(LLMError, match="unknown harness"):
            HarnessLLMClient("vscode")

    def test_model_flag_appended(self) -> None:
        client = HarnessLLMClient("claude", model="haiku")
        assert client._argv[-2:] == ["--model", "haiku"]
