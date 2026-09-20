"""Installer for per-harness adapters from the marketplace directory.

The marketplace files are the source of truth; the installer copies or
merges them into each harness's configuration. All writes are
idempotent (a second install is a no-op) and preceded by a backup.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED = ("pi", "claude", "codex", "copilot", "custom")

_MEMEX_MARKER = "memex"
_OLD_CODEX_SNIPPET = """# Memory contract (memex)

- At task start, run `memex hook session-start` and treat its output as
  project context: it lists durable memories relevant to this repository.
- When the user states a durable fact, preference, or rule, record it:
  `memex write --type <entity|preference|procedure|summary> --title "..." --body "..."`
- The `memex_recall` MCP tool (or `memex recall "<query>"`) searches all
  stored memories; prefer it over re-asking the user.
- Transcripts are captured automatically at turn completion; you never
  need to ingest sessions manually.
"""
_OLD_COPILOT_SNIPPET = """## Memory (memex)

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

TOML_TEMPLATE = """# memex configuration — see the user guide (docs/guide.md)
[llm]
# provider = "openai"     # openai | ollama | lmstudio | openrouter | custom
# model = "gpt-4o"
# api_key: prefer the MEMEX_API_KEY environment variable over storing it here

[consolidation]
# Distill episodes on a cheaper model; every field falls back to [llm].
{consolidation}
"""


def default_marketplace(explicit: Path | None = None) -> Path:
    """Resolve the marketplace directory: --from flag, the current checkout,
    the copy bundled inside the installed package (wheel installs), or the
    repository root relative to the package (editable installs)."""
    if explicit is not None:
        return explicit
    cwd_candidate = Path.cwd() / "marketplace"
    if cwd_candidate.is_dir():
        return cwd_candidate
    # __file__ is .../memex/infrastructure/: the wheel bundles marketplace
    # at .../memex/marketplace, and editable installs reach the repo root
    # three parents up from infrastructure/.
    package_dir = Path(__file__).parent
    bundled = package_dir.parent / "marketplace"
    if bundled.is_dir():
        return bundled
    editable_repo = package_dir.parent.parent.parent / "marketplace"
    if editable_repo.is_dir():
        return editable_repo
    raise FileNotFoundError(
        "marketplace directory not found (not in ./marketplace, the package, "
        "or the repository). Reinstall from source: uv tool install . --force"
    )


def init_memex(data_dir: Path, *, consolidation_provider: str | None = None) -> InstallReport:
    """Initialize ~/.memex: directory tree plus a memex.toml when absent.

    With ``consolidation_provider`` (a harness name), the generated config
    rides that harness's own model for distillation.
    """
    report = InstallReport(harness="custom")
    (data_dir / "docs").mkdir(parents=True, exist_ok=True)
    (data_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    config_path = data_dir / "memex.toml"
    if config_path.exists():
        report.notes.append("memex.toml already present; left untouched")
    else:
        if consolidation_provider:
            block = (
                f'provider = "{consolidation_provider}"'
                f"  # ride the {consolidation_provider} CLI's own model\n"
                '# model = "<cheap model>"'
            )
        else:
            block = '# provider = "openai"\n# model = "gpt-4o-mini"'
        config_path.write_text(TOML_TEMPLATE.format(consolidation=block), encoding="utf-8")
        report.files_written.append(str(config_path))
    return report


@dataclass(slots=True)
class InstallReport:
    """What the installer did for one harness."""

    harness: str
    files_written: list[str] = field(default_factory=list)
    files_merged: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    with_mcp: bool = True


def _backup(path: Path) -> None:
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".memex-bak"))


def _install_pi(marketplace: Path, home: Path, project: Path, report: InstallReport) -> None:
    extension = marketplace / "pi" / "extensions" / "memex.ts"
    target_dir = home / ".pi" / "agent" / "extensions"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "memex.ts"
    shutil.copy2(extension, target)
    report.files_written.append(str(target))
    report.notes.append("pi auto-discovers extensions on next start; remove the file to uninstall")
    report.notes.append(
        "MCP: pi has no built-in MCP server support; the extension (hooks) is the integration"
    )


