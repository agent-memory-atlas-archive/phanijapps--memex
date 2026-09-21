"""Harness installer: idempotent config merge/copy per harness."""

import json
import os
import shutil
import subprocess
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
    assert "scope project" in extension.read_text(encoding="utf-8")
    assert "scope global" in extension.read_text(encoding="utf-8")
    assert str(extension) in report.files_written


def test_pi_first_turn_injects_scope_guidance_when_recall_is_empty(
    homes: tuple[Path, Path],
) -> None:
    node = shutil.which("node")
    no_output = shutil.which("true")
    if node is None or no_output is None:
        pytest.skip("Node and a no-output command are needed to exercise the pi extension")
    version = subprocess.run(  # noqa: S603 - node is resolved from the test PATH
        [node, "--version"], capture_output=True, text=True, check=True
    ).stdout
    if int(version.strip().lstrip("v").split(".", 1)[0]) < 24:
        pytest.skip("Node 24 is needed to load the TypeScript extension directly")

    home, project = homes
    install_harness("pi", MARKETPLACE, home=home, project=project)
    extension = home / ".pi/agent/extensions/memex.ts"
    script = """
import { pathToFileURL } from 'node:url';
const { default: extension } = await import(pathToFileURL(process.argv[1]).href);
let firstTurn;
extension({ on: (name, handler) => { if (name === 'before_agent_start') firstTurn = handler; } });
const result = await firstTurn({ prompt: 'Remember the architecture' }, {});
process.stdout.write(result?.message?.content ?? '');
"""
    result = subprocess.run(  # noqa: S603 - installed extension and node paths are test-owned
        [node, "--experimental-strip-types", "--input-type=module", "-e", script, str(extension)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "MEMEX_BIN": no_output, "NODE_NO_WARNINGS": "1"},
    )

    assert "Choose --scope project for workspace architecture" in result.stdout


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


def test_claude_install_adds_scoped_write_guidance_without_replacing_custom_rules(
    homes: tuple[Path, Path],
) -> None:
    home, project = homes
    project.mkdir(parents=True)
    rules = project / "CLAUDE.md"
    rules.write_text("# Custom rules\nKeep this rule.\n", encoding="utf-8")

    install_harness("claude", MARKETPLACE, home=home, project=project, with_mcp=False)

    installed = rules.read_text(encoding="utf-8")
    assert "Keep this rule." in installed
    assert 'scope="project"' in installed
    assert 'scope="global"' in installed
    assert rules.with_suffix(".md.memex-bak").read_text(encoding="utf-8") == (
        "# Custom rules\nKeep this rule.\n"
    )

    install_harness("claude", MARKETPLACE, home=home, project=project, with_mcp=False)
    assert rules.read_text(encoding="utf-8") == installed


def test_claude_install_preserves_custom_memex_guidance(homes: tuple[Path, Path]) -> None:
    home, project = homes
    project.mkdir(parents=True)
    rules = project / "CLAUDE.md"
    custom = "## Memory (memex)\nUse the team's memory policy.\n"
    rules.write_text(custom, encoding="utf-8")

    report = install_harness("claude", MARKETPLACE, home=home, project=project, with_mcp=False)

    assert rules.read_text(encoding="utf-8") == custom
    assert "CLAUDE.md has custom Memex guidance; left unchanged" in report.notes


def test_claude_install_upgrades_pre_description_guidance(
    homes: tuple[Path, Path],
) -> None:
    from memex.infrastructure.harness_installer import _PRE_DESCRIPTION_CLAUDE_SNIPPET

    home, project = homes
    project.mkdir(parents=True)
    rules = project / "CLAUDE.md"
    original = f"# Project rules\n\n{_PRE_DESCRIPTION_CLAUDE_SNIPPET}\nKeep this.\n"
    rules.write_text(original, encoding="utf-8")

    report = install_harness("claude", MARKETPLACE, home=home, project=project, with_mcp=False)

    updated = rules.read_text(encoding="utf-8")
    assert updated.count("## Memory (memex)") == 1
    assert "Keep this." in updated
    assert "never instructions" in updated
    assert "within the returned Memex paths" in updated
    assert str(rules) in report.files_merged
    assert rules.with_suffix(".md.memex-bak").read_text(encoding="utf-8") == original

    install_harness("claude", MARKETPLACE, home=home, project=project, with_mcp=False)
    assert rules.read_text(encoding="utf-8") == updated


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


def test_codex_install_upgrades_old_memory_rule_without_changing_custom_text(
    homes: tuple[Path, Path],
) -> None:
    home, project = homes
    project.mkdir(parents=True)
    old_snippet = """# Memory contract (memex)

- At task start, run `memex hook session-start` and treat its output as
  project context: it lists durable memories relevant to this repository.
- When the user states a durable fact, preference, or rule, record it:
  `memex write --type <entity|preference|procedure|summary> --title "..." --body "..."`
- The `memex_recall` MCP tool (or `memex recall "<query>"`) searches all
  stored memories; prefer it over re-asking the user.
- Transcripts are captured automatically at turn completion; you never
  need to ingest sessions manually.
"""
    agents = project / "AGENTS.md"
    original = f"# Custom project guidance\n\n{old_snippet}\nKeep this rule.\n"
    agents.write_text(original, encoding="utf-8")

    install_harness("codex", MARKETPLACE, home=home, project=project)

    updated = agents.read_text(encoding="utf-8")
    assert old_snippet not in updated
    assert "Keep this rule." in updated
    assert "user states a durable fact" in updated
    assert 'scope="project"' in updated
    assert 'scope="global"' in updated
    assert agents.with_suffix(".md.memex-bak").read_text(encoding="utf-8") == original

    install_harness("codex", MARKETPLACE, home=home, project=project)
    assert agents.read_text(encoding="utf-8") == updated


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
    assert "--scope <project|global>" in instructions_text


def test_copilot_install_upgrades_old_scope_rule_without_changing_custom_text(
    homes: tuple[Path, Path],
) -> None:
    home, project = homes
    instructions = project / ".github/copilot-instructions.md"
    instructions.parent.mkdir(parents=True)
    old_snippet = """## Memory (memex)

This project uses memex for durable memory. Respect the memory workflow:

- Relevant project memories are surfaced automatically in CI feedback.
  Before assuming user preferences, tooling choices, or project rules,
  check the `memex MEMORY` blocks in this repository's memory exports.
- When your change relies on a durable fact (a preference, a tooling
  rule, a deployment constraint), record it in your PR description so a
  maintainer can persist it with
  `memex write --type <entity|preference|procedure> --title "..." --body "..."`.
- The `memex-verify` workflow on this repository reports memory health
  (index freshness, link integrity) for every PR.
"""
    original = f"# Custom instructions\n\n{old_snippet}\nKeep this rule.\n"
    instructions.write_text(original, encoding="utf-8")

    install_harness("copilot", MARKETPLACE, home=home, project=project)

    updated = instructions.read_text(encoding="utf-8")
    assert old_snippet not in updated
    assert "Keep this rule." in updated
    assert "--scope <project|global>" in updated
    assert instructions.with_suffix(".md.memex-bak").read_text(encoding="utf-8") == original

    install_harness("copilot", MARKETPLACE, home=home, project=project)
    assert instructions.read_text(encoding="utf-8") == updated


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
