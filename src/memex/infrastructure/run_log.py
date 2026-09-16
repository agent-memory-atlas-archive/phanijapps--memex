"""Append-only run log at ~/.memex/logs/runs.jsonl.

One JSON line per consolidation or capture run. This is the data source
`memex status`, zero-yield warnings, and cwd-attribution guards read;
nothing else parses it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RUN_LOG = "runs.jsonl"

VALID_KINDS = ("consolidation", "capture")


def append_run(data_dir: Path, entry: dict[str, Any]) -> None:
    """Append one run record; kind must be consolidation or capture."""
    if entry.get("kind") not in VALID_KINDS:
        raise ValueError(f"run kind must be one of {VALID_KINDS}")
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / RUN_LOG).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def read_runs(data_dir: Path) -> list[dict[str, Any]]:
    """All run records, oldest first; unreadable lines are skipped."""
    path = data_dir / "logs" / RUN_LOG
    if not path.exists():
        return []
    runs: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            runs.append(entry)
    return runs


def zero_yield_streak(runs: list[dict[str, Any]]) -> int:
    """Count of consecutive zero-node consolidation runs, newest first."""
    streak = 0
    for run in reversed(runs):
        if run.get("kind") != "consolidation":
            continue
        if int(run.get("nodes_created", 0) or 0) == 0:
            streak += 1
        else:
            break
    return streak
