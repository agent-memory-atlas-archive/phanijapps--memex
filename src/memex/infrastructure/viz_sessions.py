"""Composed session list and replay fragments for the local dashboard."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote

from memex.infrastructure.markdown import render_markdown
from memex.infrastructure.viz_components import escape

TOOL_PREVIEW_CHARS = 500
TOOL_DISPLAY_CHARS = 2000


@dataclass(frozen=True)
class SessionView:
    session_id: str
    day: str
    started_at: str
    turn_count: int
    episode_slug: str | None
    project_label: str
    harness: str


def render_session_groups(sessions: list[SessionView]) -> str:
    """Group by capture day, then project and harness, newest days first."""
    groups: dict[str, dict[tuple[str, str], list[SessionView]]] = {}
    for session in sessions:
        groups.setdefault(session.day, {}).setdefault(
            (session.project_label, session.harness), []
        ).append(session)
    sections = ['<h1 class="page-heading">Captured sessions</h1>']
    for day in sorted(groups, reverse=True):
        sections.append(f'<section><h2 class="session-day">{escape(day)}</h2>')
        for project, harness in sorted(
            groups[day], key=lambda pair: (pair[0].casefold(), pair[1].casefold())
        ):
            cards = []
            for session in sorted(
                groups[day][(project, harness)],
                key=lambda item: item.started_at,
                reverse=True,
            ):
                sid = escape(session.session_id)
                url = "/session/" + quote(session.session_id, safe="")
                direct = escape("/view" + url)
                episode = (
                    f'<span class="meta">Episode: {escape(session.episode_slug)}</span>'
                    if session.episode_slug
                    else ""
                )
                cards.append(
                    f'<a class="session-card" href="{direct}" hx-get="{escape(url)}" '
                    f'hx-target="#panel-body"><strong>{sid}</strong>'
                    f'<span class="subtle">{escape(session.started_at[11:16] or "Unknown time")} · '
                    f"{session.turn_count} turns</span>{episode}</a>"
                )
            sections.append(
                '<div class="session-group">'
                f'<h3 class="session-group-title">{escape(project)} · {escape(harness)}</h3>'
                '<div class="session-grid">' + "".join(cards) + "</div></div>"
            )
        sections.append("</section>")
    return "".join(sections)


def _tool_field(label: str, value: object) -> str:
    if value is None or value == "":
        return ""
    content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    preview = escape(content[:TOOL_PREVIEW_CHARS])
    rest = escape(content[TOOL_PREVIEW_CHARS:TOOL_DISPLAY_CHARS])
    clipped = len(content) > TOOL_DISPLAY_CHARS
    truncation = (
        f'<span class="subtle">Truncated after {TOOL_DISPLAY_CHARS:,} characters</span>'
        if clipped
        else ""
    )
    details = (
        f"<details><summary>Show more {label.lower()}</summary>"
        f"<pre>{rest}</pre>{truncation}</details>"
        if rest or clipped
        else ""
    )
    return f'<div class="tool-result"><strong>{label}</strong><br>{preview}{details}</div>'


def render_replay(turns: list[dict[str, object]], meta: dict[str, object]) -> str:
    """Render only known role cards; every untrusted value is escaped."""
    cards = []
    for turn in turns:
        role = str(turn.get("role", ""))
        if role not in {"user", "agent", "tool"}:
            continue
        label = {"user": "User", "agent": "AI assistant", "tool": "Tool"}[role]
        icon = {"user": "U", "agent": "AI", "tool": "T"}[role]
        timestamp = turn.get("ts")
        time_html = f'<span class="timestamp">{escape(timestamp)}</span>' if timestamp else ""
        heading = f'<div class="role">{label}{time_html}</div>'
        if role == "agent":
            rendered = render_markdown(str(turn.get("content") or ""))
            content = f'<div class="content">{rendered}</div>'
        elif role == "user":
            content = f'<div class="content">{escape(turn.get("content") or "")}</div>'
        else:
            name = f'<span class="tool-name">{escape(turn.get("tool_name") or "")}</span>'
            content = (
                name
                + _tool_field("Content", turn.get("content"))
                + _tool_field("Input", turn.get("query"))
                + _tool_field("Result", turn.get("result"))
            )
        cards.append(
            f'<article class="turn {role}"><span class="turn-icon" aria-hidden="true">'
            f"{icon}</span><div>{heading}{content}</div></article>"
        )
    if not cards:
        return '<div class="empty">Transcript has no replayable turns</div>'
    summary = (
        f'<p class="subtle">{escape(meta.get("turn_count", len(cards)))} turns · '
        f"started {escape(str(meta.get('started_at') or 'Unknown')[:16])} · "
        f"harness {escape(meta.get('harness') or 'Unknown')}</p>"
    )
    return (
        '<h1 class="page-heading">Session replay</h1>'
        + summary
        + '<div class="timeline">'
        + "".join(cards)
        + "</div>"
    )
