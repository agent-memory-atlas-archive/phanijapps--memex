"""Wiki cross-reference management over the wiki_links table (spec §7 Utility 4)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from memex.domain.errors import IndexManagerError
from memex.domain.links import parse_links
from memex.domain.models import BODY_REL, WikiNode
from memex.domain.reserved import is_structural
from memex.infrastructure.index_manager import check_slug


class LinkManager:
    """Parses ``[[slug]]`` references and maintains link adjacency.

    Sync model: replace-all-outgoing — syncing a source deletes its existing
    ``(source, *)`` pairs and inserts the freshly parsed set atomically.

    Every edge carries an OKF relation: front-matter typed links keep their
    declared ``rel``, the four OKF relation fields use their own field name,
    and a ``[[slug]]`` body reference is a ``mentions`` edge.
    """

    def __init__(self, db: sqlite3.Connection, wiki_dir: Path) -> None:
        self._db = db
        self._wiki_dir = wiki_dir

    def parse_links(self, body: str) -> list[str]:
        return parse_links(body)

    def sync_links(
        self,
        source_slug: str,
        body: str,
        *,
        source_scope: str = "global",
        source_project_id: str | None = None,
    ) -> list[str]:
        """Replace the outgoing link set of ``source_slug`` from body text."""
        targets = parse_links(body)
        self._replace(
            source_scope,
            source_project_id,
            source_slug,
            [(target, BODY_REL) for target in targets],
        )
        return targets

    def sync_node(self, node: WikiNode) -> list[str]:
        """Sync every relation a stored node declares, plus its body mentions."""
        relations = list(node.relations())
        declared = {target for target, _rel in relations}
        relations.extend(
            (target, BODY_REL) for target in parse_links(node.body) if target not in declared
        )
        self._replace(node.scope, node.project_id, node.slug, relations)
        return [target for target, _rel in relations]

    def _replace(
        self,
        source_scope: str,
        source_project_id: str | None,
        source_slug: str,
        relations: list[tuple[str, str]],
    ) -> None:
        """Atomically swap one source's outgoing edges for ``relations``."""
        with self._db:
            self._db.execute(
                "DELETE FROM wiki_links WHERE source_scope = ?"
                " AND source_project_id = ? AND source_slug = ?",
                (source_scope, source_project_id or "", source_slug),
            )
            self._db.executemany(
                "INSERT OR IGNORE INTO wiki_links"
                " (source_scope, source_project_id, source_slug, target_slug, rel)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    (source_scope, source_project_id or "", source_slug, target, rel)
                    for target, rel in relations
                ],
            )

    def get_outgoing(
        self,
        slug: str,
        *,
        source_scope: str | None = None,
        source_project_id: str | None = None,
    ) -> list[str]:
        query = (
            "SELECT source_scope, source_project_id, source_slug, target_slug"
            " FROM wiki_links WHERE source_slug = ? ORDER BY target_slug"
        )
        params: tuple[object, ...] = (slug,)
        if source_scope is not None and source_project_id is not None:
            query = (
                "SELECT source_scope, source_project_id, source_slug, target_slug"
                " FROM wiki_links WHERE source_slug = ? AND source_scope = ?"
                " AND source_project_id = ? ORDER BY target_slug"
            )
            params = (slug, source_scope, source_project_id)
        elif source_scope is not None:
            query = (
                "SELECT source_scope, source_project_id, source_slug, target_slug"
                " FROM wiki_links WHERE source_slug = ? AND source_scope = ?"
                " ORDER BY target_slug"
            )
            params = (slug, source_scope)
        elif source_project_id is not None:
            query = (
                "SELECT source_scope, source_project_id, source_slug, target_slug"
                " FROM wiki_links WHERE source_slug = ? AND source_project_id = ?"
                " ORDER BY target_slug"
            )
            params = (slug, source_project_id)
        rows = self._db.execute(
            query,
            params,
        ).fetchall()
        if not _source_namespace_complete(source_scope, source_project_id):
            indexed_sources = self._db.execute(
                "SELECT scope AS source_scope, project_id AS source_project_id,"
                " slug AS source_slug FROM wiki_index WHERE slug = ?",
                (slug,),
            ).fetchall()
            matching_sources = [
                row
                for row in indexed_sources
                if (source_scope is None or row["source_scope"] == source_scope)
                and (source_project_id is None or row["source_project_id"] == source_project_id)
            ]
            _refuse_ambiguous_source_slugs(rows + matching_sources)
        return _unique([str(row["target_slug"]) for row in rows])

    def get_backlinks(self, slug: str) -> list[str]:
        rows = self._db.execute(
            "SELECT source_scope, source_project_id, source_slug FROM wiki_links"
            " WHERE target_slug = ? ORDER BY source_slug",
            (slug,),
        ).fetchall()
        indexed_sources = self._db.execute(
            "SELECT scope AS source_scope, project_id AS source_project_id,"
            " slug AS source_slug FROM wiki_index"
            " WHERE slug IN (SELECT source_slug FROM wiki_links WHERE target_slug = ?)",
            (slug,),
        ).fetchall()
        _refuse_ambiguous_source_slugs(rows + indexed_sources)
        return _unique([str(row["source_slug"]) for row in rows])

    def link_exists(
        self,
        source_slug: str,
        target_slug: str,
        *,
        source_scope: str | None = None,
        source_project_id: str | None = None,
    ) -> bool:
        return target_slug in self.get_outgoing(
            source_slug,
            source_scope=source_scope,
            source_project_id=source_project_id,
        )

    def validate_links(
        self,
        slug: str,
        *,
        source_scope: str | None = None,
        source_project_id: str | None = None,
    ) -> list[str]:
        """Outgoing link targets that have no wiki page on disk."""
        broken: list[str] = []
        for target in self.get_outgoing(
            slug, source_scope=source_scope, source_project_id=source_project_id
        ):
            if not self._page_exists(target):
                broken.append(target)
        return broken

    def get_link_graph(self) -> dict[str, list[str]]:
        rows = self._db.execute(
            "SELECT source_scope, source_project_id, source_slug, target_slug"
            " FROM wiki_links ORDER BY source_slug, target_slug"
        ).fetchall()
        indexed_sources = self._db.execute(
            "SELECT scope AS source_scope, project_id AS source_project_id,"
            " slug AS source_slug FROM wiki_index"
            " WHERE slug IN (SELECT source_slug FROM wiki_links)"
        ).fetchall()
        _refuse_ambiguous_source_slugs(rows + indexed_sources)
        graph: dict[str, list[str]] = {}
        for row in rows:
            graph.setdefault(str(row["source_slug"]), []).append(str(row["target_slug"]))
        return {source: _unique(targets) for source, targets in graph.items()}

    def remove_slug(
        self,
        slug: str,
        *,
        source_scope: str | None = None,
        source_project_id: str | None = None,
    ) -> None:
        clauses = ["source_slug = ?"]
        params: list[object] = [slug]
        if source_scope is not None:
            clauses.append("source_scope = ?")
            params.append(source_scope)
        if source_project_id is not None:
            clauses.append("source_project_id = ?")
            params.append(source_project_id)
        with self._db:
            self._db.execute(
                "DELETE FROM wiki_links WHERE " + " AND ".join(clauses),  # noqa: S608
                params,
            )
            self._db.execute(
                "DELETE FROM wiki_links WHERE target_slug = ?"
                " AND NOT EXISTS (SELECT 1 FROM wiki_index WHERE slug = ?)",
                (slug, slug),
            )

    def _page_exists(self, slug: str) -> bool:
        try:
            check_slug(slug)
        except IndexManagerError:
            return False
        return any(not is_structural(path) for path in self._wiki_dir.rglob(f"{slug}.md"))


def _unique(values: list[str]) -> list[str]:
    """Order-preserving de-duplication: one target may carry several rels."""
    return list(dict.fromkeys(values))


def _source_namespace_complete(source_scope: str | None, source_project_id: str | None) -> bool:
    if source_scope == "global":
        return True
    return source_scope is not None and source_project_id is not None


def _refuse_ambiguous_source_slugs(rows: list[sqlite3.Row]) -> None:
    namespaces_by_slug: dict[str, set[tuple[str, str]]] = {}
    for row in rows:
        slug = str(row["source_slug"])
        namespaces_by_slug.setdefault(slug, set()).add(
            (str(row["source_scope"]), str(row["source_project_id"]))
        )
    ambiguous = sorted(
        slug for slug, namespaces in namespaces_by_slug.items() if len(namespaces) > 1
    )
    if ambiguous:
        raise IndexManagerError(f"ambiguous link source slug: {ambiguous[0]!r}")
