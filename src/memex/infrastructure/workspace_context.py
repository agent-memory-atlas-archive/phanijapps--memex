"""Best-effort workspace context for recall queries (git-derived)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_GIT = shutil.which("git") or "/usr/bin/git"


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
