"""On-demand HTMX dashboard for the memex memory store.

`memex viz` starts a localhost HTTP server that renders existing surfaces
(docs pages, session metadata, run log, index stats) as an interactive
dashboard. Read-only: the filesystem is the truth, this is a projection.

Zero new dependencies: stdlib http.server + vendored HTMX + hand-written
CSS + server-rendered SVG charts. Stops when the process stops.
"""

from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from memex.application.memory import Memex
from memex.infrastructure.config import MemexConfig

DEFAULT_PORT = 7171

# Vendored HTMX (minimal subset: hx-get, hx-trigger, hx-swap, hx-target)
_HTMX = """(function(){'use strict';function l(t){return t.closest('[hx-target]')||t.closest('[hx-get]')}
function f(e){var t=l(e.target);if(!t)return;var u=t.getAttribute('hx-get');if(!u)return;
var g=t.getAttribute('hx-target');var s=t.getAttribute('hx-swap')||'innerHTML';
var r=new XMLHttpRequest();r.open('GET',u);r.onload=function(){if(r.status==200){
var el=g?document.querySelector(g):t;if(el){if(s=='outerHTML'){el.outerHTML=r.responseText}
else{el.innerHTML=r.responseText}}}};r.send();e.preventDefault()}
document.addEventListener('click',f);
var iv=setInterval(function(){document.querySelectorAll('[hx-trigger]').forEach(function(el){
var tr=el.getAttribute('hx-trigger');if(tr&&tr.indexOf('every')>-1){var ms=parseInt(tr.match(/\\d+s/)?.[0])||5000;
if(!el._iv){el._iv=setInterval(function(){var u=el.getAttribute('hx-get');if(u){
var r=new XMLHttpRequest();r.open('GET',u);r.onload=function(){if(r.status==200){
var g=el.getAttribute('hx-target');var el2=g?document.querySelector(g):el;
if(el2)el2.innerHTML=r.responseText}};r.send()}},ms*1000)}}})},1000)})();"""

_CSS = """
:root{--ink:#1e293b;--teal:#0f766e;--bg:#f8fafc;--card:#fff;--border:#e2e8f0;--muted:#64748b}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--ink);padding:1.5rem}
h1{font-size:1.4rem;margin-bottom:.2rem}h2{font-size:1rem;color:var(--teal);margin:1.2rem 0 .5rem}
.sub{color:var(--muted);font-size:.85rem;margin-bottom:1rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1rem}
.card{background:var(--card);border:1px solid var(--border);border-radius:.5rem;padding:1rem}
.card h3{font-size:.9rem;margin-bottom:.3rem}
.badge{display:inline-block;padding:.1rem .5rem;border-radius:.35rem;font-size:.75rem;font-weight:600}
.badge.active{background:#ccfbf1;color:#0f766e}.badge.pending{background:#fef3c7;color:#92400e}
.badge.archived{background:#e2e8f0;color:#475569}.badge.superseded{background:#fce7f3;color:#9d174d}
.meta{font-size:.78rem;color:var(--muted);margin-top:.3rem}
.search{width:100%;padding:.6rem .8rem;border:1px solid var(--border);border-radius:.4rem;
font-size:.9rem;margin-bottom:.8rem;background:var(--card)}
table{width:100%;border-collapse:collapse;font-size:.82rem}
th{text-align:left;color:var(--muted);border-bottom:1px solid var(--border);padding:.4rem .5rem}
td{padding:.4rem .5rem;border-bottom:1px solid var(--border)}
.bar{fill:var(--teal);rx:2}
.chart{width:100%;height:auto}
.stat{font-size:1.8rem;font-weight:700;color:var(--teal)}
.stat-label{font-size:.75rem;color:var(--muted)}
a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}
.snippet{font-size:.8rem;color:var(--muted);margin-top:.2rem;max-height:3em;overflow:hidden}
mark{background:#fef08a;padding:0 .1rem;border-radius:.15rem}
"""


