"""SQLite secondary index with FTS5 full-text search (spec §6.2, §7 Utility 2).

The index is a rebuildable mirror of the wiki. Deviations from the spec DDL,
both deliberate:
- ``wiki_index`` carries a ``body`` column. The spec's external-content FTS
  table has no body to mirror, and its triggers insert ``''`` — full-text
  search would never index bodies.
- The ai/ad/au triggers sync real body text.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import cast

from memex.domain.errors import IndexManagerError
from memex.domain.models import WikiNode, utc_now_iso

SCHEMA_VERSION = "5"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS index_meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wiki_index (
    id            TEXT PRIMARY KEY,
    slug          TEXT NOT NULL,
    scope         TEXT NOT NULL DEFAULT 'global',
    project_id    TEXT NOT NULL DEFAULT '',
    project_label TEXT,
    file_path     TEXT UNIQUE NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    node_type     TEXT NOT NULL,
    importance    REAL NOT NULL DEFAULT 0.5,
    status        TEXT NOT NULL DEFAULT 'active',
    occurred_at   TEXT,
    source        TEXT,
    harness       TEXT,
    confidence    TEXT,
    tags          TEXT NOT NULL DEFAULT '[]',
    created       TEXT NOT NULL,
    updated       TEXT NOT NULL,
    access_count  INTEGER NOT NULL DEFAULT 0,
    last_access   TEXT,
    expires_at    TEXT,
    valid_from    TEXT,
    valid_to      TEXT,
    content_hash  TEXT NOT NULL,
    transcript_ref TEXT,
    body          TEXT NOT NULL DEFAULT ''
    , UNIQUE(scope, project_id, node_type, slug)
);

CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
    slug,
    title,
    description,
    body,
    tags,
    content='wiki_index',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS wiki_index_ai AFTER INSERT ON wiki_index BEGIN
    INSERT INTO wiki_fts(rowid, slug, title, description, body, tags)
    VALUES (new.rowid, new.slug, new.title, new.description, new.body, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS wiki_index_ad AFTER DELETE ON wiki_index BEGIN
    INSERT INTO wiki_fts(wiki_fts, rowid, slug, title, description, body, tags)
    VALUES ('delete', old.rowid, old.slug, old.title, old.description, old.body, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS wiki_index_au AFTER UPDATE ON wiki_index BEGIN
    INSERT INTO wiki_fts(wiki_fts, rowid, slug, title, description, body, tags)
    VALUES ('delete', old.rowid, old.slug, old.title, old.description, old.body, old.tags);
    INSERT INTO wiki_fts(rowid, slug, title, description, body, tags)
    VALUES (new.rowid, new.slug, new.title, new.description, new.body, new.tags);
END;

CREATE TABLE IF NOT EXISTS wiki_links (
    source_scope TEXT NOT NULL DEFAULT 'global',
    source_project_id TEXT NOT NULL DEFAULT '',
    source_slug TEXT NOT NULL,
    target_slug TEXT NOT NULL,
    PRIMARY KEY (source_scope, source_project_id, source_slug, target_slug)
);

CREATE INDEX IF NOT EXISTS idx_wiki_index_type ON wiki_index(node_type);
CREATE INDEX IF NOT EXISTS idx_wiki_index_scope ON wiki_index(scope, project_id);
CREATE INDEX IF NOT EXISTS idx_wiki_index_updated ON wiki_index(updated);
CREATE INDEX IF NOT EXISTS idx_wiki_index_importance ON wiki_index(importance);
CREATE INDEX IF NOT EXISTS idx_wiki_index_access ON wiki_index(last_access);
CREATE INDEX IF NOT EXISTS idx_wiki_links_source
    ON wiki_links(source_scope, source_project_id, source_slug);
CREATE INDEX IF NOT EXISTS idx_wiki_links_target ON wiki_links(target_slug);
"""

_SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")

