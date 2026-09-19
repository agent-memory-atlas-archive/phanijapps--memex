"""Reusable presentation primitives for the local dashboard."""

# ruff: noqa: E501

from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit


def escape(value: object) -> str:
    """Escape an untrusted value at the HTML boundary."""
    return html.escape(str(value if value is not None else ""))


def project_label(scope: str, label: str | None) -> str:
    """Render safe scope context without disclosing an opaque identifier."""
    return "Global" if scope == "global" else escape(label or "Project")


def scope_controls(projects: dict[str, str], selected: str | None, route: str) -> str:
    """Offer all, global-only, and project views with ordinary and HTMX links."""
    parsed = urlsplit(route)
    base = parsed.path
    base_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    base_params.pop("page", None)
    base_params.pop("scope", None)
    base_params.pop("project", None)
    controls = []
    global_label = "Search everywhere" if base == "/search" else "Global only"
    best_label = "Best match" if base == "/search" else "All memory"
    options = [("best", best_label), ("global", global_label)]
    options.extend(
        (project_id, label)
        for project_id, label in sorted(projects.items(), key=lambda item: item[1].casefold())
    )
    for value, label in options:
        params = {**base_params, "scope": "project" if value not in {"best", "global"} else value}
        if value not in {"best", "global"}:
            params["project"] = value
        fragment = base + "?" + urlencode(params)
        direct = fragment.replace(base, "/view/memories" if base == "/pages" else "/view/search", 1)
        target = "#main" if base == "/pages" else "#search-results"
        current = ' aria-current="true"' if selected == value else ""
        controls.append(
            f'<a href="{escape(direct)}" hx-get="{escape(fragment)}" hx-target="{target}" '
            f'hx-push-url="{escape(direct)}"{current}>{escape(label)}</a>'
        )
    return (
        '<div class="filters scope-controls" aria-label="Memory scope">'
        + " ".join(controls)
        + "</div>"
    )


PAGE_SHELL = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>memex dashboard</title><link rel="stylesheet" href="/style.css"><script src="/htmx.js"></script></head>
<body><div class="app-shell"><aside class="sidebar"><a class="brand" href="/">memex</a>
<nav aria-label="Dashboard">
<a href="/" hx-get="/overview" hx-target="#main" hx-push-url="/">Overview</a>
<a href="/view/memories" hx-get="/pages" hx-target="#main" hx-push-url="/view/memories">Memories</a>
<a href="/view/sessions" hx-get="/sessions" hx-target="#main" hx-push-url="/view/sessions">Sessions</a>
<a href="/view/tokens" hx-get="/tokens" hx-target="#main" hx-push-url="/view/tokens">Tokens</a>
</nav></aside>
<div class="workspace"><header class="topbar"><div><span>Workspace / Dashboard</span>
<strong>Local memory explorer</strong></div><span>Read only · stored on this device</span></header>
<main id="main">@@INITIAL_CONTENT@@</main></div></div>
<div class="panel-backdrop" id="panel-backdrop" onclick="closePanel()"></div>
<aside class="panel" id="panel" aria-label="Detail panel" aria-modal="true" role="dialog">
<div class="panel-header"><h2 id="panel-title">Detail</h2>
<button class="panel-close" aria-label="Close detail" onclick="closePanel()">&times;</button></div>
<div class="panel-body" id="panel-body"></div></aside>
<script>
let previousFocus;
function closePanel(){
  document.getElementById('panel').classList.remove('open');
  document.getElementById('panel-backdrop').classList.remove('open');
  if(previousFocus)previousFocus.focus();
}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closePanel()});
document.addEventListener('htmx:beforeRequest',e=>{
  if(e.detail.elt.getAttribute('hx-target')==='#panel-body')previousFocus=e.detail.elt;
});
document.addEventListener('htmx:afterSwap',e=>{
  if(e.detail.target.id==='panel-body'){
    const h=e.detail.target.querySelector('h1,h2,h3');
    document.getElementById('panel-title').textContent=h?h.textContent:'Detail';
    document.getElementById('panel').classList.add('open');
    document.getElementById('panel-backdrop').classList.add('open');
    document.querySelector('.panel-close').focus();
  }
});
</script></body></html>"""


DASHBOARD_CSS = (Path(__file__).parent / "dashboard.css").read_text(encoding="utf-8")
