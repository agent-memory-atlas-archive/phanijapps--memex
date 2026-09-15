"""Typed models for every public input and output contract (spec §4, §5).

Timestamps are ISO8601 UTC strings ending in ``Z``. Constructors validate
untrusted input eagerly so invalid states stay unrepresentable past the
boundary.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

NODE_TYPES: tuple[str, ...] = ("entity", "preference", "procedure", "summary", "episode")
NON_EPISODE_TYPES: tuple[str, ...] = tuple(t for t in NODE_TYPES if t != "episode")
TURN_ROLES: tuple[str, ...] = ("user", "agent", "tool")
FORGET_MODES: tuple[str, ...] = ("hard", "soft", "decay")

# Wire-level enums; pinned to the runtime tuples by test so they cannot drift.
NodeType = Literal["entity", "preference", "procedure", "summary", "episode"]
TurnRole = Literal["user", "agent", "tool"]
ForgetMode = Literal["hard", "soft", "decay"]
ConsolidateMode = Literal["full", "dry-run"]

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def utc_now_iso() -> str:
    """Current UTC time as an ISO8601 string with a ``Z`` suffix."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id() -> str:
    """Generate a UUID4 node identifier."""
    return str(uuid.uuid4())


def _check_iso(value: str, field_name: str) -> None:
    if not _ISO.match(value):
        raise ValueError(f"{field_name} must be an ISO8601 UTC string like 2026-09-15T10:00:00Z")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid date: {value}") from exc


def _norm_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    for tag in tags:
        cleaned = tag.strip().lower().replace(" ", "-")
        if not cleaned:
            raise ValueError("tags must be non-empty")
        normalized.append(cleaned)
    if len(set(normalized)) != len(normalized):
        raise ValueError("tags must be unique")
    return normalized


def _norm_slugs(slugs: list[str], field_name: str) -> list[str]:
    normalized = [slug.strip().lower() for slug in slugs]
    if any(not slug for slug in normalized):
        raise ValueError(f"{field_name} must contain non-empty slugs")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must be unique")
    return normalized


@dataclass(slots=True)
class TurnStreamEntry:
    """One conversation turn in a transcript (spec §4.1).

    An empty ``ts`` means the timestamp is unknown; it is omitted from the
    stored JSONL rather than fabricated.
    """

    role: str
    content: str
    turn: int
    ts: str = ""
    tool_name: str | None = None
    result: str | None = None
    query: str | None = None

    def __post_init__(self) -> None:
        if self.role not in TURN_ROLES:
            raise ValueError(f"role must be one of {TURN_ROLES}, got {self.role!r}")
        if self.turn < 1:
            raise ValueError("turn must be a 1-based integer")
        if self.ts:
            _check_iso(self.ts, "ts")
        if self.role != "tool" and (self.tool_name is not None or self.result is not None):
            raise ValueError("tool_name/result are only allowed when role='tool'")

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TurnStreamEntry:
        """Build a turn from untrusted JSON, validating required fields."""
        try:
            role = data["role"]
            content = data["content"]
            turn = data["turn"]
        except KeyError as exc:
            raise ValueError(f"turn entry missing required field: {exc.args[0]}") from exc
        if not isinstance(role, str) or not isinstance(content, str) or not isinstance(turn, int):
            raise ValueError("turn entry fields role/content must be str and turn must be int")
        optional: dict[str, str] = {}
        for key in ("ts", "tool_name", "result", "query"):
            value = data.get(key)
            if value is not None:
                if not isinstance(value, str):
                    raise ValueError(f"turn field {key} must be a string")
                optional[key] = value
        return cls(role=role, content=content, turn=turn, **optional)


@dataclass(slots=True)
class WriteInput:
    """Input contract for the write operation (spec §4.2)."""

    type: str
    title: str
    body: str
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5
    links: list[str] = field(default_factory=list)
    session_id: str | None = None
    transcript_ref: str | None = None
    expires_at: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None

    def __post_init__(self) -> None:
        if self.type not in NODE_TYPES:
            raise ValueError(f"type must be one of {NODE_TYPES}, got {self.type!r}")
        if not self.title.strip():
            raise ValueError("title must be non-empty")
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError("importance must be within [0.0, 1.0]")
        self.tags = _norm_tags(self.tags)
        self.links = _norm_slugs(self.links, "links")
        if self.type == "episode" and not (self.session_id or "").strip():
            raise ValueError("session_id is required for episode nodes")
        if self.session_id is not None and not self.session_id.strip():
            raise ValueError("session_id must be non-empty when provided")
        for name in ("expires_at", "valid_from", "valid_to"):
            value = getattr(self, name)
            if value is not None:
                _check_iso(value, name)
        if self.transcript_ref is not None and not self.transcript_ref.strip():
            raise ValueError("transcript_ref must be non-empty when provided")


