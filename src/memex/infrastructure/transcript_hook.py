"""Transcript ingestion, episode linking, and provenance tracing (spec §12)."""

from __future__ import annotations

import json
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
        jsonl_path = self.get_transcript_path(input.session_id)
        meta_path = self._meta_path(input.session_id)
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
        meta = {
            "session_id": input.session_id,
            "started_at": input.turns[0].ts if input.turns else None,
            "ended_at": input.turns[-1].ts if input.turns else None,
            "turn_count": len(input.turns),
            "user_turns": counts["user"],
            "agent_turns": counts["agent"],
            "tool_turns": counts["tool"],
            "agent_version": f"memex/{_version()}",
            "metadata": input.metadata,
        }
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

    def get_transcript_path(self, session_id: str) -> Path:
        return self.transcripts_dir / f"{session_id}.jsonl"

    def get_episode_path(self, session_id: str) -> Path:
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
        sessions: list[SessionSummary] = []
        for meta_path in sorted(self.transcripts_dir.glob("*.meta.json")):
            sessions.append(self._load_session_summary(meta_path))
        return sessions

    def delete_transcript(self, session_id: str) -> None:
        jsonl = self.get_transcript_path(session_id)
        meta = self._meta_path(session_id)
        jsonl.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        slug = episode_slug(session_id)
        if self._store.exists(slug):
            self._store.delete(slug)
            self._index.remove_record(slug)
            self._links.remove_slug(slug)

    def _write_episode(self, input: IngestTranscriptInput) -> WikiNode:
        slug = episode_slug(input.session_id)
        counts = self._count_roles(input.turns)
        episode = WikiNode(
            type="episode",
            title=f"Session {input.session_id}",
            body=self._summary(input, counts),
            id="",
            slug=slug,
            session_id=input.session_id,
            transcript_ref=f"transcripts/{input.session_id}.jsonl",
        )
        stored = self._store.write(episode)
        self._index.update_record(stored)
        self._links.sync_node(stored)
        return stored

    def _summary(self, input: IngestTranscriptInput, counts: dict[str, int]) -> str:
        excerpt = ""
        for turn in input.turns:
            if turn.role == "user":
                excerpt = turn.content[:_SUMMARY_EXCERPT_CHARS]
                break
        parts = [
            f"Session {input.session_id} with {len(input.turns)} turns "
            f"({counts['user']} user, {counts['agent']} agent, {counts['tool']} tool)."
        ]
        if excerpt:
            parts.append(f'Opened with: "{excerpt}"')
        return " ".join(parts)

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
            transcript_files.append(str(self.get_transcript_path(session)))
            meta_files.append(str(self._meta_path(session)))
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
        except (OSError, json.JSONDecodeError):
            meta = {}
        session_id = str(meta.get("session_id", meta_path.name.removesuffix(".meta.json")))
        slug = episode_slug(session_id)
        return SessionSummary(
            session_id=session_id,
            started_at=meta.get("started_at"),
            ended_at=meta.get("ended_at"),
            turn_count=int(meta.get("turn_count", 0)),
            episode_slug=slug if self._store.exists(slug) else None,
            file_path=str(self.get_transcript_path(session_id)),
        )

    def _meta_path(self, session_id: str) -> Path:
        return self.transcripts_dir / f"{session_id}.meta.json"

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
        if turn.token_usage is not None:
            data["token_usage"] = turn.token_usage
        return data


def _version() -> str:
    from memex import __version__

    return __version__
