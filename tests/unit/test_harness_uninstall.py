"""Uninstall removes Memex-owned adapter entries from isolated harness homes."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from memex import cli
from memex.infrastructure import harness_installer
from memex.infrastructure.harness_installer import install_harness, uninstall_harness

MARKETPLACE = Path(__file__).parent.parent.parent / "marketplace"


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv("MEMEX_DATA_DIR", str(tmp_path / "memex-data"))
    home, project = tmp_path / "home", tmp_path / "project"
    project.mkdir()
    return home, project


def test_claude_uninstall_preserves_other_hooks_and_project_rules(
    homes: tuple[Path, Path],
) -> None:
    home, project = homes
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps(
            {
                "model": "opus",
                "hooks": {
                    "SessionStart": [{"hooks": [{"type": "command", "command": "echo keep"}]}]
                },
            }
        ),
        encoding="utf-8",
    )
    rules = project / "CLAUDE.md"
    rules.write_text("# Team\nKeep this rule.\n", encoding="utf-8")
    install_harness("claude", MARKETPLACE, home=home, project=project, with_mcp=False)
    install_backup = settings.with_suffix(".json.memex-bak").read_bytes()

    report = uninstall_harness("claude", MARKETPLACE, home=home, project=project)

    restored = json.loads(settings.read_text(encoding="utf-8"))
    assert restored["model"] == "opus"
    assert restored["hooks"] == {
        "SessionStart": [{"hooks": [{"type": "command", "command": "echo keep"}]}]
    }
    assert rules.read_text(encoding="utf-8") == "# Team\nKeep this rule.\n"
    assert (home / ".claude/settings.json.memex-bak").exists()
    assert settings.with_suffix(".json.memex-bak").read_bytes() == install_backup
    assert settings.with_suffix(".json.memex-uninstall-bak").exists()
    assert str(settings) in report.files_updated
    assert (home.parent / "memex-data/docs").exists()
    second = uninstall_harness("claude", MARKETPLACE, home=home, project=project)
    assert not second.files_removed and not second.files_updated


def test_codex_uninstall_preserves_other_config(
    homes: tuple[Path, Path],
) -> None:
    home, project = homes
    config = home / ".codex/config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('model = "gpt"\n[mcp_servers.other]\ncommand = "other"\n', encoding="utf-8")
    agents = project / "AGENTS.md"
    agents.write_text("# Team\nKeep this rule.\n", encoding="utf-8")
    install_harness("codex", MARKETPLACE, home=home, project=project)

    uninstall_harness("codex", MARKETPLACE, home=home, project=project)

    updated = config.read_text(encoding="utf-8")
    assert 'model = "gpt"' in updated
    assert "[mcp_servers.other]" in updated
    assert "[mcp_servers.memex]" not in updated
    assert "memex-codex-notify.py" not in updated
    assert not (home / ".codex/memex-codex-notify.py").exists()
    assert agents.read_text(encoding="utf-8") == "# Team\nKeep this rule.\n"


def test_codex_uninstall_leaves_changed_wrapper(
    homes: tuple[Path, Path],
) -> None:
    home, project = homes
    install_harness("codex", MARKETPLACE, home=home, project=project)
    wrapper = home / ".codex/memex-codex-notify.py"
    wrapper.write_text("# customized\n", encoding="utf-8")
    config = home / ".codex/config.toml"
    config.write_text(
        config.read_text(encoding="utf-8") + '\n[custom]\nname = "keep"\n', encoding="utf-8"
    )

    report = uninstall_harness("codex", MARKETPLACE, home=home, project=project)

    assert wrapper.exists()
    assert any("changed since install" in note for note in report.notes)


def test_codex_uninstall_does_not_break_invalid_config_reference(
    homes: tuple[Path, Path],
) -> None:
    home, project = homes
    install_harness("codex", MARKETPLACE, home=home, project=project)
    config = home / ".codex/config.toml"
    config.write_text(config.read_text(encoding="utf-8") + "[broken\n", encoding="utf-8")

    report = uninstall_harness("codex", MARKETPLACE, home=home, project=project)

    assert (home / ".codex/memex-codex-notify.py").exists()
    assert "memex-codex-notify.py" in config.read_text(encoding="utf-8")
    assert any("not valid TOML" in note for note in report.notes)


def test_codex_uninstall_preserves_custom_memex_server(
    homes: tuple[Path, Path],
) -> None:
    home, project = homes
    install_harness("codex", MARKETPLACE, home=home, project=project)
    config = home / ".codex/config.toml"
    original = config.read_text(encoding="utf-8")
    config.write_text(
        original.replace('args = ["serve-mcp"]', 'args = ["custom"]'), encoding="utf-8"
    )

    report = uninstall_harness("codex", MARKETPLACE, home=home, project=project)

    updated = config.read_text(encoding="utf-8")
    assert "[mcp_servers.memex]" in updated
    assert 'args = ["custom"]' in updated
    assert any("modified Memex MCP entry" in note for note in report.notes)


def test_codex_uninstall_reports_modified_notify_without_partial_config_edit(
    homes: tuple[Path, Path],
) -> None:
    home, project = homes
    install_harness("codex", MARKETPLACE, home=home, project=project)
    config = home / ".codex/config.toml"
    wrapper = home / ".codex/memex-codex-notify.py"
    original = config.read_text(encoding="utf-8").replace(
        f'notify = ["{wrapper}"]', f'notify = ["python3", "{wrapper}"]'
    )
    config.write_text(original, encoding="utf-8")

    report = uninstall_harness("codex", MARKETPLACE, home=home, project=project)

    assert config.read_text(encoding="utf-8") == original
    assert wrapper.exists()
    assert any("still references the Memex notify wrapper" in note for note in report.notes)


def test_pi_uninstall_removes_only_unmodified_extension(homes: tuple[Path, Path]) -> None:
    home, project = homes
    install_harness("pi", MARKETPLACE, home=home, project=project)
    extension = home / ".pi/agent/extensions/memex.ts"
    uninstall_harness("pi", MARKETPLACE, home=home, project=project)
    assert not extension.exists()

    extension.write_text("// custom\n", encoding="utf-8")
    report = uninstall_harness("pi", MARKETPLACE, home=home, project=project)
    assert extension.exists()
    assert any("changed since install" in note for note in report.notes)


def test_copilot_uninstall_preserves_other_mcp_and_instructions(
    homes: tuple[Path, Path],
) -> None:
    home, project = homes
    vscode = project / ".vscode"
    vscode.mkdir()
    mcp_path = vscode / "mcp.json"
    mcp_path.write_text(json.dumps({"servers": {"other": {"command": "other"}}}), encoding="utf-8")
    instructions = project / ".github/copilot-instructions.md"
    instructions.parent.mkdir()
    instructions.write_text("# Team\n", encoding="utf-8")
    install_harness("copilot", MARKETPLACE, home=home, project=project)

    uninstall_harness("copilot", MARKETPLACE, home=home, project=project)

    assert json.loads(mcp_path.read_text(encoding="utf-8")) == {
        "servers": {"other": {"command": "other"}}
    }
    assert instructions.read_text(encoding="utf-8") == "# Team\n"
    assert not (project / ".github/workflows/memex-verify.yml").exists()


def test_cli_uninstall_alias_keeps_memory_data(
    homes: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home, project = homes
    monkeypatch.chdir(project)
    install_harness("pi", MARKETPLACE, home=home, project=project)

    assert cli.main(["harness", "uninstall", "pi", "--home", str(home)]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["harness"] == "pi"
    assert not (home / ".pi/agent/extensions/memex.ts").exists()
    assert (home.parent / "memex-data/docs").exists()


def test_cli_uninstall_direct_command(
    homes: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home, project = homes
    monkeypatch.chdir(project)
    install_harness("pi", MARKETPLACE, home=home, project=project)
    (project / "marketplace").mkdir()  # unrelated project directory must not shadow package assets

    assert cli.main(["uninstall", "pi", "--home", str(home)]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["files_removed"] == [str(home / ".pi/agent/extensions/memex.ts")]


def test_uninstall_custom_does_not_remove_data(homes: tuple[Path, Path]) -> None:
    home, project = homes
    report = uninstall_harness("custom", MARKETPLACE, home=home, project=project)
    assert report.notes == ["No adapter to remove; Memex data retained"]


@pytest.mark.parametrize("installed_by_memex", [True, False])
def test_claude_mcp_removal_checks_user_entry_before_deleting(
    installed_by_memex: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        "memex.infrastructure.harness_installer.shutil.which", lambda name: "/test/claude"
    )

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        command = "memex" if installed_by_memex else "other"
        output = (
            "memex:\n  Scope: User config (available in all your projects)\n"
            f"  Command: {command}\n  Args: serve-mcp\n"
        )
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    monkeypatch.setattr("memex.infrastructure.harness_installer.subprocess.run", run)
    report = harness_installer.UninstallReport(harness="claude")

    harness_installer._unregister_claude_mcp(Path.home(), report)

    assert len(commands) == (2 if installed_by_memex else 1)
    if installed_by_memex:
        assert commands[1] == ["/test/claude", "mcp", "remove", "memex", "-s", "user"]
    else:
        assert "differs from Memex install" in report.notes[0]


def test_claude_uninstall_leaves_invalid_settings_untouched(homes: tuple[Path, Path]) -> None:
    home, project = homes
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{invalid", encoding="utf-8")

    report = uninstall_harness("claude", MARKETPLACE, home=home, project=project)

    assert settings.read_text(encoding="utf-8") == "{invalid"
    assert any("not valid JSON" in note for note in report.notes)


def test_claude_mcp_lookup_timeout_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "memex.infrastructure.harness_installer.shutil.which", lambda name: "/test/claude"
    )

    def timeout(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args, 30)

    monkeypatch.setattr("memex.infrastructure.harness_installer.subprocess.run", timeout)
    report = harness_installer.UninstallReport(harness="claude")

    harness_installer._unregister_claude_mcp(Path.home(), report)

    assert report.notes == ["Claude MCP lookup failed; user entry left untouched"]


def test_claude_mcp_remove_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "memex.infrastructure.harness_installer.shutil.which", lambda name: "/test/claude"
    )

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "remove" in args:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="failed")
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=(
                "Scope: User config (available in all your projects)\n"
                "Command: memex\nArgs: serve-mcp\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("memex.infrastructure.harness_installer.subprocess.run", run)
    report = harness_installer.UninstallReport(harness="claude")

    harness_installer._unregister_claude_mcp(Path.home(), report)

    assert report.notes == ["Claude MCP removal failed; user entry remains"]


def test_claude_mcp_home_override_skips_real_cli(tmp_path: Path) -> None:
    report = harness_installer.UninstallReport(harness="claude")

    harness_installer._unregister_claude_mcp(tmp_path / "other-home", report)

    assert "skipped for --home override" in report.notes[0]


def test_copilot_uninstall_keeps_malformed_shared_mcp_config(
    homes: tuple[Path, Path],
) -> None:
    home, project = homes
    install_harness("copilot", MARKETPLACE, home=home, project=project)
    mcp_path = project / ".vscode/mcp.json"
    mcp_path.write_text("{invalid", encoding="utf-8")

    report = uninstall_harness("copilot", MARKETPLACE, home=home, project=project)

    assert mcp_path.read_text(encoding="utf-8") == "{invalid"
    assert any("not valid JSON" in note for note in report.notes)


def test_copilot_uninstall_reports_modified_mcp_entry(homes: tuple[Path, Path]) -> None:
    home, project = homes
    install_harness("copilot", MARKETPLACE, home=home, project=project)
    mcp_path = project / ".vscode/mcp.json"
    config = json.loads(mcp_path.read_text(encoding="utf-8"))
    config["servers"]["memex"]["args"] = ["custom"]
    mcp_path.write_text(json.dumps(config), encoding="utf-8")

    report = uninstall_harness("copilot", MARKETPLACE, home=home, project=project)

    assert json.loads(mcp_path.read_text(encoding="utf-8")) == config
    assert any("modified Memex MCP entry" in note for note in report.notes)


def test_copilot_uninstall_removes_sole_memex_mcp_config(homes: tuple[Path, Path]) -> None:
    home, project = homes
    install_harness("copilot", MARKETPLACE, home=home, project=project)
    mcp_path = project / ".vscode/mcp.json"

    report = uninstall_harness("copilot", MARKETPLACE, home=home, project=project)

    assert not mcp_path.exists()
    assert str(mcp_path) in report.files_removed


def test_uninstall_rejects_config_directory_symlink_outside_project(
    homes: tuple[Path, Path], tmp_path: Path
) -> None:
    home, project = homes
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / ".vscode").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="uninstall target leaves its root"):
        uninstall_harness("copilot", MARKETPLACE, home=home, project=project)


def test_missing_marketplace_asset_does_not_partially_uninstall(
    homes: tuple[Path, Path], tmp_path: Path
) -> None:
    home, project = homes
    install_harness("pi", MARKETPLACE, home=home, project=project)
    extension = home / ".pi/agent/extensions/memex.ts"
    incomplete = tmp_path / "incomplete-marketplace"
    incomplete.mkdir()

    with pytest.raises(FileNotFoundError, match="marketplace asset not found"):
        uninstall_harness("pi", incomplete, home=home, project=project)

    assert extension.exists()
