"""Harness installer: idempotent config merge/copy per harness."""

import json
from pathlib import Path

import pytest

from memex.infrastructure.harness_installer import install_harness

MARKETPLACE = Path(__file__).parent.parent.parent / "marketplace"


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    # Consolidation provisioning writes memex.toml into MEMEX_DATA_DIR;
    # keep every installer test away from the developer's real ~/.memex.
    monkeypatch.setenv("MEMEX_DATA_DIR", str(tmp_path / "memex-data"))
    return tmp_path / "home", tmp_path / "project"


def test_unknown_harness_rejected(homes: tuple[Path, Path]) -> None:
    home, project = homes
    with pytest.raises(ValueError, match="unknown harness"):
        install_harness("vscode", MARKETPLACE, home=home, project=project)


def test_missing_marketplace_rejected(homes: tuple[Path, Path]) -> None:
    home, project = homes
    with pytest.raises(FileNotFoundError, match="marketplace"):
        install_harness("pi", home / "nope", home=home, project=project)


def test_pi_install_copies_extension(homes: tuple[Path, Path]) -> None:
    home, project = homes
    report = install_harness("pi", MARKETPLACE, home=home, project=project)

    extension = home / ".pi/agent/extensions/memex.ts"
    assert extension.exists()
    assert "session_shutdown" in extension.read_text(encoding="utf-8")
    assert str(extension) in report.files_written


def test_claude_merges_hooks_idempotently(homes: tuple[Path, Path]) -> None:
    home, project = homes
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"model": "opus"}), encoding="utf-8")

    install_harness("claude", MARKETPLACE, home=home, project=project)
    first = json.loads(settings.read_text(encoding="utf-8"))

    assert first["model"] == "opus"  # existing config preserved
    commands = [
        hook["command"] for group in first["hooks"]["SessionEnd"] for hook in group["hooks"]
    ]
    assert "memex hook transcript --harness claude" in commands
    assert settings.with_suffix(".json.memex-bak").exists()

    # second install: no duplicate hook entries
    install_harness("claude", MARKETPLACE, home=home, project=project)
    second = json.loads(settings.read_text(encoding="utf-8"))
    assert second == first


def test_codex_install_wires_notify_and_mcp(homes: tuple[Path, Path]) -> None:
    home, project = homes
    project.mkdir(parents=True)
    (project / "AGENTS.md").write_text("# Project\n", encoding="utf-8")

    install_harness("codex", MARKETPLACE, home=home, project=project)

    wrapper = home / ".codex/memex-codex-notify.py"
    assert wrapper.exists()
    config = (home / ".codex/config.toml").read_text(encoding="utf-8")
    assert "notify" in config and "memex-codex-notify.py" in config
    assert "[mcp_servers.memex]" in config
    agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "memex hook session-start" in agents

    # idempotent: second install does not duplicate
    install_harness("codex", MARKETPLACE, home=home, project=project)
    config2 = (home / ".codex/config.toml").read_text(encoding="utf-8")
    assert config2.count("[mcp_servers.memex]") == 1
    agents2 = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert agents2.count("Memory contract (memex)") == 1


def test_copilot_install_instructions_and_workflow(homes: tuple[Path, Path]) -> None:
    home, project = homes
    install_harness("copilot", MARKETPLACE, home=home, project=project)

    instructions = project / ".github/copilot-instructions.md"
    assert "memex" in instructions.read_text(encoding="utf-8")
    workflow = project / ".github/workflows/memex-verify.yml"
    assert "memex verify" in workflow.read_text(encoding="utf-8")

    install_harness("copilot", MARKETPLACE, home=home, project=project)
    instructions_text = instructions.read_text(encoding="utf-8")
    assert instructions_text.count("## Memory (memex)") == 1


def test_cli_harness_install(
    homes: tuple[Path, Path], capture: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from memex import cli

    home, project = homes
    project.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MEMEX_DATA_DIR", str(project / "memex-data"))
    code = cli.main(
        [
            "harness",
            "install",
            "pi",
            "--from",
            str(MARKETPLACE),
            "--home",
            str(home),
        ]
    )
    assert code == 0
    payload = json.loads(capture["out"])
    assert payload["harness"] == "pi"
    assert payload["files_written"]
