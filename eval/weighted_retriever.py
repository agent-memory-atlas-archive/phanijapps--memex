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
    RRF_RANK_CONSTANT,
    CandidateSource,
    RankedCandidate,
    fuse_candidate_sources,
)
from memex.domain.models import RecallHit, RecallResult, utc_now_iso

_QUERY_TOKENS = re.compile(r"[a-z0-9]+")
_CANDIDATE_SNIPPET_TOKENS = 12
_SOURCE_LIMIT_MULTIPLIER = 4
_SOURCE_LIMIT_CAP = 400
_FIELD_CHANNELS = ("title", "body", "tags", "slug")
_FIELD_CHANNEL_WEIGHTS = {
    "title": DEFAULT_LEXICAL_RECIPE.title_weight,
    "body": DEFAULT_LEXICAL_RECIPE.body_weight,
    "tags": DEFAULT_LEXICAL_RECIPE.tag_weight,
    "slug": DEFAULT_LEXICAL_RECIPE.title_weight,
}
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
SELECT w.slug, bm25(wiki_fts) AS score
FROM wiki_fts
JOIN wiki_index w ON w.rowid = wiki_fts.rowid
WHERE wiki_fts MATCH :match
  AND (w.valid_from IS NULL OR w.valid_from <= :now)
  AND (w.valid_until IS NULL OR w.valid_until >= :now)
  AND (w.status IS NULL OR w.status = 'active')
ORDER BY score, w.slug
LIMIT :limit
"""

_HIT_SQL = """
SELECT
    w.slug, w.file_path, w.title, w.node_type, w.importance,
    w.tags, w.created, w.timestamp, w.updated_at, w.last_access, w.transcript_ref, w.status,
    snippet(wiki_fts, 2, '<mark>', '</mark>', '...', 12)
        AS body_snippet,
    snippet(wiki_fts, 1, '<mark>', '</mark>', '...', 12)
        AS title_snippet
FROM wiki_fts
JOIN wiki_index w ON w.rowid = wiki_fts.rowid
WHERE wiki_fts MATCH ?
  AND w.slug IN ({placeholders})
"""


def _accepted_tokens(query: str) -> list[str]:
    raw_tokens = _QUERY_TOKENS.findall(query.lower())
    tokens = [token for token in raw_tokens if token not in _QUERY_STOP_WORDS] or raw_tokens
    if not tokens:
        raise ValueError("query contains no searchable terms")
    return tokens


class WeightedLexicalRetriever:
    """Run the weighted lexical candidate across the full recall boundary."""

    identity = "field-channel-rrf-k60"

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
        tokens = _accepted_tokens(query)

        started = time.perf_counter()
        now = utc_now_iso()
        candidate_limit = min(top_k * _SOURCE_LIMIT_MULTIPLIER, _SOURCE_LIMIT_CAP)
        sources = [
            self._search_channel(field, tokens, candidate_limit, now) for field in _FIELD_CHANNELS
        ]
        ranked = fuse_candidate_sources(sources, top_k=top_k)
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

    def metadata(self) -> dict[str, object]:
        return {
            **DEFAULT_LEXICAL_RECIPE.metadata(),
            "name": self.identity,
            "query_strategy": "independent-field-channel-rrf",
            "channels": _FIELD_CHANNELS,
            "channel_weights": _FIELD_CHANNEL_WEIGHTS,
            "source_limit_multiplier": _SOURCE_LIMIT_MULTIPLIER,
            "source_limit_cap": _SOURCE_LIMIT_CAP,
            "rank_constant": RRF_RANK_CONSTANT,
            "final_tie_break": "descending-rrf-score-then-ascending-slug",
            "snippet_tokens": _CANDIDATE_SNIPPET_TOKENS,
            "complete": True,
        }

    def _search_channel(
        self,
        field: str,
        tokens: Sequence[str],
        limit: int,
        now: str,
    ) -> CandidateSource:
        match = " OR ".join(f"{field}:{token}" for token in tokens)
        rows = self._conn.execute(
            _SOURCE_SQL,
            {
                "match": match,
                "limit": limit,
                "now": now,
            },
        ).fetchall()
        ranked = [
            RankedCandidate(str(row["slug"]), rank, float(row["score"]))
            for rank, row in enumerate(rows, start=1)
        ]
        return CandidateSource(field, ranked, _FIELD_CHANNEL_WEIGHTS[field])

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
            timestamp=str(row["timestamp"]),
            updated_at=str(row["updated_at"]),
            last_access=row["last_access"],
            transcript_ref=row["transcript_ref"],
            links=links,
            status=str(row["status"]),
        )