_UPSERT = """
INSERT INTO wiki_index (
    id, slug, scope, project_id, project_label, file_path, title, description, node_type, importance, tags, created, updated,
    access_count, last_access, expires_at, valid_from, valid_to,
    content_hash, transcript_ref, body, status, occurred_at, source, harness, confidence
) VALUES (
    :id, :slug, :scope, :project_id, :project_label, :file_path, :title, :description, :node_type, :importance, :tags, :created, :updated,
    :access_count, :last_access, :expires_at, :valid_from, :valid_to,
    :content_hash, :transcript_ref, :body, :status, :occurred_at, :source, :harness, :confidence
)
ON CONFLICT(scope, project_id, node_type, slug) DO UPDATE SET
    id = excluded.id,
    file_path = excluded.file_path,
    title = excluded.title,
    description = excluded.description,
    node_type = excluded.node_type,
    importance = excluded.importance,
    tags = excluded.tags,
    updated = excluded.updated,
    expires_at = excluded.expires_at,
    valid_from = excluded.valid_from,
    valid_to = excluded.valid_to,
    content_hash = excluded.content_hash,
    transcript_ref = excluded.transcript_ref,
    body = excluded.body,
    status = excluded.status,
    occurred_at = excluded.occurred_at,
    source = excluded.source,
    harness = excluded.harness,
    confidence = excluded.confidence
"""


def node_record(node: WikiNode) -> dict[str, object]:
    """Map a WikiNode to an index row, including the mirrored body text."""
    return {
        "id": node.id,
        "slug": node.slug,
        "scope": node.scope,
        "project_id": node.project_id or "",
        "project_label": node.project_label,
        "file_path": node.file_path or "",
        "title": node.title,
        "description": node.description,
        "node_type": node.type,
        "importance": node.importance,
        "tags": json.dumps(node.tags),
        "created": node.created,
        "updated": node.updated,
        "access_count": node.access_count,
        "last_access": node.last_access,
        "expires_at": node.expires_at,
        "valid_from": node.valid_from,
        "valid_to": node.valid_to,
        "content_hash": node.content_hash,
        "transcript_ref": node.transcript_ref,
        "body": node.body,
        "status": node.status,
        "occurred_at": node.occurred_at,
        "source": node.source,
        "harness": node.harness,
        "confidence": node.confidence,
    }


def check_slug(slug: str) -> str:
    """Reject anything that is not a plain kebab slug (untrusted input)."""
    normalized = slug.strip().lower()
    if not _SAFE_SLUG.match(normalized):
        raise IndexManagerError(f"invalid slug: {slug!r}")
    return normalized


