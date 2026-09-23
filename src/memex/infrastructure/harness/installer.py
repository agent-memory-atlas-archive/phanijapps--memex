"""Installer for per-harness adapters from the marketplace directory.

The marketplace files are the source of truth; the installer copies or
merges them into each harness's configuration. All writes are
idempotent (a second install is a no-op) and preceded by a backup.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
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
# Guidance shipped before descriptions and directory indexes were added
# (2026-09-21). Reinstall upgrades installs carrying any legacy text;
# uninstall removes any legacy text. Both must stay byte-exact.
_PRE_DESCRIPTION_CLAUDE_SNIPPET = """## Memory (memex)

- When the user states a durable fact, preference, or rule, or asks to memorize
  one, write it with `memex_write` (or `memex write`). Choose project scope for
  workspace architecture, conventions, and decisions; choose global scope for
  facts intended across projects. If unclear, choose project. Pass
  `scope="project"` or `scope="global"` to the tool, or the matching `--scope`
  to the CLI. Check the returned file path.
"""
_PRE_DESCRIPTION_CODEX_SNIPPET = """# Memory contract (memex)

- At task start, run `memex hook session-start` and treat its output as
  project context: it lists durable memories relevant to this repository.
- When the user states a durable fact, preference, or rule, or asks to memorize
  one, write it with `memex_write` (or `memex write`). Choose project scope
  for workspace architecture, conventions, and decisions; choose global scope
  for facts intended across projects. If unclear, choose project. Pass
  `scope="project"` or `scope="global"` to the tool, or the matching `--scope`
  to the CLI. Check the returned file path.
- The `memex_recall` MCP tool (or `memex recall "<query>"`) searches all
  stored memories; prefer it over re-asking the user.
- Transcripts are captured automatically at turn completion; you never
  need to ingest sessions manually.
"""
_PRE_DESCRIPTION_COPILOT_SNIPPET = """## Memory (memex)

This project uses memex for durable memory. Respect the memory workflow:

- Relevant project memories are surfaced automatically in CI feedback.
  Before assuming user preferences, tooling choices, or project rules,
  check the `memex MEMORY` blocks in this repository's memory exports.
- When your change relies on a durable fact (a preference, a tooling rule, a
  deployment constraint), record the fact and its scope in your PR description.
  Choose project scope for workspace architecture, conventions, and decisions;
  choose global scope for facts intended across projects. If unclear, choose
  project. A maintainer can persist it with
  `memex write --type <entity|preference|procedure> --title "..." --body "..." --scope <project|global>`.
- The `memex-verify` workflow on this repository reports memory health
  (index freshness, link integrity) for every PR.