class VizHandler(BaseHTTPRequestHandler):
    """Routes: / (dashboard), /pages, /search, /sessions, /health, /htmx.js, /style.css"""

    memex: Memex | None = None  # set by serve()

    def do_GET(self) -> None:
        url = urlparse(self.path)
        route = url.path.rstrip("/") or "/"
        qs = parse_qs(url.query)

        if route == "/htmx.js":
            self._text(_HTMX, "application/javascript")
        elif route == "/style.css":
            self._text(_CSS, "text/css")
        elif route == "/":
            self._text(self._page_shell(), "text/html")
        elif route == "/overview":
            self._text(self._fragment_overview(), "text/html")
        elif route == "/pages":
            self._text(self._fragment_pages(qs.get("type", [None])[0]), "text/html")
        elif route == "/search":
            self._text(self._fragment_search(qs.get("q", [""])[0]), "text/html")
        elif route == "/sessions":
            self._text(self._fragment_sessions(), "text/html")
        elif route == "/tokens":
            self._text(self._fragment_tokens(), "text/html")
        elif route == "/health":
            self._text(self._fragment_health(), "text/html")
        else:
            self._text("not found", "text/plain", 404)

    def log_message(self, format: str, *args: object) -> None:
        pass  # quiet: dashboards don't need request logs

    def _text(self, body: str, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        payload = body.encode()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(body.encode())

    def _m(self) -> Memex:
        if self.memex is None:
            raise RuntimeError("viz handler not initialized")
        return self.memex

    # ------------------------------------------------------------- shell

    def _page_shell(self) -> str:
        return f"""<!DOCTYPE html>
<html><head><title>memex viz</title>
<link rel="stylesheet" href="/style.css">
<script src="/htmx.js"></script>
</head><body>
<h1>memex</h1>
<p class="sub">{html.escape(str(self._m().data_dir))}</p>
<div id="app" hx-get="/overview" hx-trigger="load" hx-swap="innerHTML"></div>
</body></html>"""

    # ---------------------------------------------------------- fragments

    def _fragment_overview(self) -> str:
        stats = self._m().status()
        return f"""
<div class="grid">
<div class="card"><div class="stat">{stats["index_total"]}</div>
<div class="stat-label">memory pages</div></div>
<div class="card"><div class="stat">{stats["pending"]}</div>
<div class="stat-label">pending approval</div></div>
<div class="card"><div class="stat">{stats["archived"]}</div>
<div class="stat-label">archived</div></div>
<div class="card"><div class="stat">{stats.get("zero_yield_streak", 0)}</div>
<div class="stat-label">zero-yield streak</div></div>
</div>
<h2>Health <span style="font-size:.75rem;color:var(--muted)">(auto-refresh 5s)</span></h2>
<div id="health" hx-get="/health" hx-trigger="every 5s"></div>
<h2>Search memories</h2>
<input class="search" type="search" placeholder="Search memories..."
  hx-get="/search" hx-trigger="keyup delay:300ms" hx-target="#results" name="q">
<div id="results"></div>
<h2>Recent memories</h2>
<div hx-get="/pages" hx-trigger="load" hx-swap="innerHTML"></div>
<h2>Sessions</h2>
<div hx-get="/sessions" hx-trigger="load" hx-swap="innerHTML"></div>
<h2>Token consumption</h2>
<div hx-get="/tokens" hx-trigger="load" hx-swap="innerHTML"></div>
"""

    def _fragment_health(self) -> str:
        stats = self._m().status()
        stale = int(stats.get("index_stale_rows", 0) or 0)
        color = "#0f766e" if stale == 0 else "#b45309"
        return f"""<div class="card" style="border-left:3px solid {color}">
<b>Index:</b> {stats["index_total"]} pages, {stale} stale &nbsp;
<b>Pending:</b> {stats["pending"]} &nbsp;
<b>Archived:</b> {stats["archived"]} &nbsp;
<b>Zero-yield:</b> {stats.get("zero_yield_streak", 0)} consecutive
</div>"""

    def _fragment_pages(self, node_type: str | None) -> str:
        nodes = self._m().wiki_store.list(node_type)
        cards = []
        for node in sorted(nodes, key=lambda n: n.updated, reverse=True)[:20]:
            badge = f'<span class="badge {node.status}">{node.status}</span>'
            tags = " ".join(f"#{t}" for t in node.tags[:4])
            cards.append(
                f'<div class="card"><h3>{html.escape(node.title)} {badge}</h3>'
                f'<div class="snippet">{html.escape(node.body[:200])}</div>'
                f'<div class="meta">{node.type} · {tags} · {node.updated[:10]} · '
                f"importance {node.importance}</div></div>"
            )
        type_filter = " ".join(
            f'<a href="#" hx-get="/pages?type={t}" hx-target="#pages-div"'
            f' style="margin-right:.5rem">{t}</a>'
            for t in ("entity", "preference", "procedure", "summary", "episode")
        )
        return (
            f'<div style="margin-bottom:.5rem">{type_filter}</div>'
            f'<div id="pages-div" class="grid">{"".join(cards)}</div>'
        )

    def _fragment_search(self, q: str) -> str:
        if not q.strip():
            return ""
        try:
            result = self._m().recall(q, top_k=8)
        except Exception:
            return '<div class="card">No results</div>'
        if not result.hits:
            return '<div class="card">No results</div>'
        rows = []
        for hit in result.hits:
            rows.append(
                f'<div class="card"><h3><a href="#">{html.escape(hit.title)}</a></h3>'
                f'<div class="snippet">{html.escape(hit.snippet[:200])}</div>'
                f'<div class="meta">{hit.node_type} · rank {hit.rank} · importance {hit.importance}</div></div>'
            )
        return f'<div class="grid">{"".join(rows)}</div>'

    def _fragment_sessions(self) -> str:
        sessions = self._m().transcript_hook.list_sessions()
        if not sessions:
            return '<div class="card">No sessions captured yet</div>'
        rows = []
        for s in sorted(sessions, key=lambda x: x.started_at or "", reverse=True)[:15]:
            rows.append(
                f"<tr><td>{s.session_id[:16]}…</td>"
                f"<td>{s.turn_count}</td>"
                f"<td>{(s.started_at or '?')[:16]}</td>"
                f"<td>{s.episode_slug or '—'}</td></tr>"
            )
        return (
            "<table><tr><th>Session</th><th>Turns</th><th>Started</th><th>Episode</th></tr>"
            + "".join(rows)
            + "</table>"
        )

    def _fragment_tokens(self) -> str:
        """Server-rendered SVG bar chart from .meta.json token totals."""
        metas = []
        for meta_path in sorted(self._m().transcript_hook.transcripts_dir.glob("*.meta.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(meta, dict):
                    metas.append(meta)
            except (OSError, json.JSONDecodeError):
                continue
        if not metas:
            return '<div class="card">No token data yet (captures write usage to meta.json)</div>'

        metas.sort(key=lambda m: m.get("started_at") or "")
        bars = []
        max_tokens = (
            max((m.get("token_usage", {}).get("total_tokens", 0) for m in metas), default=1) or 1
        )
        bar_w = max(600 // len(metas), 8)
        chart_h = 120
        for i, meta in enumerate(metas):
            tokens = meta.get("token_usage", {}).get("total_tokens", 0)
            h = max(int(tokens / max_tokens * chart_h), 2)
            x = i * bar_w
            y = chart_h - h
            sid = meta.get("session_id", "?")[:10]
            bars.append(
                f'<rect class="bar" x="{x}" y="{y}" width="{bar_w - 2}" height="{h}" rx="2">'
                f"<title>{html.escape(sid)}: {tokens:,} tokens</title></rect>"
            )
        return (
            f'<svg class="chart" viewBox="0 0 600 {chart_h}" xmlns="http://www.w3.org/2000/svg">'
            + "".join(bars)
            + "</svg>"
        )


def serve(data_dir: Path | None = None, port: int = DEFAULT_PORT) -> None:
    """Start the viz server. Blocks until interrupted."""
    import webbrowser

    config = MemexConfig(data_dir=data_dir) if data_dir else MemexConfig()

    class BoundVizHandler(VizHandler):
        memex = Memex(config)

    handler = BoundVizHandler
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://localhost:{port}"
    print(f"memex viz → {url} (Ctrl-C to stop)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        if handler.memex is not None:
            handler.memex.close()
        server.server_close()
