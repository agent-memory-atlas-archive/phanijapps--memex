"""On-demand HTMX dashboard for the memex memory store.

`memex viz` starts a localhost HTTP server that renders existing surfaces
(docs pages, session metadata, run log, index stats) as an interactive
dashboard. Read-only: the filesystem is the truth, this is a projection.

Zero new dependencies: stdlib http.server + vendored HTMX 2.0.4 +
hand-written CSS + server-rendered SVG charts. Stops when the process stops.
"""

from __future__ import annotations

import html
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from memex.application.memory import Memex
from memex.domain.models import WikiNode

DEFAULT_PORT = 7171

_HTMX_PATH = Path(__file__).parent / "htmx.min.js"
_HTMX_BYTES: bytes = (
    _HTMX_PATH.read_bytes() if _HTMX_PATH.exists() else b"console.error('htmx not found');"
)

_ENRICHED_MARKER = re.compile(r"<!-- enriched -->\s*", re.DOTALL)
_MARK_TAG = re.compile(r"</?mark>")

_CSS = """
:root {
  --bg: #0d1117; --surface: #161b22; --border: #30363d;
  --text: #e6edf3; --text-muted: #8b949e; --text-dim: #6e7681;
  --accent: #58a6ff; --ok: #3fb950; --warn: #d29922; --error: #f85149;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  --radius: 6px; --space: 1rem;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f6f8fa; --surface: #fff; --border: #d0d7de;
    --text: #1f2328; --text-muted: #656d76; --text-dim: #8c959f;
    --accent: #0969da; --ok: #1a7f37; --warn: #9a6700; --error: #cf222e;
  }
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:var(--sans); background:var(--bg); color:var(--text);
       font-size:14px; line-height:1.5; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }

/* ---- Shell ---- */
.shell { max-width:1200px; margin:0 auto; padding:1.5rem; }
header { display:flex; align-items:center; gap:1rem; margin-bottom:1rem; }
header h1 { font-size:1.1rem; font-weight:600; letter-spacing:-0.02em; }
.datapath { font-family:var(--mono); font-size:.75rem; color:var(--text-dim); }

/* ---- Nav tabs ---- */
nav { display:flex; gap:.25rem; border-bottom:1px solid var(--border); margin-bottom:1rem; }
nav a { padding:.5rem .9rem; font-size:.82rem; font-weight:500; color:var(--text-muted);
        border-bottom:2px solid transparent; }
nav a:hover { color:var(--text); text-decoration:none; }
nav a[aria-current] { color:var(--text); border-bottom-color:var(--accent); }

/* ---- Status bar ---- */
.statusbar { display:flex; align-items:center; gap:1rem; padding:.6rem .9rem;
             background:var(--surface); border:1px solid var(--border);
             border-radius:var(--radius); margin-bottom:1rem; font-size:.82rem; }
.statusbar .dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.statusbar .dot.ok { background:var(--ok); }
.statusbar .dot.warn { background:var(--warn); }
.statusbar .dot.error { background:var(--error); }
.statusbar .metric { display:flex; gap:.3rem; align-items:baseline; }
.statusbar .metric b { font-variant-numeric:tabular-nums; }
.statusbar .metric span { color:var(--text-muted); }
.statusbar .spacer { flex:1; }
.statusbar a { font-size:.78rem; }

/* ---- KPI grid ---- */
.kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:.75rem; margin-bottom:1rem; }
.kpi { background:var(--surface); border:1px solid var(--border);
       border-radius:var(--radius); padding:.9rem 1rem; }
.kpi .value { font-size:1.6rem; font-weight:700; font-variant-numeric:tabular-nums;
              letter-spacing:-0.02em; }
.kpi .label { font-size:.72rem; color:var(--text-muted); text-transform:uppercase;
              letter-spacing:.05em; margin-top:.15rem; }
@media (max-width:768px) { .kpis { grid-template-columns:repeat(2,1fr); } }

/* ---- Section headers ---- */
.section { font-size:.72rem; font-weight:600; color:var(--text-muted);
           text-transform:uppercase; letter-spacing:.08em; margin:1.2rem 0 .5rem; }

/* ---- Memory cards ---- */
.cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:.6rem; }
.card { background:var(--surface); border:1px solid var(--border);
        border-radius:var(--radius); padding:.75rem .85rem; }
.card h3 { font-size:.85rem; font-weight:600; margin-bottom:.2rem; }
.card .body { font-size:.78rem; color:var(--text-muted); line-height:1.4;
              max-height:3.6em; overflow:hidden; }
.card .meta { font-size:.7rem; color:var(--text-dim); margin-top:.3rem;
              display:flex; gap:.4rem; flex-wrap:wrap; align-items:center; }
.card .meta .sep { color:var(--border); }

/* ---- Type badges ---- */
.badge { display:inline-block; padding:1px 6px; border-radius:3px;
         font-size:.68rem; font-weight:600; font-family:var(--mono); }
.badge.entity { color:#a371f7; background:rgba(163,113,247,.12); }
.badge.preference { color:#f0883e; background:rgba(240,136,62,.12); }
.badge.procedure { color:#58a6ff; background:rgba(88,166,255,.12); }
.badge.summary { color:#3fb950; background:rgba(63,185,80,.12); }
.badge.episode { color:#8b949e; background:rgba(139,148,158,.12); }
.badge.pending { color:var(--warn); background:rgba(210,153,34,.12); }
.badge.archived { color:var(--text-dim); background:rgba(110,118,129,.12); }
.badge.superseded { color:#f85149; background:rgba(248,81,73,.12); }

/* ---- Filter pills ---- */
.filters { display:flex; gap:.35rem; margin-bottom:.6rem; flex-wrap:wrap; }
.filters a { padding:.2rem .65rem; border-radius:99px; font-size:.75rem;
             font-weight:500; color:var(--text-muted); background:var(--surface);
             border:1px solid var(--border); }
.filters a:hover { color:var(--text); text-decoration:none; }
.filters a[aria-current] { color:var(--accent); border-color:var(--accent); }

/* ---- Search ---- */
.search-bar { position:relative; margin-bottom:.8rem; }
.search-bar input { width:100%; padding:.6rem .9rem; background:var(--surface);
                    border:1px solid(var(--border)); border-radius:var(--radius);
                    color:var(--text); font-size:.88rem; font-family:var(--sans); }
.search-bar input:focus { outline:none; border-color:var(--accent); }
.search-bar input::placeholder { color:var(--text-dim); }
mark { background:rgba(88,166,255,.2); color:inherit; padding:0 1px;
       border-radius:2px; }

/* ---- Tables ---- */
table { width:100%; border-collapse:collapse; font-size:.78rem; }
th { text-align:left; padding:.4rem .5rem; color:var(--text-muted);
     font-weight:500; font-size:.72rem; text-transform:uppercase;
     letter-spacing:.05em; border-bottom:1px solid(var(--border)); }
td { padding:.4rem .5rem; border-bottom:1px solid(var(--border));
     font-family:var(--mono); font-size:.75rem; }
td.muted { color:var(--text-muted); }
tr:last-child td { border-bottom:none; }

/* ---- Charts ---- */
.chart-box { background:var(--surface); border:1px solid(var(--border));
             border-radius:var(--radius); padding:1rem; }
.chart-box svg { width:100%; height:auto; display:block; }
.bar { fill:var(--accent); opacity:.8; }
.bar:hover { opacity:1; }
.grid-line { stroke:var(--border); stroke-width:.5; opacity:.3; }
.axis-label { fill:var(--text-dim); font-size:10px; font-family:var(--mono); }

/* ---- Empty/error states ---- */
.empty { padding:1.5rem; text-align:center; color:var(--text-muted);
         background:var(--surface); border:1px dashed var(--border);
         border-radius:var(--radius); font-size:.85rem; }
.error { padding:1rem; color:var(--error); background:var(--surface);
         border:1px solid var(--error); border-radius:var(--radius); font-size:.82rem; }

/* ---- Misc ---- */
.htmx-indicator { opacity:0; transition:opacity .2s; }
.htmx-request .htmx-indicator { opacity:1; }
.subtle { font-size:.72rem; color:var(--text-dim); }
"""

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>memex viz</title>
<link rel="stylesheet" href="/style.css">
<script src="/htmx.js"></script>
</head>
<body>
<div class="shell">
<header>
<h1>memex</h1>
<span class="datapath">{data_dir}</span>
</header>
<nav>
  <a href="/view/overview" hx-get="/overview" hx-target="#main" hx-push-url="true">Overview</a>
  <a href="/view/memories" hx-get="/pages" hx-target="#main" hx-push-url="true">Memories</a>
  <a href="/view/sessions" hx-get="/sessions" hx-target="#main" hx-push-url="true">Sessions</a>
  <a href="/view/tokens" hx-get="/tokens" hx-target="#main" hx-push-url="true">Tokens</a>