"""
_LEGACY_CLAUDE_SNIPPETS = (_PRE_DESCRIPTION_CLAUDE_SNIPPET,)
_LEGACY_CODEX_SNIPPETS = (_OLD_CODEX_SNIPPET, _PRE_DESCRIPTION_CODEX_SNIPPET)
_LEGACY_COPILOT_SNIPPETS = (_OLD_COPILOT_SNIPPET, _PRE_DESCRIPTION_COPILOT_SNIPPET)

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
    """Resolve the harness asset directory.

    ``explicit`` is the ``--from`` flag; otherwise the assets are the copy
    that ships inside the installed package, which is the same directory for
    a wheel and for an editable install. The package root is found by name,
    never by counting parents, so moving this module cannot break installs.
    """
    if explicit is not None:
        return explicit
    package_root = next(parent for parent in Path(__file__).parents if parent.name == "memex")
    bundled = package_root / "marketplace"
    if bundled.is_dir():
        return bundled
    raise FileNotFoundError(
        "marketplace assets are missing from the memex package. "
        "Reinstall from source: uv tool install . --force"
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


@dataclass(slots=True)
class UninstallReport:
    """Memex adapter changes removed without deleting the memory store."""

    harness: str
    files_removed: list[str] = field(default_factory=list)
    files_updated: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _backup(path: Path, *, suffix: str = ".memex-bak") -> None:
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + suffix))


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
    legacy = next((old for old in _LEGACY_CLAUDE_SNIPPETS if old in existing_rules), None)
    if snippet in existing_rules:
        report.notes.append("CLAUDE.md already contains the memory contract")
    elif legacy is not None:
        _backup(rules_path)
        rules_path.write_text(existing_rules.replace(legacy, snippet, 1), encoding="utf-8")
        report.files_merged.append(str(rules_path))
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
    legacy = next((old for old in _LEGACY_CODEX_SNIPPETS if old in existing_agents), None)
    if legacy is not None:
        _backup(agents)
        agents.write_text(existing_agents.replace(legacy, snippet, 1), encoding="utf-8")
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
    legacy = next((old for old in _LEGACY_COPILOT_SNIPPETS if old in existing_instructions), None)
    if legacy is not None:
        _backup(instructions)
        instructions.write_text(existing_instructions.replace(legacy, snippet, 1), encoding="utf-8")
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


def _remove_owned_file(path: Path, source: Path, report: UninstallReport) -> None:
    if not path.exists():
        return
    if path.is_symlink() or path.read_bytes() != source.read_bytes():
        report.notes.append(f"{path} changed since install; left untouched")
        return
    path.unlink()
    report.files_removed.append(str(path))


def _remove_snippet(path: Path, snippets: tuple[str, ...], report: UninstallReport) -> None:
    if not path.exists():
        return
    if path.is_symlink():
        report.notes.append(f"{path} is a symlink; left untouched")
        return
    original = path.read_text(encoding="utf-8")
    updated = original
    for snippet in snippets:
        if snippet in updated:
            updated = (
                updated.replace("\n\n" + snippet, "\n", 1)
                if "\n\n" + snippet in updated
                else updated.replace(snippet, "", 1)
            )
            break
    if updated == original:
        report.notes.append(f"{path} has no exact Memex snippet; left untouched")
        return
    _backup(path, suffix=".memex-uninstall-bak")
    if updated.strip():
        path.write_text(updated, encoding="utf-8")
        report.files_updated.append(str(path))
    else:
        path.unlink()
        report.files_removed.append(str(path))


def _remove_claude_hooks(path: Path, report: UninstallReport) -> None:
    if not path.exists():
        return
    if path.is_symlink():
        report.notes.append(f"{path} is a symlink; left untouched")
        return
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        report.notes.append(f"{path} is not valid JSON; left untouched")
        return
    if not isinstance(settings, dict) or not isinstance(settings.get("hooks"), dict):
        return
    hooks = settings["hooks"]
    commands = {
        "SessionStart": "memex hook session-start",
        "UserPromptSubmit": "memex hook prompt",
        "SessionEnd": "memex hook transcript --harness claude",
    }
    changed = False
    for event, command in commands.items():
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                kept.append(group)
                continue
            remaining = [
                hook
                for hook in group["hooks"]
                if not (
                    isinstance(hook, dict)
                    and hook.get("type") == "command"
                    and hook.get("command") == command
                )
            ]
            if len(remaining) != len(group["hooks"]):
                changed = True
                if remaining or len(group) > 1:
                    kept.append({**group, "hooks": remaining})
            else:
                kept.append(group)
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    if not changed:
        return
    if not hooks:
        settings.pop("hooks")
    _backup(path, suffix=".memex-uninstall-bak")
    if settings:
        path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        report.files_updated.append(str(path))
    else:
        path.unlink()
        report.files_removed.append(str(path))


def _unregister_claude_mcp(home: Path, report: UninstallReport) -> None:
    if home != Path.home():
        report.notes.append(
            "Claude MCP registration uses the real home; skipped for --home override"
        )
        return
    claude_bin = shutil.which("claude")
    if claude_bin is None:
        report.notes.append(
            "Claude CLI unavailable; remove user MCP entry with `claude mcp remove memex -s user`"
        )
        return
    try:
        listing = subprocess.run(  # noqa: S603 - executable resolved from PATH
            [claude_bin, "mcp", "get", "memex"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        report.notes.append("Claude MCP lookup failed; user entry left untouched")
        return
    if listing.returncode != 0:
        return
    lines = {line.strip() for line in listing.stdout.splitlines()}
    if (
        not {
            "Scope: User config (available in all your projects)",
            "Command: memex",
            "Args: serve-mcp",
        }
        <= lines
    ):
        report.notes.append("Claude MCP entry differs from Memex install; left untouched")
        return
    try:
        removed = subprocess.run(  # noqa: S603 - executable resolved from PATH
            [claude_bin, "mcp", "remove", "memex", "-s", "user"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        report.notes.append("Claude MCP removal failed; user entry remains")
        return
    if removed.returncode == 0:
        report.notes.append("Claude user MCP entry removed")
    else:
        report.notes.append("Claude MCP removal failed; user entry remains")


def _uninstall_claude(
    marketplace: Path, home: Path, project: Path, report: UninstallReport
) -> None:
    _remove_claude_hooks(home / ".claude" / "settings.json", report)
    snippet = (marketplace / "claude" / "CLAUDE-snippet.md").read_text(encoding="utf-8")
    _remove_snippet(project / "CLAUDE.md", (snippet, *_LEGACY_CLAUDE_SNIPPETS), report)
    _unregister_claude_mcp(home, report)


def _remove_codex_config(path: Path, wrapper: Path, report: UninstallReport) -> bool:
    if not path.exists():
        return True
    if path.is_symlink():
        report.notes.append(f"{path} is a symlink; left untouched")
        return False
    original = path.read_text(encoding="utf-8")
    try:
        parsed = tomllib.loads(original)
    except tomllib.TOMLDecodeError:
        report.notes.append(f"{path} is not valid TOML; left untouched")
        return False
    lines = original.splitlines(keepends=True)
    notify_line = f'notify = ["{wrapper}"]'
    has_installed_notify = notify_line in {line.strip() for line in lines}
    if str(wrapper) in original and not has_installed_notify:
        report.notes.append(f"{path} still references the Memex notify wrapper; left untouched")
        return False
    if has_installed_notify:
        lines = [line for line in lines if line.strip() != notify_line]
    servers = parsed.get("mcp_servers")
    server = servers.get("memex") if isinstance(servers, dict) else None
    if server is not None and server != {"command": "memex", "args": ["serve-mcp"]}:
        report.notes.append(f"{path} has a modified Memex MCP entry; left untouched")
    elif server == {"command": "memex", "args": ["serve-mcp"]}:
        start = next(
            (i for i, line in enumerate(lines) if line.strip() == "[mcp_servers.memex]"), None
        )
        if start is not None:
            end = next(
                (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
                len(lines),
            )
            del lines[start:end]
    updated = "".join(lines)
    if updated != original:
        _backup(path, suffix=".memex-uninstall-bak")
        if updated.strip():
            path.write_text(updated, encoding="utf-8")
            report.files_updated.append(str(path))
        else:
            path.unlink()
            report.files_removed.append(str(path))
    return str(wrapper) not in updated


def _uninstall_codex(marketplace: Path, home: Path, project: Path, report: UninstallReport) -> None:
    wrapper = home / ".codex" / "memex-codex-notify.py"
    if _remove_codex_config(home / ".codex" / "config.toml", wrapper, report):
        _remove_owned_file(wrapper, marketplace / "codex" / "memex-codex-notify.py", report)
    snippet = (marketplace / "codex" / "AGENTS-snippet.md").read_text(encoding="utf-8")
    _remove_snippet(project / "AGENTS.md", (snippet, *_LEGACY_CODEX_SNIPPETS), report)


def _uninstall_pi(marketplace: Path, home: Path, project: Path, report: UninstallReport) -> None:
    _remove_owned_file(
        home / ".pi" / "agent" / "extensions" / "memex.ts",
        marketplace / "pi" / "extensions" / "memex.ts",
        report,
    )


def _uninstall_copilot(
    marketplace: Path, home: Path, project: Path, report: UninstallReport
) -> None:
    _remove_owned_file(
        project / ".github" / "workflows" / "memex-verify.yml",
        marketplace / "copilot" / "memex-verify.yml",
        report,
    )
    snippet = (marketplace / "copilot" / "copilot-instructions-snippet.md").read_text(
        encoding="utf-8"
    )
    _remove_snippet(
        project / ".github" / "copilot-instructions.md",
        (snippet, *_LEGACY_COPILOT_SNIPPETS),
        report,
    )
    path = project / ".vscode" / "mcp.json"
    if not path.exists():
        return
    if path.is_symlink():
        report.notes.append(f"{path} is a symlink; left untouched")
        return
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        report.notes.append(f"{path} is not valid JSON; left untouched")
        return
    if not isinstance(config, dict) or not isinstance(config.get("servers"), dict):
        return
    servers = config["servers"]
    if "memex" not in servers:
        return
    if servers["memex"] != {"command": "memex", "args": ["serve-mcp"]}:
        report.notes.append(f"{path} has a modified Memex MCP entry; left untouched")
        return
    del servers["memex"]
    if not servers:
        del config["servers"]
    _backup(path, suffix=".memex-uninstall-bak")
    if config:
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        report.files_updated.append(str(path))
    else:
        path.unlink()
        report.files_removed.append(str(path))


_UNINSTALLERS = {
    "pi": _uninstall_pi,
    "claude": _uninstall_claude,
    "codex": _uninstall_codex,
    "copilot": _uninstall_copilot,
}

_UNINSTALL_ASSETS = {
    "pi": ("pi/extensions/memex.ts",),
    "claude": ("claude/CLAUDE-snippet.md",),
    "codex": ("codex/memex-codex-notify.py", "codex/AGENTS-snippet.md"),
    "copilot": ("copilot/memex-verify.yml", "copilot/copilot-instructions-snippet.md"),
}

_UNINSTALL_TARGETS = {
    "pi": (("home", ".pi/agent/extensions/memex.ts"),),
    "claude": (("home", ".claude/settings.json"), ("project", "CLAUDE.md")),
    "codex": (
        ("home", ".codex/config.toml"),
        ("home", ".codex/memex-codex-notify.py"),
        ("project", "AGENTS.md"),
    ),
    "copilot": (
        ("project", ".github/workflows/memex-verify.yml"),
        ("project", ".github/copilot-instructions.md"),
        ("project", ".vscode/mcp.json"),
    ),
}


def uninstall_harness(
    harness: str, marketplace: Path, *, home: Path, project: Path
) -> UninstallReport:
    """Remove exact adapter entries; keep memories and modified files."""
    if harness == "custom":
        return UninstallReport(
            harness="custom", notes=["No adapter to remove; Memex data retained"]
        )
    try:
        uninstaller = _UNINSTALLERS[harness]
    except KeyError:
        raise ValueError(f"unknown harness {harness!r}; expected one of {SUPPORTED}") from None
    if not marketplace.is_dir():
        raise FileNotFoundError(f"marketplace directory not found: {marketplace}")
    for relative in _UNINSTALL_ASSETS[harness]:
        asset = marketplace / relative
        if not asset.is_file():
            raise FileNotFoundError(f"marketplace asset not found: {asset}")
    for root_name, relative in _UNINSTALL_TARGETS[harness]:
        root = home if root_name == "home" else project
        path = root / relative
        if not path.resolve(strict=False).is_relative_to(root.resolve(strict=False)):
            raise ValueError(f"uninstall target leaves its root: {path}")
    report = UninstallReport(harness=harness)
    uninstaller(marketplace, home, project, report)
    return report


def _memex_data_dir() -> Path:
    import os

    return Path(os.environ.get("MEMEX_DATA_DIR", str(Path.home() / ".memex"))).expanduser()
