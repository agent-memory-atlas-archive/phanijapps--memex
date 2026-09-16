"""BM25 retrieval over the FTS5 index (spec §7 Utility 3)."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path

from memex.domain.models import RecallHit, RecallResult, utc_now_iso

_QUERY_TOKENS = re.compile(r"[a-z0-9]+")

# FTS column order: slug=0, title=1, body=2, tags=3. The spec's snippet
# example used column 1 while documenting it as body; body is column 2.
_SNIPPET_BODY_COLUMN = 2
_SNIPPET_TITLE_COLUMN = 1

_BASE_SQL = """
SELECT
    w.slug, w.file_path, w.title, w.node_type, w.importance,
    w.tags, w.created, w.updated, w.last_access, w.transcript_ref, w.status,
    bm25(wiki_fts) AS score,
    snippet(wiki_fts, 2, '<mark>', '</mark>', '...', 32) AS body_snippet,
    snippet(wiki_fts, 1, '<mark>', '</mark>', '...', 32) AS title_snippet
FROM wiki_fts
JOIN wiki_index w ON w.rowid = wiki_fts.rowid
WHERE wiki_fts MATCH :match
"""


class BM25Retriever:
    """Ranked lexical search. ``retrieve`` also records access statistics."""

    def __init__(
        self,
        db_path: Path,
        k1: float = 1.5,
        b: float = 0.75,
        default_top_k: int = 10,
    ) -> None:
        self.db_path = db_path
        # k1/b are accepted for config compatibility; SQLite FTS5 bm25() uses
        # compile-time defaults that cannot be tuned from SQL.
        self.k1 = k1
        self.b = b
        self.default_top_k = default_top_k
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        # Guarded like IndexManager: the MCP SDK invokes tools on worker
        # threads, so this connection may be used from several threads.
        self._lock = threading.RLock()
        self._conn.row_factory = sqlite3.Row

    def _match_query(self, query: str) -> str:
        """Reduce free text to safe OR-joined FTS5 terms (untrusted input)."""
        tokens = _QUERY_TOKENS.findall(query.lower())
        if not tokens:
            raise ValueError("query contains no searchable terms")
        return " OR ".join(tokens)

    def search_fts(self, query: str, top_k: int) -> list[tuple[str, float]]:
        """Raw (slug, score) pairs ordered by ascending bm25 score."""
        match = self._match_query(query)
        with self._lock:
            rows = self._conn.execute(
                _BASE_SQL + " ORDER BY score LIMIT :top_k",
                {"match": match, "top_k": top_k},
            ).fetchall()
        return [(str(row["slug"]), float(row["score"])) for row in rows]

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        node_type: str | None = None,
        time_range: tuple[str, str] | None = None,
        tags: list[str] | None = None,
        include_expired: bool = False,
        include_inactive: bool = False,
    ) -> RecallResult:
        """Search the index and return ranked hits with metadata.

        The query is reduced to alphanumeric tokens joined by OR, so
        untrusted input never reaches the FTS5 MATCH parser. Hits are
        ordered by ascending BM25 score — lower is better, per SQLite FTS5.
        Nodes past ``expires_at`` or ``valid_to`` are invisible unless the
        caller opts in; this is how soft-forgetting hides memories.

        Side effects: every returned hit gets ``access_count += 1`` and a
        refreshed ``last_access``. Files are never touched.

        Args:
            query: Free-text terms; must contain one alphanumeric token.
            top_k: Maximum hits, in [1, 100]; defaults to
                ``default_top_k`` from construction.
            node_type: Restrict hits to one node type.
            time_range: ``(from, to)`` ISO8601 bounds on ``updated``.
            tags: All listed tags must be present (AND semantics).
            include_expired: Also return soft-forgotten and decayed nodes.

        Returns:
            RecallResult with 1-based ranks, best first. Empty ``hits`` is
            a normal result, not an error.

        Raises:
            ValueError: Query has no searchable terms, or ``top_k`` outside
                [1, 100].
        """
        limit = top_k if top_k is not None else self.default_top_k
        if not 1 <= limit <= 100:
            raise ValueError("top_k must be between 1 and 100")
        started = time.perf_counter()

        clauses: list[str] = []
        params: dict[str, object] = {"match": self._match_query(query), "top_k": limit}
        if node_type is not None:
            clauses.append("w.node_type = :node_type")
            params["node_type"] = node_type
        if time_range is not None:
            clauses.append("w.updated >= :time_from AND w.updated <= :time_to")
            params["time_from"], params["time_to"] = time_range
        for index, tag in enumerate(tags or []):
            key = f"tag_{index}"
            clauses.append(f"w.tags LIKE :{key}")
            params[key] = f'%"{tag}"%'
        if not include_expired:
            now = utc_now_iso()
            clauses.append("(w.expires_at IS NULL OR w.expires_at >= :now)")
            clauses.append("(w.valid_to IS NULL OR w.valid_to >= :now)")
            params["now"] = now
        if not include_inactive:
            clauses.append("(w.status IS NULL OR w.status = 'active')")

        sql = _BASE_SQL
        if clauses:
            sql += " AND " + " AND ".join(clauses)
        sql += " ORDER BY score LIMIT :top_k"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
            total = self._conn.execute("SELECT COUNT(*) AS n FROM wiki_index").fetchone()

        hits = [self._to_hit(row, rank) for rank, row in enumerate(rows, start=1)]
        self._record_access(hits)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return RecallResult(
            query=query,
            hits=hits,
            total_indexed=int(total["n"]),
            search_engine="bm25",
            search_time_ms=round(elapsed_ms, 3),
        )

    def close(self) -> None:
        self._conn.close()

    def _record_access(self, hits: list[RecallHit]) -> None:
        """Recall side effect: bump access_count/last_access per hit (§9.2)."""
        now = utc_now_iso()
        with self._lock, self._conn:
            self._conn.executemany(
                "UPDATE wiki_index SET access_count = access_count + 1, last_access = ?"
                " WHERE slug = ?",
                [(now, hit.slug) for hit in hits],
            )

    def _to_hit(self, row: sqlite3.Row, rank: int) -> RecallHit:
        body_snippet = str(row["body_snippet"])
        title_snippet = str(row["title_snippet"])
        # FTS5 snippet() returns text even when the column itself has no
        # match, so "where did it match" is detected via the <mark> tags.
        if "<mark>" in body_snippet:
            snippet, source = body_snippet, "body"
        else:
            snippet, source = title_snippet, "title"
        with self._lock:
            links = [
                str(link_row["target_slug"])
                for link_row in self._conn.execute(
                    "SELECT target_slug FROM wiki_links WHERE source_slug = ? ORDER BY target_slug",
                    (str(row["slug"]),),
                ).fetchall()
            ]
        try:
            status = str(row["status"])
        except (IndexError, KeyError):
            status = "active"
        return RecallHit(
            slug=str(row["slug"]),
            status=status,
            file_path=str(row["file_path"]),
            title=str(row["title"]),
            node_type=str(row["node_type"]),
            importance=float(row["importance"]),
            score=float(row["score"]),
            rank=rank,
            snippet=snippet,
            snippet_source=source,
            tags=json.loads(str(row["tags"])),
            created=str(row["created"]),
            updated=str(row["updated"]),
            last_access=row["last_access"],
            transcript_ref=row["transcript_ref"],
            links=links,
        )
