"""MCP registration during install: per-harness, flag-controlled."""

import json
import stat
from pathlib import Path

import pytest

from memex.infrastructure.harness.installer import install_harness

MARKETPLACE = Path(__file__).parent.parent.parent / "src/memex/marketplace"


def fake_claude(bin_dir: Path, behavior: str) -> None:
    script = bin_dir / "claude"
    if behavior == "absent":
        return
    if behavior == "already":
        body = "#!/bin/sh\necho 'memex  memex serve-mcp  (user)'\nexit 0\n"
    elif behavior == "ok":
        body = "#!/bin/sh\nexit 0\n"
    else:  # fail
        body = "#!/bin/sh\necho 'boom' >&2\nexit 1\n"
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv("MEMEX_DATA_DIR", str(tmp_path / "memex-data"))
    project = tmp_path / "project"
    project.mkdir(parents=True)
    return tmp_path / "home", project


def claude_notes(home: Path, project: Path, behavior: str, with_mcp: bool = True) -> list[str]:
    bin_dir = project / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake_claude(bin_dir, behavior)
    report = install_harness(
        "claude",
        MARKETPLACE,
        home=home,
        project=project,
        with_mcp=with_mcp,
    )
    return [note for note in report.notes if "MCP" in note]


class TestClaudeMcp:
    def test_registers_via_cli(
        self, homes: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        home, project = homes
        monkeypatch.setenv("PATH", str(project / "bin"))
        notes = claude_notes(home, project, "ok")
        assert any("registered with Claude Code" in note for note in notes)

    def test_already_registered_is_idempotent(
        self, homes: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        home, project = homes
        monkeypatch.setenv("PATH", str(project / "bin"))
        notes = claude_notes(home, project, "already")
        assert any("already registered" in note for note in notes)

    def test_cli_failure_reported_not_fatal(
        self, homes: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        home, project = homes
        monkeypatch.setenv("PATH", str(project / "bin"))
        notes = claude_notes(home, project, "fail")
        assert any("MCP registration failed" in note for note in notes)

    def test_no_cli_gives_the_command(
        self, homes: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        home, project = homes
        monkeypatch.setenv("PATH", str(project / "empty"))
        notes = claude_notes(home, project, "absent")
        assert any("claude mcp add" in note for note in notes)

    def test_no_mcp_flag_skips(
        self, homes: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        home, project = homes
        monkeypatch.setenv("PATH", str(project / "bin"))
        notes = claude_notes(home, project, "ok", with_mcp=False)
        assert notes == []


class TestCodexMcp:
    def test_mcp_in_config_by_default(self, homes: tuple[Path, Path]) -> None:
        home, project = homes
        project.mkdir(parents=True, exist_ok=True)
        install_harness("codex", MARKETPLACE, home=home, project=project)
        config = (home / ".codex/config.toml").read_text(encoding="utf-8")
        assert "[mcp_servers.memex]" in config

    def test_no_mcp_flag_omits_server(self, homes: tuple[Path, Path]) -> None:
        home, project = homes
        project.mkdir(parents=True, exist_ok=True)
        install_harness("codex", MARKETPLACE, home=home, project=project, with_mcp=False)
        config = (home / ".codex/config.toml").read_text(encoding="utf-8")
        assert "[mcp_servers.memex]" not in config
        assert "notify" in config  # transcript capture still wired


class TestPiMcp:
    def test_notes_explain_no_mcp(self, homes: tuple[Path, Path]) -> None:
        home, project = homes
        report = install_harness("pi", MARKETPLACE, home=home, project=project)
        assert any("no built-in MCP" in note for note in report.notes)


class TestCopilotMcp:
    def test_vscode_mcp_json_written(self, homes: tuple[Path, Path]) -> None:
        home, project = homes
        install_harness("copilot", MARKETPLACE, home=home, project=project)
        mcp = json.loads((project / ".vscode/mcp.json").read_text(encoding="utf-8"))
        assert mcp["servers"]["memex"] == {"command": "memex", "args": ["serve-mcp"]}

    def test_mcp_json_merge_is_idempotent(self, homes: tuple[Path, Path]) -> None:
        home, project = homes
        project.mkdir(parents=True, exist_ok=True)
        vscode = project / ".vscode"
        vscode.mkdir()
        (vscode / "mcp.json").write_text(
            json.dumps({"servers": {"other": {"command": "x"}}}), encoding="utf-8"
        )
        install_harness("copilot", MARKETPLACE, home=home, project=project)
        install_harness("copilot", MARKETPLACE, home=home, project=project)
        mcp = json.loads((vscode / "mcp.json").read_text(encoding="utf-8"))
        assert set(mcp["servers"]) == {"other", "memex"}

    def test_no_mcp_flag_skips_vscode(self, homes: tuple[Path, Path]) -> None:
        home, project = homes
        install_harness("copilot", MARKETPLACE, home=home, project=project, with_mcp=False)
        assert not (project / ".vscode/mcp.json").exists()
