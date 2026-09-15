#!/usr/bin/env python3
"""Codex notify hook: capture rollout transcripts into memex.

Codex invokes this program with one argument: a JSON event object. On
`agent-turn-complete` the newest rollout session file is ingested as a
memex transcript (episode node + provenance). Best-effort by design:
any failure exits 0 and never disturbs the Codex session.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def newest_rollout() -> str | None:
    sessions = Path.home() / ".codex" / "sessions"
    if not sessions.is_dir():
        return None
    files = sorted(
        sessions.rglob("rollout-*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return str(files[0]) if files else None


def main() -> int:
    if len(sys.argv) < 2:
        return 0
    try:
        event = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        return 0
    if not isinstance(event, dict) or event.get("type") != "agent-turn-complete":
        return 0

    rollout = (
        event.get("rollout-path")
        or event.get("rollout_path")
        or event.get("session-file")
        or newest_rollout()
    )
    if not rollout:
        return 0
    try:
        subprocess.run(
            ["memex", "hook", "transcript", "--harness", "codex", "--path", rollout],
            timeout=60,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