def _register_claude_mcp(report: InstallReport) -> None:
    """Register the memex stdio server via `claude mcp add` (user scope)."""
    claude_bin = shutil.which("claude")
    if claude_bin is None:
        report.notes.append(
            "MCP: install the Claude CLI, then run "
            "`claude mcp add --scope user memex -- memex serve-mcp`"
        )
        return
    listing = subprocess.run(  # noqa: S603 - claude resolved via which
        [claude_bin, "mcp", "list"], capture_output=True, text=True, timeout=30, check=False
    )
    if "memex" in (listing.stdout or ""):
        report.notes.append("MCP: memex already registered with Claude Code")
        return
    added = subprocess.run(  # noqa: S603 - claude resolved via which
        [claude_bin, "mcp", "add", "--scope", "user", "memex", "--", "memex", "serve-mcp"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if added.returncode == 0:
        report.notes.append("MCP: registered with Claude Code (user scope)")
    else:
        detail = (added.stderr or "").strip().splitlines()[-1][:100] if added.stderr else ""
        report.notes.append(f"MCP registration failed: {detail or 'unknown error'}")


def _install_claude(marketplace: Path, home: Path, project: Path, report: InstallReport) -> None:
    project.mkdir(parents=True, exist_ok=True)
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings: dict[str, object] = {}
    if settings_path.exists():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            settings = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            report.notes.append("existing settings.json unreadable; backed up and replaced")
    _backup(settings_path)

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks
    events = {
        "SessionStart": ["memex", "hook", "session-start"],
        "UserPromptSubmit": ["memex", "hook", "prompt"],
        "SessionEnd": ["memex", "hook", "transcript", "--harness", "claude"],
    }
    changed = False
    for event, command in events.items():
        groups = hooks.get(event, [])
        if not isinstance(groups, list):
            groups = []
        already = any(
            isinstance(group, dict)
            and any(
                isinstance(hook, dict) and hook.get("command") == " ".join(command)
                for hook in group.get("hooks", [])
                if isinstance(hook, dict)
            )
            for group in groups
        )
        if already:
            continue
        groups.append({"hooks": [{"type": "command", "command": " ".join(command)}]})
        hooks[event] = groups
        changed = True

    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    if changed:
        report.files_merged.append(str(settings_path))
    else:
        report.files_written.append(str(settings_path))
        report.notes.append("hooks already present; settings.json rewritten unchanged")
    if report.with_mcp:
        _register_claude_mcp(report)

    rules_path = project / "CLAUDE.md"
    snippet = (marketplace / "claude" / "CLAUDE-snippet.md").read_text(encoding="utf-8")
    existing_rules = rules_path.read_text(encoding="utf-8") if rules_path.exists() else ""
    if snippet in existing_rules:
        report.notes.append("CLAUDE.md already contains the memory contract")
    elif "## Memory (memex)" in existing_rules:
        report.notes.append("CLAUDE.md has custom Memex guidance; left unchanged")
    else:
        _backup(rules_path)
        separator = ("\n" if existing_rules.endswith("\n") else "\n\n") if existing_rules else ""
        rules_path.write_text(existing_rules + separator + snippet, encoding="utf-8")
        report.files_merged.append(str(rules_path))


def _install_codex(marketplace: Path, home: Path, project: Path, report: InstallReport) -> None:
    project.mkdir(parents=True, exist_ok=True)
    codex_dir = home / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)

    wrapper_source = marketplace / "codex" / "memex-codex-notify.py"
    wrapper = codex_dir / "memex-codex-notify.py"
    shutil.copy2(wrapper_source, wrapper)
    wrapper.chmod(0o755)
    report.files_written.append(str(wrapper))

    config_path = codex_dir / "config.toml"
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    _backup(config_path)

    # `notify` must sit in the TOML root table (line 3 by convention):
    # appending after a [table] header would scope it to that table and
    # silently disable it. Normalize: drop any existing notify line
    # (root or misplaced), then insert at line 3.
    lines = [line for line in existing.splitlines() if not line.strip().startswith("notify")]
    notify_line = f'notify = ["{wrapper}"]'
    lines.insert(min(2, len(lines)), notify_line)
    updated = "\n".join(lines)
    if updated and not updated.endswith("\n"):
        updated += "\n"

    if report.with_mcp:
        if "[mcp_servers.memex]" not in updated:
            updated += '\n[mcp_servers.memex]\ncommand = "memex"\nargs = ["serve-mcp"]\n'
    else:
        report.notes.append("MCP: skipped (--no-mcp)")

    if updated != existing:
        config_path.write_text(updated, encoding="utf-8")
        report.files_merged.append(str(config_path))
    else:
        report.notes.append("config.toml already wired; left unchanged")

    agents = project / "AGENTS.md"
    snippet = (marketplace / "codex" / "AGENTS-snippet.md").read_text(encoding="utf-8")
    existing_agents = agents.read_text(encoding="utf-8") if agents.exists() else ""
    if _OLD_CODEX_SNIPPET in existing_agents:
        _backup(agents)
        agents.write_text(existing_agents.replace(_OLD_CODEX_SNIPPET, snippet, 1), encoding="utf-8")
        report.files_merged.append(str(agents))
    elif "memex hook session-start" in existing_agents:
        report.notes.append("AGENTS.md already contains the memory contract")
    else:
        with agents.open("a", encoding="utf-8") as handle:
            handle.write("\n" + snippet if not snippet.startswith("\n") else snippet)
        report.files_merged.append(str(agents))


def _install_copilot(marketplace: Path, home: Path, project: Path, report: InstallReport) -> None:
    github = project / ".github"
    github.mkdir(parents=True, exist_ok=True)

    instructions = github / "copilot-instructions.md"
    snippet = (marketplace / "copilot" / "copilot-instructions-snippet.md").read_text(
        encoding="utf-8"
    )
    existing_instructions = (
        instructions.read_text(encoding="utf-8") if instructions.exists() else ""
    )
    if _OLD_COPILOT_SNIPPET in existing_instructions:
        _backup(instructions)
        instructions.write_text(
            existing_instructions.replace(_OLD_COPILOT_SNIPPET, snippet, 1), encoding="utf-8"
        )
        report.files_merged.append(str(instructions))
    elif "memex" in existing_instructions:
        report.notes.append("copilot-instructions.md already mentions memex")
    else:
        with instructions.open("a", encoding="utf-8") as handle:
            handle.write(snippet)
        report.files_merged.append(str(instructions))

    workflows = github / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    workflow_target = workflows / "memex-verify.yml"
    shutil.copy2(marketplace / "copilot" / "memex-verify.yml", workflow_target)
    report.files_written.append(str(workflow_target))
    if report.with_mcp:
        vscode = project / ".vscode"
        vscode.mkdir(parents=True, exist_ok=True)
        mcp_path = vscode / "mcp.json"
        mcp_config: dict[str, object] = {}
        if mcp_path.exists():
            try:
                loaded = json.loads(mcp_path.read_text(encoding="utf-8"))
                mcp_config = loaded if isinstance(loaded, dict) else {}
            except json.JSONDecodeError:
                _backup(mcp_path)
        servers = mcp_config.setdefault("servers", {})
        if not isinstance(servers, dict):
            servers = {}
            mcp_config["servers"] = servers
        if "memex" not in servers:
            servers["memex"] = {"command": "memex", "args": ["serve-mcp"]}
            mcp_path.write_text(json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8")
            report.files_merged.append(str(mcp_path))
            report.notes.append("MCP: .vscode/mcp.json (VS Code agent mode)")
    report.notes.append(
        "hosted Copilot cannot reach local stdio MCP; "
        "the verify workflow is the deterministic layer"
    )


_INSTALLERS = {
    "pi": _install_pi,
    "claude": _install_claude,
    "codex": _install_codex,
    "copilot": _install_copilot,
}

_HARNESS_PROVIDERS = {"pi": "pi", "claude": "claude", "codex": "codex"}


def install_harness(
    harness: str,
    marketplace: Path,
    *,
    home: Path,
    project: Path,
    with_mcp: bool = True,
) -> InstallReport:
    """Install one harness adapter from the marketplace directory."""
    if harness == "custom":
        return init_memex(_memex_data_dir())
    try:
        installer = _INSTALLERS[harness]
    except KeyError:
        raise ValueError(f"unknown harness {harness!r}; expected one of {SUPPORTED}") from None
    if not marketplace.is_dir():
        raise FileNotFoundError(f"marketplace directory not found: {marketplace}")
    report = InstallReport(harness=harness, with_mcp=with_mcp)
    installer(marketplace, home, project, report)
    if harness in _HARNESS_PROVIDERS:
        # Seamless consolidation: point new installs at the harness's model.
        init = init_memex(_memex_data_dir(), consolidation_provider=_HARNESS_PROVIDERS[harness])
        report.files_written.extend(init.files_written)
        report.notes.extend(init.notes)
    return report


def _memex_data_dir() -> Path:
    import os

    return Path(os.environ.get("MEMEX_DATA_DIR", str(Path.home() / ".memex"))).expanduser()