</nav>
<main id="main" hx-get="/overview" hx-trigger="load">{initial}</main>
</div>
</body>
</html>"""


def _esc(text: object) -> str:
    """HTML-escape any value at the interpolation boundary."""
    return html.escape(str(text if text is not None else ""))


def _clean_snippet(snippet: str) -> str:
    """Escape content while preserving safe <mark> tags from FTS5."""
    escaped = html.escape(snippet)
    # Re-inject the mark tags that html.escape destroyed
    return escaped.replace("&lt;mark&gt;", "<mark>").replace("&lt;/mark&gt;", "</mark>")


def _strip_enriched(body: str) -> str:
    """Remove the <!-- enriched --> marker and extract the summary below it."""
    match = re.search(r"<!-- enriched -->\s*\n*(.*?)(?:\n---|\Z)", body, re.DOTALL)
    if match:
        return match.group(1).strip()
    return _ENRICHED_MARKER.sub("", body).strip()


def _type_badge(node_type: str, status: str) -> str:
    if status != "active":
        return f'<span class="badge {status}">{_esc(status)}</span>'
    return f'<span class="badge {node_type}">{_esc(node_type)}</span>'


def _meta_line(node: WikiNode) -> str:
    parts = [_esc(getattr(node, "type", ""))]
    if getattr(node, "tags", None):
        parts.append(" ".join(f"#{_esc(t)}" for t in node.tags[:4]))
    updated = str(getattr(node, "updated", "") or "")[:10]
    if updated:
        parts.append(updated)
    importance = getattr(node, "importance", None)
    if importance is not None:
        parts.append(f"imp {_esc(importance)}")
    return f'<span class="meta"><span>{'</span><span class="sep">·</span><span>'.join(parts)}</span></span>'


class VizHandler(BaseHTTPRequestHandler):
    memex: Memex | None = None

    def do_GET(self) -> None:
        url = urlparse(self.path)
        route = url.path.rstrip("/") or "/"
        qs = parse_qs(url.query)

        if route == "/htmx.js":
            self._bytes(_HTMX_BYTES, "application/javascript")
        elif route == "/style.css":
            self._text(_CSS, "text/css")
        elif route == "/":
            self._text(_PAGE.format(data_dir=_esc(self._m().data_dir), initial=""), "text/html")
        elif route == "/overview":
            self._text(self._frag_overview(), "text/html")
        elif route == "/pages":
            node_type = qs.get("type", [None])[0]
            self._text(self._frag_pages(node_type), "text/html")
        elif route == "/search":
            self._text(self._frag_search(qs.get("q", [""])[0]), "text/html")
        elif route == "/sessions":
            self._text(self._frag_sessions(), "text/html")
        elif route == "/tokens":
            self._text(self._frag_tokens(), "text/html")
        elif route == "/health":
            self._text(self._frag_health(), "text/html")
        else:
            self._text('<div class="empty">Not found</div>', "text/html", 200)

    def log_message(self, format: str, *args: object) -> None:
        pass

    def _bytes(self, payload: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _text(self, body: str, ctype: str, code: int = 200) -> None:
        self._bytes(body.encode(), ctype, code)

    def _m(self) -> Memex:
        if self.memex is None:
            raise RuntimeError("viz handler not initialized")
        return self.memex

    def _frag_overview(self) -> str:
        stats = self._m().status()
        total = int(str(stats.get("index_total", "0") or "0"))
        pending = int(str(stats.get("pending", "0") or "0"))
        stale = int(str(stats.get("index_stale_rows", "0") or "0"))

        health = '<span class="dot ok"></span>' if stale == 0 else '<span class="dot warn"></span>'

        # Recent non-episode memories (the interesting ones)
        nodes = [n for n in self._m().wiki_store.list() if n.type != "episode"][:8]
        cards = "".join(self._card(n) for n in nodes)
        memories = (
            f'<div class="cards">{cards}</div>'
            if cards
            else '<div class="empty">No distilled memories yet — run <code>memex consolidate</code></div>'
        )

        return f"""
