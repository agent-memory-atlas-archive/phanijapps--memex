"""Transcript ingestion, episode linking, and provenance tracing (spec §12)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from memex.application.dto import to_jsonable
from memex.domain.models import (
    IngestTranscriptInput,
    ProvenanceReport,
    SessionSummary,
    TranscriptLinkReport,
    TurnStreamEntry,
    WikiNode,
)
from memex.domain.slugs import slugify
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.link_manager import LinkManager
from memex.infrastructure.wiki_store import WikiStore

_SUMMARY_EXCERPT_CHARS = 200
_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*$")


def episode_slug(session_id: str) -> str:
    return slugify(session_id)


class TranscriptHook:
    """Stores raw transcripts and links them to episode wiki nodes."""

    def __init__(
        self,
        data_dir: Path,
        wiki_store: WikiStore,
        index_mgr: IndexManager,
        link_mgr: LinkManager,
    ) -> None:
        self.data_dir = data_dir
        self.transcripts_dir = data_dir / "transcripts"
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self._store = wiki_store
        self._index = index_mgr
        self._links = link_mgr

    def ingest(
        self, input: IngestTranscriptInput, *, overwrite: bool = False
    ) -> TranscriptLinkReport:
        """Store a raw transcript and link it to an episode node.

        Turn contents are stored verbatim and never logged. Side effects:
        writes ``transcripts/{session_id}.jsonl`` and ``.meta.json``, creates
        ``wiki/episodes/{session_id}.md`` with ``transcript_ref`` front
        matter, and indexes the episode.

        Args:
            input: Session turns and optional metadata; ``session_id`` is
                restricted to ``[A-Za-z0-9._-]`` (it becomes a filename).
            overwrite: Replace an existing transcript for this session.

        Raises:
            FileExistsError: A transcript for ``session_id`` already exists
                and ``overwrite`` is False.
            ValueError: ``session_id`` or a turn entry is invalid.
        """
        captured_at = self._capture_date(input)
        jsonl_path = self.get_transcript_path(input.session_id, captured_at)
        meta_path = self._meta_path(input.session_id, captured_at)
        if jsonl_path.exists() and not overwrite:
            raise FileExistsError(f"transcript already exists: {jsonl_path.name}")

        with jsonl_path.open("w", encoding="utf-8") as handle:
            if input.header is not None:
                header = input.header
                header.session_id = input.session_id
                handle.write(json.dumps(to_jsonable(header)) + "\n")
            for turn in input.turns:
                handle.write(json.dumps(self._turn_to_json(turn)) + "\n")

        counts = self._count_roles(input.turns)
        harness = input.header.harness if input.header else None
        meta: dict[str, object] = {
            "session_id": input.session_id,
            "harness": harness,
            "started_at": input.turns[0].ts if input.turns else None,
            "ended_at": input.turns[-1].ts if input.turns else None,
            "turn_count": len(input.turns),
            "user_turns": counts["user"],
            "agent_turns": counts["agent"],
            "tool_turns": counts["tool"],
            "agent_version": f"memex/{_version()}",
            "metadata": input.metadata,
        }
        # Token counts live in this sidecar, never in the transcript JSONL.
        if input.token_usage:
            meta["token_usage"] = input.token_usage
        turn_usage = [
            {"turn": turn.turn, "usage": turn.token_usage}
            for turn in input.turns
            if turn.token_usage is not None
        ]
        if turn_usage:
            meta["turn_token_usage"] = turn_usage
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

        episode = self._write_episode(input)
        return TranscriptLinkReport(
            session_id=input.session_id,
            transcript_file=str(jsonl_path),
            meta_file=str(meta_path),
            episode_node=episode.slug,
            episode_file_path=str(episode.file_path or ""),
            turn_count=len(input.turns),
            user_turns=counts["user"],
            agent_turns=counts["agent"],
            tool_turns=counts["tool"],
        )

    def get_transcript_path(self, session_id: str, captured_at: str | None = None) -> Path:
        self._require_session_id(session_id)
        if captured_at is None:
            return self._find_transcript(session_id, ".jsonl")
        return self._date_dir(captured_at) / f"{session_id}.jsonl"

    def get_episode_path(self, session_id: str) -> Path:
        self._require_session_id(session_id)
        return self._store.get_path(episode_slug(session_id), "episode")

    def get_episode_by_session(self, session_id: str) -> WikiNode | None:
        return self._store.read(episode_slug(session_id))

    def get_provenance(self, slug: str) -> ProvenanceReport | None:
        """Trace a wiki page back to originating transcripts (§12.4).

        Confidence is ``direct`` when the node carries a ``transcript_ref``
        (episodes), ``inferred`` when an episode links to the node, and
        ``none`` when no transcript chain exists. Returns None when the
        slug itself does not exist.
        """
        node = self._store.read(slug)
        if node is None:
            return None
        if node.transcript_ref:
            session = Path(node.transcript_ref).stem
            return self._report(slug, [session], "direct")
        episode_slugs = self._episode_backlinks(slug)
        if episode_slugs:
            sessions = [s for s in (self._session_of(episode) for episode in episode_slugs) if s]
            return self._report(slug, sessions, "inferred")
        return self._report(slug, [], "none")

    def list_sessions(self) -> list[SessionSummary]:
        return self.list_sessions_report()[0]

    def list_sessions_report(self) -> tuple[list[SessionSummary], int]:
        """Return valid sessions and the count of unreadable metadata records."""
        sessions: list[SessionSummary] = []
        unreadable = 0
        root = self.transcripts_dir.resolve()
        for meta_path in sorted(self.transcripts_dir.rglob("*.meta.json")):
            try:
                if not meta_path.resolve().is_relative_to(root):
                    unreadable += 1
                    continue
                sessions.append(self._load_session_summary(meta_path))
            except (OSError, ValueError, TypeError, AttributeError, RuntimeError):
                unreadable += 1
                continue
        return sessions, unreadable

    def delete_transcript(self, session_id: str, *, confirm: bool = False) -> None:
        if not confirm:
            raise ValueError("transcript deletion requires confirm=True")
        self._require_session_id(session_id)
        jsonl = self._find_transcript(session_id, ".jsonl")
        meta = self._find_transcript(session_id, ".meta.json")
        self._unlink_confined(jsonl)
        self._unlink_confined(meta)
        slug = episode_slug(session_id)
        episode = self._store.read(slug)
        if episode is not None:
            episode.transcript_ref = f"retired:{episode.transcript_ref or session_id}"
            stored = self._store.write(episode)
            self._index.update_record(stored)

    def clear_transcripts(self, *, confirm: bool = False) -> int:
        """Delete raw transcripts while retaining episodes with retired references."""
        if not confirm:
            raise ValueError("transcript clearing requires confirm=True")
        cleared = 0
        for meta_path in self.transcripts_dir.rglob("*.meta.json"):
            session_id = meta_path.name.removesuffix(".meta.json")
            if not self.is_valid_session_id(session_id):
                continue
            transcript_path = meta_path.with_name(f"{session_id}.jsonl")
            self._unlink_confined(transcript_path)
            self._unlink_confined(meta_path)
            episode = self._store.read(episode_slug(session_id))
            if episode is not None:
                episode.transcript_ref = f"retired:{transcript_path.relative_to(self.data_dir)}"
                stored = self._store.write(episode)
                self._index.update_record(stored)
                self._links.sync_node(stored)
            cleared += 1
        return cleared

    def _write_episode(self, input: IngestTranscriptInput) -> WikiNode:
        slug = episode_slug(input.session_id)
        counts = self._count_roles(input.turns)
        harness = input.header.harness if input.header else None
        episode = WikiNode(
            type="episode",
            title=f"Session {input.session_id}",
            harness=harness,
            body=self._summary(input, counts),
            id="",
            slug=slug,
            session_id=input.session_id,
            transcript_ref=str(
                self.get_transcript_path(input.session_id, self._capture_date(input)).relative_to(
                    self.data_dir
                )
            ),
        )
        stored = self._store.write(episode)
        self._index.update_record(stored)
        self._links.sync_node(stored)
        return stored

    _SYSTEM_NOISE_PREFIXES = ("#", "<", "\u003crecommended", "<recommended", "<environment")

    def _summary(self, input: IngestTranscriptInput, counts: dict[str, int]) -> str:
        """Deterministic session body: real intent + last outcome + tools.

        Filters system noise (AGENTS.md, environment context, plugin lists)
        so the episode says what the session was about, not what the host
        injected before the first user turn.
        """
        intent = ""
        for turn in input.turns:
            if turn.role == "user" and not any(
                turn.content.startswith(prefix) for prefix in self._SYSTEM_NOISE_PREFIXES
            ):
                intent = turn.content[:_SUMMARY_EXCERPT_CHARS].strip()
                break

        outcome = ""
        for turn in reversed(input.turns):
            if turn.role == "agent" and turn.content.strip():
                outcome = turn.content[:_SUMMARY_EXCERPT_CHARS].strip()
                break

        tools = sorted({turn.tool_name for turn in input.turns if turn.tool_name})[:5]

        lines = [
            f"Session {input.session_id} with {len(input.turns)} turns "
            f"({counts['user']} user, {counts['agent']} agent, {counts['tool']} tool)."
        ]
        if intent:
            lines.append(f"\n**Intent:** {intent}")
        if outcome:
            lines.append(f"\n**Outcome:** {outcome}")
        if tools:
            lines.append(f"\n**Tools:** {', '.join(tools)}")
        return "\n".join(lines)

    def _episode_backlinks(self, slug: str) -> list[str]:
        rows = self._index.connection.execute(
            "SELECT w.slug FROM wiki_links l JOIN wiki_index w ON w.slug = l.source_slug"
            " WHERE l.target_slug = ? AND w.node_type = 'episode' ORDER BY w.slug",
            (slug,),
        ).fetchall()
        return [str(row["slug"]) for row in rows]

    def _session_of(self, episode_slug_value: str) -> str | None:
        node = self._store.read(episode_slug_value)
        if node is None or not node.session_id:
            return None
        return node.session_id

    def _report(self, slug: str, sessions: list[str], confidence: str) -> ProvenanceReport:
        transcript_files: list[str] = []
        meta_files: list[str] = []
        for session in sessions:
            transcript_path = self._find_transcript(session, ".jsonl")
            meta_path = self._find_transcript(session, ".meta.json")
            transcript_files.append(str(transcript_path))
            meta_files.append(str(meta_path))
        return ProvenanceReport(
            slug=slug,
            direct_transcript_ref=None,
            linked_episodes=[episode_slug(s) for s in sessions],
            transcript_files=transcript_files,
            meta_files=meta_files,
            confidence=confidence,
        )

    def _load_session_summary(self, meta_path: Path) -> SessionSummary:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("unreadable session metadata") from exc
        if not isinstance(meta, dict):
            raise ValueError("session metadata must be an object")
        session_id = str(meta.get("session_id", meta_path.name.removesuffix(".meta.json")))
        self._require_session_id(session_id)
        started_at = meta.get("started_at")
        ended_at = meta.get("ended_at")
        if started_at is not None and not isinstance(started_at, str):
            raise ValueError("invalid session start time")
        if ended_at is not None and not isinstance(ended_at, str):
            raise ValueError("invalid session end time")
        turn_count = int(meta.get("turn_count", 0))
        if turn_count < 0:
            raise ValueError("invalid session turn count")
        slug = episode_slug(session_id)
        return SessionSummary(
            session_id=session_id,
            started_at=started_at,
            ended_at=ended_at,
            turn_count=turn_count,
            episode_slug=slug if self._store.exists(slug) else None,
            file_path=str(meta_path.with_name(f"{session_id}.jsonl")),
        )

    def _meta_path(self, session_id: str, captured_at: str | None = None) -> Path:
        self._require_session_id(session_id)
        return self._date_dir(captured_at) / f"{session_id}.meta.json"

    def _capture_date(self, input: IngestTranscriptInput) -> str:
        value = (
            input.header.captured_at if input.header else (input.turns[0].ts if input.turns else "")
        )
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
        except ValueError:
            return datetime.now(UTC).strftime("%Y-%m-%d")

    def _date_dir(self, captured_at: str | None) -> Path:
        day = captured_at or datetime.now(UTC).strftime("%Y-%m-%d")
        directory = self.transcripts_dir / day
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _find_transcript(self, session_id: str, suffix: str) -> Path:
        self._require_session_id(session_id)
        matches = list(self.transcripts_dir.rglob(f"{session_id}{suffix}"))
        return matches[0] if matches else self.transcripts_dir / f"{session_id}{suffix}"

    @staticmethod
    def is_valid_session_id(session_id: str) -> bool:
        return bool(_SESSION_ID.fullmatch(session_id))

    def _require_session_id(self, session_id: str) -> None:
        if not self.is_valid_session_id(session_id):
            raise ValueError("session_id must be alphanumeric with '.', '_', '-' only")

    def _unlink_confined(self, path: Path) -> None:
        root = self.transcripts_dir.resolve()
        try:
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise ValueError("transcript path escapes the transcript directory") from exc
        path.unlink(missing_ok=True)

    @staticmethod
    def _count_roles(turns: list[TurnStreamEntry]) -> dict[str, int]:
        return {
            "user": sum(1 for turn in turns if turn.role == "user"),
            "agent": sum(1 for turn in turns if turn.role == "agent"),
            "tool": sum(1 for turn in turns if turn.role == "tool"),
        }

    @staticmethod
    def _turn_to_json(turn: TurnStreamEntry) -> dict[str, object]:
        data: dict[str, object] = {
            "role": turn.role,
            "content": turn.content,
            "turn": turn.turn,
        }
        if turn.ts:
            data["ts"] = turn.ts
        if turn.tool_name is not None:
            data["tool_name"] = turn.tool_name
        if turn.result is not None:
            data["result"] = turn.result
        if turn.query is not None:
            data["query"] = turn.query
        return data  # token_usage intentionally omitted: meta.json only


def _version() -> str:
    from memex import __version__

    return __version__
