"""Harness-piggybacked episode enrichment.

Instead of a separate LLM API call, the already-running harness CLI
(codex/claude/pi) summarizes the session — no API key, no separate client.
Rides the harness's own model and billing. Idempotent: episodes already
carrying enrichment are skipped.
"""

from __future__ import annotations

import subprocess

from memex.domain.models import TurnStreamEntry

# Marker in the episode front matter / body that enrichment already ran
ENRICHMENT_MARKER = "<!-- enriched -->"

_HARNESS_COMMANDS: dict[str, list[str]] = {
    "codex": ["codex", "exec", "--skip-git-repo-check"],
    "claude": ["claude", "-p", "--output-format", "text"],
    "pi": ["pi", "-p"],
}

ENRICH_PROMPT = """Summarize this coding session in 2-3 sentences.
State: what was asked, what was decided or built, what was learned.
Be specific. No preamble, no headers, just the sentences.

Session turns (user and agent only, tools filtered):

{turns}"""

_TURN_CHARS = 6000
_TIMEOUT = 120


def is_enriched(body: str) -> bool:
    """True when the episode body already carries LLM enrichment."""
    return ENRICHMENT_MARKER in body


def enrich_episode(
    harness: str,
    turns: list[TurnStreamEntry],
) -> str | None:
    """Ask the harness CLI to summarize the session. None on failure.

    The harness is already running (the hook fired from its lifecycle), so
    this piggybacks on its model, credentials, and billing — no separate
    LLM call, no API key.
    """
    import shutil

    base = _HARNESS_COMMANDS.get(harness)
    if base is None:
        return None
    binary = shutil.which(base[0])
    if binary is None:
        return None

    # Build the conversation excerpt: user + agent turns only
    parts: list[str] = []
    for turn in turns:
        if turn.role in ("user", "agent"):
            content = turn.content[:500]
            if content.strip():
                parts.append(f"[{turn.role}] {content}")
    text = "\n".join(parts)[:_TURN_CHARS]
    if not text.strip():
        return None

    prompt = ENRICH_PROMPT.format(turns=text)
    try:
        completed = subprocess.run(  # noqa: S603 - harness CLI, argv built locally
            [*base, prompt],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None

    summary = completed.stdout.strip()
    if len(summary) < 20:  # too short to be a real summary
        return None
    return summary


def enriched_body(summary: str, original: str) -> str:
    """Wrap an LLM summary with the enrichment marker, keeping the original."""
    return f"{ENRICHMENT_MARKER}\n\n{summary}\n\n---\n\n{original}"
