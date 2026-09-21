"""BM25 retrieval over the FTS5 index (spec §7 Utility 3)."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from memex.domain.models import RecallHit, RecallResult, utc_now_iso

_QUERY_TOKENS = re.compile(r"[a-z0-9]+")
MAX_QUERY_BYTES = 1024
MAX_QUERY_TOKENS = 64
_WINNER_SEARCH_ENGINE = "semantic-and-fallback-fts5"
_WINNER_BODY_WEIGHT = 2.0
_WINNER_DESCRIPTION_WEIGHT = 1.0  # neutral: keeps slug/title/body/tags contributions fixed
_QUERY_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "did",
        "do",
        "does",
        "from",
        "how",
        "in",
        "is",
        "of",
        "the",
        "to",
        "we",
        "what",
        "why",
    }
)
_SEMANTIC_SCAFFOLDING_PHRASES = (
    ("instead", "of"),
    ("how", "many"),
    ("switch", "from"),
)

# FTS column order: slug=0, title=1, description=2, body=3, tags=4.
_SNIPPET_TITLE_COLUMN = 1
_SNIPPET_DESCRIPTION_COLUMN = 2
_SNIPPET_BODY_COLUMN = 3
_WINNER_SNIPPET_TOKENS = 12

_LEGACY_BASE_SQL = """
SELECT
    w.slug, w.file_path, w.title, w.description, w.node_type, w.importance,
    w.tags, w.created, w.updated, w.last_access, w.transcript_ref, w.status,
    w.scope, w.project_id, w.project_label,
    bm25(wiki_fts) AS score,
    snippet(wiki_fts, 3, '<mark>', '</mark>', '...', 32) AS body_snippet,
    snippet(wiki_fts, 2, '<mark>', '</mark>', '...', 32) AS description_snippet,
    snippet(wiki_fts, 1, '<mark>', '</mark>', '...', 32) AS title_snippet
FROM wiki_fts
JOIN wiki_index w ON w.rowid = wiki_fts.rowid
WHERE wiki_fts MATCH :match
"""
_WINNER_SELECT_SQL = """
SELECT
    w.slug, w.file_path, w.title, w.description, w.node_type, w.importance,
    w.tags, w.created, w.updated, w.last_access, w.transcript_ref, w.status,
    w.scope, w.project_id, w.project_label,
    bm25(wiki_fts, 1.0, 1.0, :description_weight, :body_weight, 1.0) AS score,
    snippet(wiki_fts, 3, '<mark>', '</mark>', '...', :snippet_tokens)
        AS body_snippet,
    snippet(wiki_fts, 2, '<mark>', '</mark>', '...', :snippet_tokens)
        AS description_snippet,
    snippet(wiki_fts, 1, '<mark>', '</mark>', '...', :snippet_tokens)
        AS title_snippet
