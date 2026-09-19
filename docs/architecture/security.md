# Dashboard security boundary

The optional `memex viz` process binds to loopback only. Every dashboard GET is
read-only: it may inspect Markdown pages, transcript files, metadata, and the
SQLite index, but must not write them or update access counters. Assets are
served locally; the dashboard makes no remote requests.

Stored memories, transcript turns, session metadata, and URL parameters are
untrusted. Rendered values are escaped, except AI Markdown rendered through
the existing safe renderer. Session IDs are validated before lookup, and
resolved transcript and metadata paths must stay inside the transcript root.
Invalid records receive a bounded empty or degraded state rather than a
filesystem path, raw exception, or executable markup.

Scope and project identifiers select an existing namespace; they do not create
paths from user input. Direct `/view/` URLs and HTMX fragments follow the same
read and rendering rules. The isolated live-server tests in
`tests/unit/test_viz_routes.py` protect these invariants.
