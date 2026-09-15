"""Wiki cross-reference management over the wiki_links table (spec §7 Utility 4)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from memex.domain.links import parse_links
from memex.domain.models import WikiNode


class LinkManager:
    """Parses ``[[slug]]`` references and maintains link adjacency.

    Sync model: replace-all-outgoing — syncing a source deletes its existing
    ``(source, *)`` pairs and inserts the freshly parsed set atomically.
    """

    def __init__(self, db: sqlite3.Connection, wiki_dir: Path) -> None:
        self._db = db
        self._wiki_dir = wiki_dir

    def parse_links(self, body: str) -> list[str]:
        return parse_links(body)

    def sync_links(self, source_slug: str, body: str) -> list[str]:
        """Replace the outgoing link set of ``source_slug`` from body text."""
        targets = parse_links(body)
        with self._db:
            self._db.execute("DELETE FROM wiki_links WHERE source_slug = ?", (source_slug,))
            self._db.executemany(
                "INSERT OR IGNORE INTO wiki_links (source_slug, target_slug) VALUES (?, ?)",
                [(source_slug, target) for target in targets],
            )
        return targets

    def sync_node(self, node: WikiNode) -> list[str]:
        """Sync links for a stored node, merging its explicit front-matter links."""
        targets = list(node.links)
        for parsed in parse_links(node.body):
            if parsed not in targets:
                targets.append(parsed)
        with self._db:
            self._db.execute("DELETE FROM wiki_links WHERE source_slug = ?", (node.slug,))
            self._db.executemany(
                "INSERT OR IGNORE INTO wiki_links (source_slug, target_slug) VALUES (?, ?)",
                [(node.slug, target) for target in targets],
            )
        return targets

    def get_outgoing(self, slug: str) -> list[str]:
        rows = self._db.execute(
            "SELECT target_slug FROM wiki_links WHERE source_slug = ? ORDER BY target_slug",
            (slug,),
        ).fetchall()
        return [str(row["target_slug"]) for row in rows]

    def get_backlinks(self, slug: str) -> list[str]:
        rows = self._db.execute(
            "SELECT source_slug FROM wiki_links WHERE target_slug = ? ORDER BY source_slug",
            (slug,),
        ).fetchall()
        return [str(row["source_slug"]) for row in rows]

    def link_exists(self, source_slug: str, target_slug: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM wiki_links WHERE source_slug = ? AND target_slug = ?",
            (source_slug, target_slug),
        ).fetchone()
        return row is not None

    def validate_links(self, slug: str) -> list[str]:
        """Outgoing link targets that have no wiki page on disk."""
        broken: list[str] = []
        for target in self.get_outgoing(slug):
            if not self._page_exists(target):
                broken.append(target)
        return broken

    def get_link_graph(self) -> dict[str, list[str]]:
        rows = self._db.execute(
            "SELECT source_slug, target_slug FROM wiki_links ORDER BY source_slug, target_slug"
        ).fetchall()
        graph: dict[str, list[str]] = {}
        for row in rows:
            graph.setdefault(str(row["source_slug"]), []).append(str(row["target_slug"]))
        return graph

    def remove_slug(self, slug: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM wiki_links WHERE source_slug = ?", (slug,))
            self._db.execute("DELETE FROM wiki_links WHERE target_slug = ?", (slug,))

    def _page_exists(self, slug: str) -> bool:
        for entry in self._wiki_dir.iterdir():
            if entry.is_dir() and (entry / f"{slug}.md").exists():
                return True
        return False