FROM wiki_fts
JOIN wiki_index w ON w.rowid = wiki_fts.rowid
WHERE wiki_fts MATCH :match
"""


def _stable_dedupe(tokens: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def _query_tokens(query: str) -> list[str]:
    if len(query) > MAX_QUERY_BYTES or len(query.encode("utf-8")) > MAX_QUERY_BYTES:
        raise ValueError(f"query exceeds {MAX_QUERY_BYTES} UTF-8 bytes")
    tokens = _QUERY_TOKENS.findall(query.lower())
    if not tokens:
        raise ValueError("query contains no searchable terms")
    if len(tokens) > MAX_QUERY_TOKENS:
        raise ValueError(f"query contains too many searchable terms (maximum {MAX_QUERY_TOKENS})")
    return tokens


def _phrase_indexes(tokens: list[str], phrase: tuple[str, ...]) -> set[int]:
    indexes: set[int] = set()
    width = len(phrase)
    for start in range(len(tokens) - width + 1):
        if tuple(tokens[start : start + width]) == phrase:
            indexes.update(range(start, start + width))
    return indexes


def _how_does_handle_indexes(tokens: list[str]) -> set[int]:
    indexes: set[int] = set()
    for start in range(len(tokens) - 2):
        if tokens[start : start + 2] != ["how", "does"]:
            continue
        try:
            handle = tokens.index("handle", start + 2)
        except ValueError:
            continue
        indexes.update({start, start + 1, handle})
    return indexes


def _why_is_showing_indexes(tokens: list[str]) -> set[int]:
    indexes: set[int] = set()
    for start in range(len(tokens) - 2):
        if tokens[start : start + 2] != ["why", "is"]:
            continue
        try:
            indexes.add(tokens.index("showing", start + 2))
        except ValueError:
            continue
    return indexes


def _drop_semantic_scaffolding(tokens: list[str]) -> list[str]:
    rejected = {
        index
        for phrase in _SEMANTIC_SCAFFOLDING_PHRASES
        for index in _phrase_indexes(tokens, phrase)
    }
    rejected.update(_how_does_handle_indexes(tokens))
    rejected.update(_why_is_showing_indexes(tokens))
    return [token for index, token in enumerate(tokens) if index not in rejected]


def production_ranker_metadata() -> dict[str, object]:
    """Describe the promoted production retrieval algorithm."""
    return {
        "name": _WINNER_SEARCH_ENGINE,
        "query_strategy": "strict-and-weighted-fts5",
        "zero_hit_fallback": "broad-or-weighted-fts5",
        "token_strategy": "lowercase-alphanumeric-safe-stable-dedupe",
        "removed_scaffolding": (
            "instead of",
            "how does ... handle",
            "how many",
            "why is ... showing",
            "switch from",
        ),
        "column_weights": {
            "slug": 1.0,
            "title": 1.0,
            "description": _WINNER_DESCRIPTION_WEIGHT,
            "body": _WINNER_BODY_WEIGHT,
            "tags": 1.0,
        },
        "snippet_tokens": _WINNER_SNIPPET_TOKENS,
        "tie_break": "score-then-slug",
        "safe_query_boundary": "alphanumeric tokens only, capped before FTS5 MATCH",
        "max_query_bytes": MAX_QUERY_BYTES,
        "max_query_tokens": MAX_QUERY_TOKENS,
    }


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
        return " OR ".join(_query_tokens(query))

    def _semantic_tokens(self, query: str) -> list[str]:
        raw_tokens = _query_tokens(query)
        tokens = _drop_semantic_scaffolding(raw_tokens)
        tokens = [token for token in tokens if token not in _QUERY_STOP_WORDS]
        tokens = _stable_dedupe(tokens)
        return tokens or _stable_dedupe(raw_tokens)

    def search_fts(self, query: str, top_k: int) -> list[tuple[str, float]]:
        """Raw (slug, score) pairs ordered by ascending bm25 score."""
        match = self._match_query(query)
        with self._lock:
            rows = self._conn.execute(
                _LEGACY_BASE_SQL + " ORDER BY score, w.slug LIMIT :top_k",
                {"match": match, "top_k": top_k},
            ).fetchall()
        return [(str(row["slug"]), float(row["score"])) for row in rows]

    def retrieve_legacy_or(
        self,
        query: str,
        top_k: int | None = None,
        node_type: str | None = None,
        time_range: tuple[str, str] | None = None,
        tags: list[str] | None = None,
        include_expired: bool = False,
        include_inactive: bool = False,
    ) -> RecallResult:
        """Run the pre-promotion SQLite FTS5 OR baseline."""
        limit = self._validated_limit(top_k)
        started = time.perf_counter()
        match = self._match_query(query)
        rows, total = self._execute_ranked_query(
            _LEGACY_BASE_SQL,
            match,
            limit=limit,
            node_type=node_type,
            time_range=time_range,
            tags=tags,
            include_expired=include_expired,
            include_inactive=include_inactive,
        )
        hits = self._hits_from_rows(rows, limit)
        self.record_access(hits)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return RecallResult(
            query=query,
            hits=hits,
            total_indexed=total,
            search_engine="sqlite-fts5-bm25",
            search_time_ms=round(elapsed_ms, 3),
        )

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        node_type: str | None = None,
        time_range: tuple[str, str] | None = None,
        tags: list[str] | None = None,
        include_expired: bool = False,
        include_inactive: bool = False,
        scope: str = "global",
        project_id: str | None = None,
    ) -> RecallResult:
        """Search the index and return ranked hits with metadata.

        The query is reduced to safe alphanumeric semantic tokens, searched
        with strict AND matching, and retried with OR only when strict matching
        returns no rows. Untrusted input never reaches the FTS5 MATCH parser.
        Hits are ordered by ascending BM25 score — lower is better, per SQLite
        FTS5. Nodes past ``expires_at`` or ``valid_to`` are invisible unless
        the caller opts in; this is how soft-forgetting hides memories.

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
            ValueError: Query has no searchable terms, query work exceeds the
                retriever cap, or ``top_k`` outside [1, 100].
        """
        result = self.retrieve_without_access(
            query,
            top_k=top_k,
            node_type=node_type,
            time_range=time_range,
            tags=tags,
            include_expired=include_expired,
            include_inactive=include_inactive,
            scope=scope,
            project_id=project_id,
        )
        self.record_access(result.hits)
        return result

    def retrieve_without_access(
        self,
        query: str,
        top_k: int | None = None,
        node_type: str | None = None,
        time_range: tuple[str, str] | None = None,
        tags: list[str] | None = None,
        include_expired: bool = False,
        include_inactive: bool = False,
        scope: str = "global",
        project_id: str | None = None,
    ) -> RecallResult:
        """Search the promoted ranker without mutating access statistics."""
        limit = self._validated_limit(top_k)
        started = time.perf_counter()

        tokens = self._semantic_tokens(query)
        rows, total = self._execute_ranked_query(
            _WINNER_SELECT_SQL,
            " AND ".join(tokens),
            limit=limit,
            node_type=node_type,
            time_range=time_range,
            tags=tags,
            include_expired=include_expired,
            include_inactive=include_inactive,
            scope=scope,
            project_id=project_id,
            extra_params={
                "body_weight": _WINNER_BODY_WEIGHT,
                "description_weight": _WINNER_DESCRIPTION_WEIGHT,
                "snippet_tokens": _WINNER_SNIPPET_TOKENS,
            },
        )
        if not rows:
            rows, total = self._execute_ranked_query(
                _WINNER_SELECT_SQL,
                " OR ".join(tokens),
                limit=limit,
                node_type=node_type,
                time_range=time_range,
                tags=tags,
                include_expired=include_expired,
                include_inactive=include_inactive,
                scope=scope,
                project_id=project_id,
                extra_params={
                    "body_weight": _WINNER_BODY_WEIGHT,
                    "description_weight": _WINNER_DESCRIPTION_WEIGHT,
                    "snippet_tokens": _WINNER_SNIPPET_TOKENS,
                },
            )

        hits = self._hits_from_rows(rows, limit)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return RecallResult(
            query=query,
            hits=hits,
            total_indexed=total,
            search_engine=_WINNER_SEARCH_ENGINE,
            search_time_ms=round(elapsed_ms, 3),
        )

    def _validated_limit(self, top_k: int | None) -> int:
        limit = top_k if top_k is not None else self.default_top_k
        if not 1 <= limit <= 100:
            raise ValueError("top_k must be between 1 and 100")
        return limit

    def _execute_ranked_query(
        self,
        base_sql: str,
        match: str,
        *,
        limit: int,
        node_type: str | None,
        time_range: tuple[str, str] | None,
        tags: list[str] | None,
        include_expired: bool,
        include_inactive: bool,
        scope: str = "global",
        project_id: str | None = None,
        extra_params: dict[str, object] | None = None,
    ) -> tuple[list[sqlite3.Row], int]:
        clauses, params = self._eligibility_filters(
            node_type=node_type,
            time_range=time_range,
            tags=tags,
            include_expired=include_expired,
            include_inactive=include_inactive,
            scope=scope,
            project_id=project_id,
        )
        params.update(extra_params or {})
        params.update({"match": match, "top_k": limit})
        sql = base_sql
        if clauses:
            sql += " AND " + " AND ".join(clauses)
        sql += " ORDER BY score, w.slug LIMIT :top_k"

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
            total = self._conn.execute("SELECT COUNT(*) AS n FROM wiki_index").fetchone()
        return self._dedupe_rows(rows), int(total["n"])

    def _hits_from_rows(self, rows: list[sqlite3.Row], limit: int) -> list[RecallHit]:
        links = self._links(rows)
        return [
            self._to_hit(row, rank, links.get(self._row_key(row), []))
            for rank, row in enumerate(rows[:limit], start=1)
        ]

    def _eligibility_filters(
        self,
        *,
        node_type: str | None,
        time_range: tuple[str, str] | None,
        tags: list[str] | None,
        include_expired: bool,
        include_inactive: bool,
        scope: str = "global",
        project_id: str | None = None,
    ) -> tuple[list[str], dict[str, object]]:
        clauses: list[str] = []
        params: dict[str, object] = {}
        if node_type is not None:
            clauses.append("w.node_type = :node_type")
            params["node_type"] = node_type
        if scope == "project":
            if not project_id:
                raise ValueError("project_id is required for project recall")
            clauses.append("w.scope = 'project' AND w.project_id = :project_id")
            params["project_id"] = project_id
        elif scope != "global":
            raise ValueError("scope must be 'global' or 'project'")
        if time_range is not None:
            clauses.append("w.updated >= :time_from AND w.updated <= :time_to")
            params["time_from"], params["time_to"] = time_range
        for index, tag in enumerate(tags or []):
            key = f"tag_{index}"
            clauses.append(f"w.tags LIKE :{key}")
            params[key] = f'%"{tag}"%'
        if not include_expired:
            now = utc_now_iso()
            clauses.append("(w.expires_at IS NULL OR w.expires_at > :now)")
            clauses.append("(w.valid_to IS NULL OR w.valid_to > :now)")
            params["now"] = now
        if not include_inactive:
            clauses.append("(w.status IS NULL OR w.status = 'active')")
        return clauses, params

    @staticmethod
    def _dedupe_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
        deduped: list[sqlite3.Row] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            key = (str(row["scope"]), str(row["project_id"]), str(row["slug"]))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

    def close(self) -> None:
        self._conn.close()

    def record_access(self, hits: Sequence[RecallHit]) -> None:
        """Recall side effect: bump access_count/last_access per hit (§9.2)."""
        now = utc_now_iso()
        with self._lock, self._conn:
            self._conn.executemany(
                "UPDATE wiki_index SET access_count = access_count + 1, last_access = ?"
                " WHERE slug = ? AND scope = ? AND project_id = ?",
                [(now, hit.slug, hit.scope, hit.project_id or "") for hit in hits],
            )

    def _links(self, rows: list[sqlite3.Row]) -> dict[tuple[str, str, str], list[str]]:
        if not rows:
            return {}
        keys = [self._row_key(row) for row in rows]
        placeholders = ",".join("(?, ?, ?)" for _ in keys)
        params = tuple(value for key in keys for value in key)
        sql = (
            "SELECT source_scope, source_project_id, source_slug, target_slug FROM wiki_links "  # noqa: S608
            f"WHERE (source_scope, source_project_id, source_slug) IN ({placeholders}) "
            "ORDER BY source_scope, source_project_id, source_slug, target_slug"
        )
        with self._lock:
            link_rows = self._conn.execute(sql, params).fetchall()
        links: dict[tuple[str, str, str], list[str]] = {}
        for row in link_rows:
            key = (
                str(row["source_scope"]),
                str(row["source_project_id"]),
                str(row["source_slug"]),
            )
            links.setdefault(key, []).append(str(row["target_slug"]))
        return links

    @staticmethod
    def _row_key(row: sqlite3.Row) -> tuple[str, str, str]:
        return (str(row["scope"]), str(row["project_id"]), str(row["slug"]))

    def _to_hit(self, row: sqlite3.Row, rank: int, links: list[str]) -> RecallHit:
        body_snippet = str(row["body_snippet"])
        description_snippet = str(row["description_snippet"])
        title_snippet = str(row["title_snippet"])
        # FTS5 snippet() returns text even when the column itself has no
        # match, so "where did it match" is detected via the <mark> tags.
        if "<mark>" in body_snippet:
            snippet, source = body_snippet, "body"
        elif "<mark>" in description_snippet:
            snippet, source = description_snippet, "description"
        else:
            snippet, source = title_snippet, "title"
        try:
            status = str(row["status"])
        except (IndexError, KeyError):
            status = "active"
        return RecallHit(
            slug=str(row["slug"]),
            status=status,
            file_path=str(row["file_path"]),
            title=str(row["title"]),
            description=str(row["description"] or ""),
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
            scope=str(row["scope"]),
            project_id=str(row["project_id"]) or None,
            project_label=str(row["project_label"]) if row["project_label"] else None,
        )
