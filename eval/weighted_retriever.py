"""Evaluation-only weighted lexical retriever with production-shaped results."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path

from eval.candidates import (
    DEFAULT_LEXICAL_RECIPE,
    CandidateSource,
    RankedCandidate,
    fuse_candidate_sources,
)
from memex.domain.models import RecallHit, RecallResult, utc_now_iso

_QUERY_TOKENS = re.compile(r"[a-z0-9]+")
_CANDIDATE_SNIPPET_TOKENS = 12
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
_SOURCE_SQL = """
SELECT w.slug, bm25(
    wiki_fts, :slug_weight, :title_weight, :body_weight, :tag_weight
) AS score
FROM wiki_fts
JOIN wiki_index w ON w.rowid = wiki_fts.rowid
WHERE wiki_fts MATCH :match
  AND (w.expires_at IS NULL OR w.expires_at >= :now)
  AND (w.valid_to IS NULL OR w.valid_to >= :now)
  AND (w.status IS NULL OR w.status = 'active')
ORDER BY score, w.slug
LIMIT :limit
"""

_HIT_SQL = """
SELECT
    w.slug, w.file_path, w.title, w.node_type, w.importance,
    w.tags, w.created, w.updated, w.last_access, w.transcript_ref, w.status,
    snippet(wiki_fts, 2, '<mark>', '</mark>', '...', 12)
        AS body_snippet,
    snippet(wiki_fts, 1, '<mark>', '</mark>', '...', 12)
        AS title_snippet
FROM wiki_fts
JOIN wiki_index w ON w.rowid = wiki_fts.rowid
WHERE wiki_fts MATCH ?
  AND w.slug IN ({placeholders})