class IndexManager:
    """Owns mem.db: DDL, WAL, upserts, and metadata bookkeeping."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._needs_rebuild = False
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.initialize()

    @property
    def connection(self) -> sqlite3.Connection:
        """Shared connection for collaborators (LinkManager, watcher)."""
        return self._conn

    def needs_rebuild(self) -> bool:
        """True when the on-disk table shape predates the current schema.

        Checks real columns, not the meta stamp: initialize() writes the
        current stamp on every open, so the stamp cannot detect an upgrade
        from a store the new code just opened. mem.db is disposable by
        charter: a mismatch drops and rebuilds from the wiki, never DDL.
        """
        try:
            columns = {
                row["name"]
                for row in self._conn.execute("PRAGMA table_info(wiki_index)").fetchall()
            }
        except sqlite3.OperationalError:
            return True  # no table at all
        if not columns:
            return True
        expected = {
            "status",
            "occurred_at",
            "source",
            "harness",
            "confidence",
            "scope",
            "project_id",
            "project_label",
            "description",
        }
        return self._needs_rebuild or not expected <= columns

    def drop_for_rebuild(self) -> None:
        with self._lock:
            self._conn.executescript(
                "DROP TABLE IF EXISTS wiki_links;"
                "DROP TABLE IF EXISTS wiki_fts;"
                "DROP TABLE IF EXISTS wiki_index;"
                "DROP TABLE IF EXISTS index_meta;"
            )
            self._conn.commit()
            self._needs_rebuild = False
        self.initialize()

    def initialize(self) -> None:
        with self._lock:
            if self._index_schema_is_incompatible():
                self._needs_rebuild = True
                self._conn.executescript(
                    "DROP TABLE IF EXISTS wiki_links;"
                    "DROP TABLE IF EXISTS wiki_fts;"
                    "DROP TABLE IF EXISTS wiki_index;"
                    "DROP TABLE IF EXISTS index_meta;"
                )
            elif self._links_schema_is_incompatible():
                self._needs_rebuild = True
                self._conn.execute("DROP TABLE IF EXISTS wiki_links")
            self._conn.executescript(_SCHEMA)
            self.set_meta("schema_version", SCHEMA_VERSION)
            self._conn.commit()

    def _index_schema_is_incompatible(self) -> bool:
        """Detect a disposable pre-namespace or pre-description index."""
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'wiki_index'"
        ).fetchone()
        if row is None:
            return False
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(wiki_index)")}
        return not {"scope", "project_id", "project_label", "description"} <= columns

    def _links_schema_is_incompatible(self) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'wiki_links'"
        ).fetchone()
        if row is None:
            return False
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(wiki_links)")}
        return not {"source_scope", "source_project_id"} <= columns

    def build(self, nodes: list[WikiNode]) -> int:
        """Bulk upsert. Returns the number of records written."""
        self.initialize()
        with self._lock:
            try:
                self._conn.executemany(_UPSERT, [node_record(node) for node in nodes])
                self._conn.commit()
            except sqlite3.Error as exc:
                self._conn.rollback()
                raise IndexManagerError(f"index build failed: {exc}") from exc
        return len(nodes)

    def update_record(self, node: WikiNode) -> None:
        """Upsert one node."""
        self.initialize()
        with self._lock:
            try:
                self._conn.execute(_UPSERT, node_record(node))
                self._conn.commit()
            except sqlite3.Error as exc:
                self._conn.rollback()
                raise IndexManagerError(f"index update failed for {node.slug!r}: {exc}") from exc

    def remove_record(
        self,
        slug: str,
        *,
        scope: str | None = None,
        project_id: str | None = None,
        node_type: str | None = None,
    ) -> None:
        safe = check_slug(slug)
        query = (
            "DELETE FROM wiki_index WHERE slug = ?"
            " AND (? IS NULL OR scope = ?)"
            " AND (? IS NULL OR project_id = ?)"
            " AND (? IS NULL OR node_type = ?)"
        )
        params = (safe, scope, scope, project_id, project_id, node_type, node_type)
        with self._lock:
            link_params = (safe, scope, scope, project_id, project_id)
            self._conn.execute(
                "DELETE FROM wiki_links WHERE source_slug = ?"
                " AND (? IS NULL OR source_scope = ?)"
                " AND (? IS NULL OR source_project_id = ?)",
                link_params,
            )
            self._conn.execute(query, params)
            self._conn.execute(
                "DELETE FROM wiki_links WHERE target_slug = ?"
                " AND NOT EXISTS (SELECT 1 FROM wiki_index WHERE slug = ?)",
                (safe, safe),
            )
            self._conn.commit()

    def reset(self) -> None:
        """Truncate the index (wiki_index, FTS mirror, links)."""
        self.initialize()
        with self._lock:
            self._conn.execute("DELETE FROM wiki_links")
            self._conn.execute("DELETE FROM wiki_index")
            self._conn.commit()

    def get(
        self,
        slug: str,
        *,
        scope: str | None = None,
        project_id: str | None = None,
        node_type: str | None = None,
    ) -> sqlite3.Row | None:
        safe = check_slug(slug)
        query = (
            "SELECT * FROM wiki_index WHERE slug = ?"
            " AND (? IS NULL OR scope = ?)"
            " AND (? IS NULL OR project_id = ?)"
            " AND (? IS NULL OR node_type = ?)"
            " ORDER BY scope, project_id, node_type"
        )
        params = (safe, scope, scope, project_id, project_id, node_type, node_type)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            raise IndexManagerError(f"ambiguous index row for slug: {slug!r}")
        return cast(sqlite3.Row, rows[0])

    def get_all_slugs(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT slug FROM wiki_index ORDER BY slug").fetchall()
        return [str(row["slug"]) for row in rows]

    def get_all_records(self) -> list[sqlite3.Row]:
        """Return index rows for namespace-aware maintenance operations."""
        with self._lock:
            return self._conn.execute("SELECT * FROM wiki_index").fetchall()

    def get_by_type(self, node_type: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT slug FROM wiki_index WHERE node_type = ? ORDER BY slug", (node_type,)
            ).fetchall()
        return [str(row["slug"]) for row in rows]

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM wiki_index").fetchone()
        return int(row["n"])

    def increment_access(self, slug: str) -> None:
        """Bump access_count and last_access for a recalled node."""
        safe = check_slug(slug)
        with self._lock:
            self._conn.execute(
                "UPDATE wiki_index SET access_count = access_count + 1, last_access = ?"
                " WHERE slug = ?",
                (utc_now_iso(), safe),
            )
            self._conn.commit()

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO index_meta (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()

    def get_meta(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM index_meta WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row is not None else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()
