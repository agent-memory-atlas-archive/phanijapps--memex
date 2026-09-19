"""Best-effort workspace context for recall queries (git-derived)."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from memex.domain.slugs import derive_slug

_GIT = shutil.which("git") or "/usr/bin/git"


@dataclass(frozen=True, slots=True)
class ProjectContext:
    project_id: str
    label: str
    locator: str


def _git(cwd: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            [_GIT, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip()


def session_query(cwd: Path) -> str:
    """Repo name, branch, and last commit subject — recall hints, never errors."""
    parts = [cwd.name]
    branch = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if branch:
        parts.append(branch)
    subject = _git(cwd, "log", "-1", "--pretty=%s")
    if subject:
        parts.append(subject)
    return " ".join(parts)


def project_context(cwd: Path) -> ProjectContext:
    """Return a stable, private project identifier and safe display label.

    A Git remote is preferred as the identity source.  Its value, credentials,
    hostname, and local fallback path are never returned or persisted: only a
    SHA-256-derived identifier is exposed.  A non-Git directory uses its
    resolved path solely as hash input and displays its final folder name.  The
    locator is a non-persisted, safe directory name for new project pages.
    """
    root_value = _git(cwd, "rev-parse", "--show-toplevel")
    root = Path(root_value) if root_value else cwd.resolve()
    remote = _git(root, "remote", "get-url", "origin")
    identity_source = _normalized_remote(remote) if remote else str(root)
    project_id = hashlib.sha256(identity_source.encode("utf-8")).hexdigest()[:24]
    label = root.name or cwd.name
    locator = _remote_locator(remote) if remote else _folder_locator(label)
    return ProjectContext(project_id=project_id, label=label, locator=locator)


def project_identity(cwd: Path) -> tuple[str, str]:
    """Backward-compatible project identifier and display label."""
    context = project_context(cwd)
    return context.project_id, context.label


def _normalized_remote(remote: str) -> str:
    """Normalize Git remote forms while discarding credentials before hashing."""
    value = remote.strip()
    if "://" in value:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        path = parsed.path.rstrip("/").removesuffix(".git")
        return f"{host}{path}"
    if "@" in value and ":" in value:
        value = value.split("@", 1)[1].replace(":", "/", 1)
    return value.rstrip("/").removesuffix(".git").lower()


def _remote_locator(remote: str) -> str:
    repo = Path(_normalized_remote(remote)).name or "project"
    return f"git-{derive_slug(repo, algo='kebab') or 'project'}"


def _folder_locator(name: str) -> str:
    return derive_slug(name, algo="kebab") or "project"