<div class="statusbar" id="health" hx-get="/health" hx-trigger="every 5s" hx-swap="innerHTML">
  {health}
  <span class="metric"><b>{total}</b><span>pages</span></span>
  <span class="metric"><b>{pending}</b><span>pending</span></span>
  <span class="metric"><b>{stale}</b><span>stale rows</span></span>
  <span class="spacer"></span>
  <span class="subtle">auto-refresh 5s</span>
</div>
<div class="kpis">
  <div class="kpi"><div class="value">{total}</div><div class="label">Memory pages</div></div>
  <div class="kpi"><div class="value">{pending}</div><div class="label">Pending approval</div></div>
  <div class="kpi"><div class="value">{stale}</div><div class="label">Stale index rows</div></div>
  <div class="kpi"><div class="value">{int(str(stats.get("zero_yield_streak", "0") or "0"))}</div><div class="label" title="Consecutive consolidations that produced zero new nodes">Zero-yield streak</div></div>
</div>
<div class="search-bar">
  <input type="search" placeholder="Search memories…" autocomplete="off"
    hx-get="/search" hx-trigger="keyup changed delay:300ms" hx-target="#search-results" name="q">
</div>
<div id="search-results"></div>
<div class="section">Recent memories</div>
{memories}
"""

    def _frag_health(self) -> str:
        stats = self._m().status()
        stale = int(str(stats.get("index_stale_rows", "0") or "0"))
        dot = '<span class="dot ok"></span>' if stale == 0 else '<span class="dot warn"></span>'
        pending = int(str(stats.get("pending", "0") or "0"))
        total = int(str(stats.get("index_total", "0") or "0"))
        streak = int(str(stats.get("zero_yield_streak", "0") or "0"))
        link = ' · <a href="#">run memex verify</a>' if stale > 0 else ""
        return (
            f'{dot}<span class="metric"><b>{total}</b><span>pages</span></span>'
            f'<span class="metric"><b>{pending}</b><span>pending</span></span>'
            f'<span class="metric"><b>{stale}</b><span>stale</span></span>'
            f'<span class="metric"><b>{streak}</b><span>zero-yield</span></span>'
            f'<span class="spacer"></span><span class="subtle">5s</span>{link}'
        )

    def _card(self, node: WikiNode) -> str:
        body_raw = _strip_enriched(str(getattr(node, "body", "")))
        badge = _type_badge(getattr(node, "type", ""), getattr(node, "status", "active"))
        return (
            f'<div class="card"><h3>{_esc(getattr(node, "title", ""))} {badge}</h3>'
            f'<div class="body">{_esc(body_raw[:200])}</div>'
            f"{_meta_line(node)}</div>"
        )

    def _frag_pages(self, node_type: str | None) -> str:
        if node_type and node_type not in (
            "entity",
            "preference",
            "procedure",
            "summary",
            "episode",
        ):
            return f'<div class="empty">Unknown type: {_esc(node_type)}. <a href="/pages">View all</a></div>'
        nodes = self._m().wiki_store.list(node_type)
        if not nodes:
            return '<div class="empty">No memories of this type yet</div>'
        nodes = sorted(nodes, key=lambda n: getattr(n, "updated", ""), reverse=True)[:24]
        cards = "".join(self._card(n) for n in nodes)
        filters = '<div class="filters">'
        if node_type is None:
            filters += '<a href="#" aria-current="true">All</a>'
        else:
            filters += '<a href="#" hx-get="/pages" hx-target="#main" hx-push-url="true">All</a>'
        for t in ("entity", "preference", "procedure", "summary", "episode"):
            active = ' aria-current="true"' if t == node_type else ""
            filters += f' <a href="#" hx-get="/pages?type={t}" hx-target="#main" hx-push-url="true"{active}>{t}</a>'
        filters += "</div>"
        return f'{filters}<div class="cards">{cards}</div>'

    def _frag_search(self, q: str) -> str:
        if not q.strip():
            return ""
        try:
            result = self._m().recall(q, top_k=8)
        except Exception:
            return '<div class="error">Search failed — index may be stale. Run <code>memex rebuild-index</code>.</div>'
        if not result.hits:
            return f'<div class="empty">No memories match "{_esc(q)}"</div>'
        items = []
        for hit in result.hits:
            snippet = _clean_snippet(hit.snippet[:250] if hit.snippet else "")
            badge = f'<span class="badge {hit.node_type}">{_esc(hit.node_type)}</span>'
            items.append(
                f'<div class="card"><h3>{_esc(hit.title)} {badge}</h3>'
                f'<div class="body">{snippet}</div>'
                f'<div class="meta"><span>rank {hit.rank}</span><span class="sep">·</span>'
                f"<span>imp {hit.importance}</span></div></div>"
            )
        return f'<div class="cards">{"".join(items)}</div>'

    def _frag_sessions(self) -> str:
        sessions = self._m().transcript_hook.list_sessions()
        if not sessions:
            return '<div class="empty">No sessions captured yet — install a harness adapter (<code>memex install codex</code>)</div>'
        sessions = sorted(sessions, key=lambda s: s.started_at or "", reverse=True)[:20]
        rows = []
        for s in sessions:
            sid = _esc(str(s.session_id)[:18])
            turns = _esc(s.turn_count)
            started = _esc(str(s.started_at or "?")[:16])
            ep = _esc(str(s.episode_slug or "—")[:24] if s.episode_slug else "—")
            rows.append(
                f'<tr><td>{sid}</td><td>{turns}</td><td class="muted">{started}</td><td class="muted">{ep}</td></tr>'
            )
        return (
            "<table><thead><tr><th>Session</th><th>Turns</th><th>Started</th><th>Episode</th></tr></thead>"
            + "".join(rows)
            + "</table>"
        )

    def _frag_tokens(self) -> str:
        metas = []
        for meta_path in sorted(self._m().transcript_hook.transcripts_dir.glob("*.meta.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(meta, dict):
                    metas.append(meta)
            except (OSError, json.JSONDecodeError):
                continue
        if not metas:
            return '<div class="empty">No token data yet — captures write usage to meta.json</div>'
        metas.sort(key=lambda m: str(m.get("started_at") or ""))

        # Filter to sessions with numeric token data; skip malformed
        valid = []
        for m in metas:
            try:
                tokens = m.get("token_usage", {}).get("total_tokens", 0)
                if isinstance(tokens, (int, float)):
                    valid.append((m, int(tokens)))
                else:
                    continue
            except (AttributeError, TypeError):
                continue

        if not valid:
            return '<div class="empty">No valid token data found</div>'

        # Cap at ~60 bars; bucket by day if more
        if len(valid) > 60:
            daily: dict[str, int] = {}
            for m, tokens in valid:
                day = str(m.get("started_at", ""))[:10]
                daily[day] = daily.get(day, 0) + tokens
            valid = [({"started_at": d, "session_id": d}, t) for d, t in sorted(daily.items())]

        max_tokens = max(t for _, t in valid) or 1
        chart_h = 140
        chart_w = min(len(valid) * 10, 1100)
        bar_w = max(chart_w // len(valid), 4)
        bars = []
        for i, (m, tokens) in enumerate(valid):
            x = i * bar_w
            h = 1 if tokens == 0 else max(int(tokens / max_tokens * chart_h), 2)
            y = chart_h - h
            sid = str(m.get("session_id", "?"))[:12]
            bars.append(
                f'<rect class="bar" x="{x}" y="{y}" width="{max(bar_w - 2, 1)}" height="{h}" rx="2">'
                f"<title>{_esc(sid)}: {tokens:,} tokens</title></rect>"
            )
        # Gridlines
        grid_h = chart_h
        gridlines = "".join(
            f'<line class="grid-line" x1="0" y1="{grid_h - i * grid_h // 4}" x2="{chart_w}" y2="{grid_h - i * grid_h // 4}"/>'
            for i in range(5)
        )
        return (
            f'<div class="chart-box"><svg viewBox="0 0 {chart_w} {chart_h + 20}" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Token consumption per session">'
            f"{gridlines}{''.join(bars)}"
            f'<text class="axis-label" x="4" y="{chart_h + 14}">0</text>'
            f'<text class="axis-label" x="{chart_w - 40}" y="{chart_h + 14}">{max_tokens:,}</text>'
            f"</svg></div>"
        )


def serve(data_dir: Path | None = None, port: int = DEFAULT_PORT) -> None:
    """Start the viz server. Blocks until interrupted."""
    import webbrowser

    from memex.infrastructure.config import MemexConfig

    config = MemexConfig(data_dir=data_dir) if data_dir else MemexConfig()

    class BoundVizHandler(VizHandler):
        memex = Memex(config)

    server = ThreadingHTTPServer(("127.0.0.1", port), BoundVizHandler)
    url = f"http://localhost:{port}"
    print(f"memex viz → {url} (Ctrl-C to stop)")
    try:
        webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        if BoundVizHandler.memex is not None:
            BoundVizHandler.memex.close()
        server.server_close()
