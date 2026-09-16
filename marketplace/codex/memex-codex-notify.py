#!/usr/bin/env python3
"""Codex lifecycle hook: capture rollout transcripts into memex.

Handles three Codex events, each delivered as JSON on stdin:
agent-turn-complete, PostCompact, and SessionEnd. The payload's
session_id and transcript_path address the session directly — the
globally newest rollout is only a fallback when the payload identifies
neither.

Timing: Codex's SessionEnd teardown allows 1-3 seconds, so that event
performs a fast handoff — memex is spawned detached (its own session)
and the hook returns immediately; reconciliation happens moments later
in the detached process. Turn-complete and PostCompact run synchronously
with a generous timeout.

Diagnostics: one JSON line per capture attempt is appended to
<MEMEX_DATA_DIR>/logs/codex-capture.log with the event name, session id,
and an error category. Transcript text and tool arguments are never
logged. Every hook failure is nonblocking: the wrapper exits 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

MEMEX_BIN = os.environ.get("MEMEX_BIN", "memex")
SYNC_TIMEOUT_S = 90
# Categories: ok | timeout | nonzero | missing_path | bad_input | spawn_error


def _data_dir() -> Path:
    return Path(os.environ.get("MEMEX_DATA_DIR", str(Path.home() / ".memex"))).expanduser()


def _log(event: str, session_id: str, category: str, detail: str = "") -> None:
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "session_id": session_id,
        "category": category,
    }
    if detail:
        entry["detail"] = detail[:120]  # category text only; never content
    try:
        log_dir = _data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "codex-capture.log").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _event_name(payload: dict[str, object]) -> str:
    raw = str(payload.get("type") or payload.get("event") or "")
    return raw.strip().lower().replace("_", "-")


def _field(payload: dict[str, object], *names: str) -> str | None:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def _rollout_for_session(session_id: str) -> str | None:
    """Newest rollout whose filename embeds the session id (never the
    globally newest file when a session is identified)."""
    sessions = Path.home() / ".codex" / "sessions"
    if not sessions.is_dir():
        return None
    matches = sorted(
        sessions.rglob(f"*{session_id}*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return str(matches[0]) if matches else None


def _capture_args(event: str, payload: dict[str, object]) -> list[str] | None:
    session_id = _field(payload, "session_id", "session-id", "thread_id", "thread-id") or ""
    path = _field(payload, "transcript_path", "transcript-path", "rollout_path", "rollout-path")
    if path is None and session_id:
        path = _rollout_for_session(session_id)
    if path is None:
        _log(event, session_id, "missing_path")
        return None
    args = [MEMEX_BIN, "hook", "transcript", "--harness", "codex", "--path", path]
    if session_id:
        args += ["--session-id", session_id]
    return args


def _run_sync(event: str, session_id: str, args: list[str]) -> None:
    try:
        completed = subprocess.run(  # noqa: S603 - argv built locally
            args, capture_output=True, text=True, timeout=SYNC_TIMEOUT_S, check=False
        )
    except subprocess.TimeoutExpired:
        _log(event, session_id, "timeout")
        return
    except OSError:
        _log(event, session_id, "spawn_error")
        return
    category = "ok" if completed.returncode == 0 else "nonzero"
    _log(event, session_id, category, f"exit {completed.returncode}")


def _handoff_detached(event: str, session_id: str, args: list[str]) -> None:
    """Fast handoff for SessionEnd: return immediately, capture later."""
    try:
        subprocess.Popen(  # noqa: S603 - argv built locally
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _log(event, session_id, "ok", "detached")
    except OSError:
        _log(event, session_id, "spawn_error")


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        # Legacy turn-complete transport: JSON as argv[1].
        raw = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        _log("unknown", "", "bad_input")
        return 0
    if not isinstance(payload, dict):
        _log("unknown", "", "bad_input")
        return 0

    event = _event_name(payload)
    session_id = _field(payload, "session_id", "session-id", "thread_id", "thread-id") or ""

    if "turn-complete" in event:
        kind = "sync"
    elif "compact" in event:
        kind = "sync"
    elif "session-end" in event or "sessionend" in event:
        kind = "detached"
    else:
        return 0  # unrelated event: never block

    args = _capture_args(event, payload)
    if args is None:
        return 0
    if kind == "sync":
        _run_sync(event, session_id, args)
    else:
        _handoff_detached(event, session_id, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