"""


class WeightedLexicalRetriever:
    """Run the weighted lexical candidate across the full recall boundary."""

    identity = DEFAULT_LEXICAL_RECIPE.name

    def __init__(self, db_path: Path) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        total = self._conn.execute("SELECT COUNT(*) FROM wiki_index").fetchone()
        self._total_indexed = int(total[0])

    def close(self) -> None:
        self._conn.close()

    def retrieve(self, query: str, *, top_k: int = 10) -> RecallResult:
        """Return fused hits and record access exactly once per returned page."""
        if not 1 <= top_k <= 100:
            raise ValueError("top_k must be between 1 and 100")
        raw_tokens = _QUERY_TOKENS.findall(query.lower())
        tokens = [token for token in raw_tokens if token not in _QUERY_STOP_WORDS] or raw_tokens
        if not tokens:
            raise ValueError("query contains no searchable terms")

        started = time.perf_counter()
        now = utc_now_iso()
        candidate_limit = min(top_k * 4, 400)
        strict = self._search(" AND ".join(tokens), candidate_limit, now)
        if len(strict) >= DEFAULT_LEXICAL_RECIPE.min_strict_candidates:
            ranked = strict
        else:
            broad = self._search(" OR ".join(tokens), candidate_limit, now)
            ranked = fuse_candidate_sources(
                [CandidateSource("strict", strict, 3.0), CandidateSource("backoff", broad)],
                top_k=candidate_limit,
            )
        ranked = self._diversify_titles(ranked, top_k)
        hits = self._hydrate(ranked, " OR ".join(tokens))
        self._record_access(hits)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return RecallResult(
            query=query,
            hits=hits,
            total_indexed=self._total_indexed,
            search_engine=self.identity,
            search_time_ms=round(elapsed_ms, 3),
        )

    def metadata(self) -> dict[str, str | int | float | bool]:
        return {
            **DEFAULT_LEXICAL_RECIPE.metadata(),
            "query_strategy": "field-qualified-and-with-or-backoff",
            "snippet_tokens": _CANDIDATE_SNIPPET_TOKENS,
            "complete": True,
        }

    def _search(self, match: str, limit: int, now: str) -> list[RankedCandidate]:
        rows = self._conn.execute(
            _SOURCE_SQL,
            {
                "match": match,
                "limit": limit,
                "now": now,
                "slug_weight": 0.0,
                "title_weight": DEFAULT_LEXICAL_RECIPE.title_weight,
                "body_weight": DEFAULT_LEXICAL_RECIPE.body_weight,
                "tag_weight": DEFAULT_LEXICAL_RECIPE.tag_weight,
            },
        ).fetchall()
        return [
            RankedCandidate(str(row["slug"]), rank, float(row["score"]))
            for rank, row in enumerate(rows, start=1)
        ]

    def _hydrate(
        self,
        ranked: Sequence[RankedCandidate],
        broad_match: str,
    ) -> list[RecallHit]:
        if not ranked:
            return []
        placeholders = ",".join("?" for _ in ranked)
        sql = _HIT_SQL.format(placeholders=placeholders)
        rows = self._conn.execute(
            sql,
            (broad_match, *(candidate.slug for candidate in ranked)),
        ).fetchall()
        by_slug = {str(row["slug"]): row for row in rows}
        links = self._links([candidate.slug for candidate in ranked])
        return [
            self._to_hit(by_slug[candidate.slug], candidate, links.get(candidate.slug, []))
            for candidate in ranked
            if candidate.slug in by_slug
        ]

    def _links(self, slugs: Sequence[str]) -> dict[str, list[str]]:
        placeholders = ",".join("?" for _ in slugs)
        sql = (
            "SELECT source_slug, target_slug FROM wiki_links "  # noqa: S608
            f"WHERE source_slug IN ({placeholders}) ORDER BY source_slug, target_slug"
        )
        rows = self._conn.execute(sql, tuple(slugs)).fetchall()
        links: dict[str, list[str]] = {}
        for row in rows:
            links.setdefault(str(row["source_slug"]), []).append(str(row["target_slug"]))
        return links

    def _diversify_titles(
        self,
        ranked: Sequence[RankedCandidate],
        top_k: int,
    ) -> list[RankedCandidate]:
        if not ranked:
            return []
        placeholders = ",".join("?" for _ in ranked)
        sql = f"SELECT slug, title FROM wiki_index WHERE slug IN ({placeholders})"  # noqa: S608
        rows = self._conn.execute(sql, tuple(candidate.slug for candidate in ranked)).fetchall()
        titles = {str(row["slug"]): str(row["title"]).casefold() for row in rows}
        selected: list[RankedCandidate] = []
        deferred: list[RankedCandidate] = []
        seen_titles: set[str] = set()
        for candidate in ranked:
            title = titles.get(candidate.slug, candidate.slug)
            if title in seen_titles:
                deferred.append(candidate)
                continue
            seen_titles.add(title)
            selected.append(candidate)
            if len(selected) == top_k:
                break
        if len(selected) < top_k:
            selected.extend(deferred[: top_k - len(selected)])
        return [
            RankedCandidate(candidate.slug, rank, candidate.score)
            for rank, candidate in enumerate(selected, start=1)
        ]

    def _record_access(self, hits: Sequence[RecallHit]) -> None:
        now = utc_now_iso()
        with self._conn:
            self._conn.executemany(
                "UPDATE wiki_index SET access_count = access_count + 1, last_access = ? "
                "WHERE slug = ?",
                [(now, hit.slug) for hit in hits],
            )

    @staticmethod
    def _to_hit(
        row: sqlite3.Row,
        candidate: RankedCandidate,
        links: list[str],
    ) -> RecallHit:
        body_snippet = str(row["body_snippet"])
        title_snippet = str(row["title_snippet"])
        if "<mark>" in body_snippet:
            snippet, source = body_snippet, "body"
        else:
            snippet, source = title_snippet, "title"
        return RecallHit(
            slug=str(row["slug"]),
            file_path=str(row["file_path"]),
            title=str(row["title"]),
            node_type=str(row["node_type"]),
            importance=float(row["importance"]),
            score=candidate.score,
            rank=candidate.rank,
            snippet=snippet,
            snippet_source=source,
            tags=json.loads(str(row["tags"])),
            created=str(row["created"]),
            updated=str(row["updated"]),
            last_access=row["last_access"],
            transcript_ref=row["transcript_ref"],
            links=links,
            status=str(row["status"]),
        )
