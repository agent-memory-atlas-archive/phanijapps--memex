"""First-class consolidation: [consolidation] model overrides + hook wiring."""

import json
from pathlib import Path

import pytest

from memex import cli
from memex.application.memory import Memex
from memex.domain.models import WriteInput
from memex.infrastructure.config import ConfigLoader, MemexConfig

FIXTURES = Path(__file__).parent.parent / "fixtures"


def write_config(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestConsolidationConfig:
    def test_defaults_inherit_llm(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in (
            "MEMEX_API_KEY",
            "MEMEX_LLM_PROVIDER",
            "MEMEX_CONSOLIDATE_PROVIDER",
            "MEMEX_CONSOLIDATE_MODEL",
            "MEMEX_CONSOLIDATE_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        config = ConfigLoader().load()
        effective = config.consolidation_llm()

        assert effective.provider == config.llm.provider
        assert effective.model == config.llm.model
        assert effective.api_key == config.llm.api_key

    def test_overrides_and_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in (
            "MEMEX_API_KEY",
            "MEMEX_LLM_PROVIDER",
            "MEMEX_CONSOLIDATE_PROVIDER",
            "MEMEX_CONSOLIDATE_MODEL",
            "MEMEX_CONSOLIDATE_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("MEMEX_API_KEY", "sk-main")
        config_path = tmp_path / "memex.toml"
        write_config(
            config_path,
            '[llm]\nprovider = "openai"\nmodel = "gpt-4o"\n\n'
            '[consolidation]\nprovider = "ollama"\nmodel = "llama3.1"\n',
        )
        config = ConfigLoader().load(config_path)
        effective = config.consolidation_llm()

        assert effective.provider == "ollama"
        assert effective.model == "llama3.1"
        assert effective.base_url == "http://localhost:11434/v1"
        assert effective.api_key == "sk-main"  # inherited

    def test_env_overrides_beat_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MEMEX_API_KEY", raising=False)
        monkeypatch.delenv("MEMEX_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("MEMEX_DATA_DIR", raising=False)
        monkeypatch.setenv("MEMEX_CONSOLIDATE_PROVIDER", "openrouter")
        monkeypatch.setenv("MEMEX_CONSOLIDATE_MODEL", "cheap-model")
        monkeypatch.setenv("MEMEX_CONSOLIDATE_API_KEY", "sk-consolidate")

        config_path = tmp_path / "memex.toml"
        write_config(config_path, '[consolidation]\nprovider = "ollama"\nmodel = "llama"\n')
        effective = ConfigLoader().load(config_path).consolidation_llm()

        assert effective.provider == "openrouter"
        assert effective.model == "cheap-model"
        assert effective.api_key == "sk-consolidate"

    def test_invalid_provider_rejected(self, tmp_path: Path) -> None:
        config_path = tmp_path / "memex.toml"
        write_config(config_path, '[consolidation]\nprovider = "bogus"\n')
        with pytest.raises(Exception, match=r"consolidation\.provider"):
            ConfigLoader().load(config_path)


def _seed(data_dir: Path) -> None:
    memex = Memex(MemexConfig(data_dir=data_dir))
    memex.write(WriteInput(type="entity", title="Seed node", body="seed body"))
    memex.close()


class TestHookConsolidate:
    def test_no_key_degrades_not_fails(
        self, data_dir: Path, capture: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for var in ("MEMEX_API_KEY", "MEMEX_LLM_PROVIDER", "MEMEX_AUTO_CONSOLIDATE"):
            monkeypatch.delenv(var, raising=False)
        _seed(data_dir)

        code = cli.main(
            [
                "--data-dir",
                str(data_dir),
                "hook",
                "transcript",
                "--harness",
                "pi",
                "--path",
                str(FIXTURES / "pi_session.jsonl"),
                "--consolidate",
            ]
        )
        assert code == 0
        payload = json.loads(capture["out"])
        assert payload["consolidation"]["requested"] is True
        assert "api_key" in payload["consolidation"]["error"]

    def test_env_knob_enables_without_flag(
        self, data_dir: Path, capture: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for var in ("MEMEX_API_KEY", "MEMEX_LLM_PROVIDER"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("MEMEX_AUTO_CONSOLIDATE", "1")
        _seed(data_dir)

        code = cli.main(
            [
                "--data-dir",
                str(data_dir),
                "hook",
                "transcript",
                "--harness",
                "claude",
                "--path",
                str(FIXTURES / "claude_transcript.jsonl"),
            ]
        )
        assert code == 0
        payload = json.loads(capture["out"])
        assert payload["consolidation"]["requested"] is True

    def test_off_by_default(
        self, data_dir: Path, capture: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MEMEX_AUTO_CONSOLIDATE", raising=False)
        _seed(data_dir)

        code = cli.main(
            [
                "--data-dir",
                str(data_dir),
                "hook",
                "transcript",
                "--harness",
                "codex",
                "--path",
                str(FIXTURES / "codex_rollout.jsonl"),
            ]
        )
        assert code == 0
        assert "consolidation" not in json.loads(capture["out"])

    def test_local_provider_unreachable_partial_report(
        self, data_dir: Path, capture: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for var in ("MEMEX_API_KEY", "MEMEX_LLM_PROVIDER", "MEMEX_AUTO_CONSOLIDATE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("MEMEX_LLM_PROVIDER", "ollama")  # no server in tests
        _seed(data_dir)

        code = cli.main(
            [
                "--data-dir",
                str(data_dir),
                "hook",
                "transcript",
                "--harness",
                "pi",
                "--path",
                str(FIXTURES / "pi_session.jsonl"),
                "--consolidate",
            ]
        )
        assert code == 0
        payload = json.loads(capture["out"])
        # Client built (no key needed for ollama); LLM failure degraded to a
        # partial report: llm_calls 0, no nodes, hook still succeeds.
        assert payload["consolidation"]["llm_calls"] == 0
        assert payload["consolidation"]["nodes_created"] == 0
