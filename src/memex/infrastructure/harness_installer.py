"""Installer for per-harness adapters from the marketplace directory.

The marketplace files are the source of truth; the installer copies or
merges them into each harness's configuration. All writes are
idempotent (a second install is a no-op) and preceded by a backup.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED = ("pi", "claude", "codex", "copilot", "custom")

_MEMEX_MARKER = "memex"

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
    (data_dir / "wiki").mkdir(parents=True, exist_ok=True)
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


def _install_claude(marketplace: Path, home: Path, project: Path, report: InstallReport) -> None:
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
    report.notes.append("MCP: run `claude mcp add memex -- memex serve-mcp` once")


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
    additions = ""
    if "memex-codex-notify" not in existing:
        additions += f'notify = ["{wrapper}"]\n'
    if "[mcp_servers.memex]" not in existing:
        additions += '\n[mcp_servers.memex]\ncommand = "memex"\nargs = ["serve-mcp"]\n'
    if additions:
        if existing and not existing.endswith("\n"):
            existing += "\n"
        config_path.write_text(existing + additions, encoding="utf-8")
        report.files_merged.append(str(config_path))
    else:
        report.notes.append("config.toml already wired; left unchanged")

    agents = project / "AGENTS.md"
    snippet = (marketplace / "codex" / "AGENTS-snippet.md").read_text(encoding="utf-8")
    if agents.exists() and "memex hook session-start" in agents.read_text(encoding="utf-8"):
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
    if instructions.exists() and "memex" in instructions.read_text(encoding="utf-8"):
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


def install_harness(harness: str, marketplace: Path, *, home: Path, project: Path) -> InstallReport:
    """Install one harness adapter from the marketplace directory."""
    if harness == "custom":
        return init_memex(_memex_data_dir())
    try:
        installer = _INSTALLERS[harness]
    except KeyError:
        raise ValueError(f"unknown harness {harness!r}; expected one of {SUPPORTED}") from None
    if not marketplace.is_dir():
        raise FileNotFoundError(f"marketplace directory not found: {marketplace}")
    report = InstallReport(harness=harness)
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