@dataclass(slots=True)
class WikiNode:
    """Full representation of a wiki page, front matter plus body."""

    type: str
    title: str
    body: str
    id: str
    slug: str = ""
    file_path: str | None = None
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5
    created: str = field(default_factory=utc_now_iso)
    updated: str = field(default_factory=utc_now_iso)
    access_count: int = 0
    last_access: str | None = None
    expires_at: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    transcript_ref: str | None = None
    session_id: str | None = None
    links: list[str] = field(default_factory=list)
    content_hash: str = ""

    def __post_init__(self) -> None:
        if self.type not in NODE_TYPES:
            raise ValueError(f"type must be one of {NODE_TYPES}, got {self.type!r}")
        if not self.title.strip():
            raise ValueError("title must be non-empty")
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError("importance must be within [0.0, 1.0]")


@dataclass(slots=True)
class RecallHit:
    """One ranked search result (spec §5.1)."""

    slug: str
    file_path: str
    title: str
    node_type: str
    importance: float
    score: float
    rank: int
    snippet: str
    snippet_source: str
    tags: list[str]
    created: str
    updated: str
    last_access: str | None
    transcript_ref: str | None
    links: list[str]


@dataclass(slots=True)
class RecallResult:
    """Recall output: query, ranked hits, and search metadata."""

    query: str
    hits: list[RecallHit]
    total_indexed: int
    search_engine: str
    search_time_ms: float


@dataclass(slots=True)
class ForgetResult:
    """Output of the forget operation (spec §9.4)."""

    slug: str
    forgotten: bool
    mode: str
    file_path: str | None


@dataclass(slots=True)
class ConsolidateInput:
    """Trigger for LLM consolidation (spec §4.3)."""

    mode: str = "full"
    episode_ids: list[str] | None = None
    max_episodes: int = 10
    include_links: bool = True

    def __post_init__(self) -> None:
        if self.mode not in ("full", "dry-run"):
            raise ValueError("mode must be 'full' or 'dry-run'")
        if self.max_episodes < 1:
            raise ValueError("max_episodes must be >= 1")


@dataclass(slots=True)
class ConsolidationReport:
    """Output of consolidation (spec §5.2)."""

    mode: str
    episodes_processed: int
    nodes_created: list[WriteInput]
    nodes_updated: list[str]
    links_added: int
    llm_calls: int
    llm_prompt_tokens: int
    llm_completion_tokens: int
    dry_run: bool


@dataclass(slots=True)
class IngestTranscriptInput:
    """Transcript ingest contract (spec §4.4)."""

    session_id: str
    turns: list[TurnStreamEntry]
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", self.session_id):
            raise ValueError("session_id must be alphanumeric with '.', '_', '-' only")


@dataclass(slots=True)
class TranscriptLinkReport:
    """Transcript ingest output (spec §5.3)."""

    session_id: str
    transcript_file: str
    meta_file: str
    episode_node: str
    episode_file_path: str
    turn_count: int
    user_turns: int
    agent_turns: int
    tool_turns: int


@dataclass(slots=True)
class ProvenanceReport:
    """Trace from a wiki page back to originating transcripts (spec §7 Utility 7)."""

    slug: str
    direct_transcript_ref: str | None
    linked_episodes: list[str]
    transcript_files: list[str]
    meta_files: list[str]
    confidence: str


@dataclass(slots=True)
class SessionSummary:
    """One stored session as listed by ``list_sessions`` (spec §12.5)."""

    session_id: str
    started_at: str | None
    ended_at: str | None
    turn_count: int
    episode_slug: str | None
    file_path: str


@dataclass(slots=True)
class RebuildIndexReport:
    """Output of the index rebuild operation (spec §9.6)."""

    nodes_indexed: int
    nodes_skipped: int
    nodes_errored: int
    duration_ms: float
    errors: list[str]


@dataclass(slots=True)
class BackupReport:
    """Output of the backup operation (spec §9.7)."""

    archive_path: str
    size_bytes: int
    file_counts: dict[str, int]
    duration_ms: float


@dataclass(slots=True)
class RestoreReport:
    """Output of the restore operation (spec §9.8)."""

    restored: bool
    file_counts: dict[str, int]
    index_rebuilt: bool
    warnings: list[str]
    previous_backup_dir: str | None
