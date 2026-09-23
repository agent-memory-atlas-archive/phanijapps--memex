"""Minimal Markdown-to-HTML renderer (stdlib only).

Handles the subset memex pages actually use: headers, bold/italic,
code blocks, inline code, links, ordered/unordered lists, blockquotes,
wiki-links, and paragraphs. All input is HTML-escaped before Markdown
transforms, so stored memory content (untrusted per AGENTS.md) cannot
inject markup.
"""

from __future__ import annotations

import html
import re


def render_markdown(text: str) -> str:
    """Render Markdown to HTML. Input is escaped first (XSS-safe)."""
    escaped = html.escape(text)
    lines = escaped.split("\n")
    output: list[str] = []
    in_code = False
    code_lines: list[str] = []
    in_list: str | None = None  # "ul" | "ol" | None
    in_quote = False

    def _close_list() -> None:
        nonlocal in_list
        if in_list:
            output.append(f"</{in_list}>")
            in_list = None

    def _close_quote() -> None:
        nonlocal in_quote
        if in_quote:
            output.append("</blockquote>")
            in_quote = False

    def _inline(text: str) -> str:
        # Wiki-links: [[slug]] → styled span
        text = re.sub(
            r"\[\[([^\]]+)\]\]",
            r'<span class="wikilink">\1</span>',
            text,
        )
        # Links: [text](url) — only http(s) and relative
        text = re.sub(
            r"\[([^\]]+)\]\(((?:https?://|\/)[^)]+)\)",
            r'<a href="\2" rel="noopener">\1</a>',
            text,
        )
        # Bold: **text**
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        # Italic: *text* (not **)
        text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
        # Inline code: `text`
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        return text

    for line in lines:
        stripped = line.strip()

        # Code fence toggle
        if stripped.startswith("```"):
            if in_code:
                lang = code_lines[0].strip() if code_lines else ""
                body = "\n".join(code_lines[1:] if lang else code_lines)
                output.append(f"<pre><code>{body}</code></pre>")
                code_lines = []
                in_code = False
            else:
                _close_list()
                _close_quote()
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        # Skip empty lines (paragraph separator)
        if not stripped:
            _close_list()
            _close_quote()
            continue

        # Headers
        header = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if header:
            _close_list()
            _close_quote()
            level = len(header.group(1))
            output.append(f"<h{level}>{_inline(header.group(2))}</h{level}>")
            continue

        # Horizontal rule
        if re.match(r"^(-{3,}|\*{3,})$", stripped):
            _close_list()
            _close_quote()
            output.append("<hr>")
            continue

        # Blockquote
        if stripped.startswith("&gt;"):
            _close_list()
            if not in_quote:
                output.append("<blockquote>")
                in_quote = True
            output.append(f"<p>{_inline(stripped[4:].strip())}</p>")
            continue
        if in_quote:
            _close_quote()

        # Unordered list
        if re.match(r"^[-*+]\s+", stripped):
            if in_list != "ul":
                _close_list()
                output.append("<ul>")
                in_list = "ul"
            item = re.sub(r"^[-*+]\s+", "", stripped)
            output.append(f"<li>{_inline(item)}</li>")
            continue

        # Ordered list
        if re.match(r"^\d+\.\s+", stripped):
            if in_list != "ol":
                _close_list()
                output.append("<ol>")
                in_list = "ol"
            item = re.sub(r"^\d+\.\s+", "", stripped)
            output.append(f"<li>{_inline(item)}</li>")
            continue

        # Regular paragraph
        _close_list()
        output.append(f"<p>{_inline(stripped)}</p>")

    _close_list()
    _close_quote()
    if in_code:
        body = "\n".join(code_lines)
        output.append(f"<pre><code>{body}</code></pre>")

    return "\n".join(output)
