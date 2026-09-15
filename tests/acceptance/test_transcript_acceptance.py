"""Spec acceptance tests 16-18: transcript ingest, provenance, sessions."""

from __future__ import annotations

from pathlib import Path

import pytest

from memex.domain.models import IngestTranscriptInput, TurnStreamEntry, WikiNode
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.link_manager import LinkManager
from memex.infrastructure.transcript_hook import TranscriptHook
from memex.infrastructure.wiki_store import WikiStore


def turn(role: str, content: str, number: int, ts: str) -> TurnStreamEntry:
    return TurnStreamEntry(role=role, content=content, turn=number, ts=ts)


@pytest.fixture
def hook(data_dir: Path) -> tuple[TranscriptHook, WikiStore, IndexManager]:
    store = WikiStore(data_dir)
    index = IndexManager(data_dir / "mem.db")
    links = LinkManager(index.connection, store.wiki_dir)
    transcript_hook = TranscriptHook(data_dir, store, index, links)
    return transcript_hook, store, index


def session_input(session_id: str) -> IngestTranscriptInput:
    return IngestTranscriptInput(
        session_id=session_id,
        turns=[
            turn("user", "Remember that I prefer ruff over flake8.", 1, "2026-09-15T10:00:00Z"),
            turn(
                "agent", "Got it. I'll use ruff for all linting tasks.", 2, "2026-09-15T10:00:01Z"
            ),
            turn("tool", "✓ ruff installed", 3, "2026-09-15T10:00:02Z"),
        ],
        metadata={"task": "setup"},
    )


def test_transcript_ingest_and_link(hook: tuple[TranscriptHook, WikiStore, IndexManager]) -> None:
    transcript_hook, store, index = hook

    report = transcript_hook.ingest(session_input("sess-abc123"))

    jsonl = Path(report.transcript_file)
    meta = Path(report.meta_file)
    assert jsonl.exists() and meta.exists()
    assert jsonl.name == "sess-abc123.jsonl"
    assert jsonl.parent.name == "transcripts"

    episode = store.read(report.episode_node)
    assert episode is not None
    assert episode.type == "episode"
    assert episode.transcript_ref == "transcripts/sess-abc123.jsonl"
    assert episode.session_id == "sess-abc123"

    assert report.turn_count == 3
    assert report.user_turns == 1
    assert report.agent_turns == 1
    assert report.tool_turns == 1

    row = index.get(report.episode_node)
    assert row is not None
    assert row["node_type"] == "episode"


def test_transcript_provenance_trace(hook: tuple[TranscriptHook, WikiStore, IndexManager]) -> None:
    transcript_hook, store, index = hook

    report = transcript_hook.ingest(session_input("sess-prov"))
    fact = store.write(
        WikiNode(
            type="preference",
            title="User prefers ruff",
            body="The user prefers [[ruff-linter]] over flake8.",
            id="",
        )
    )
    index.update_record(fact)
    episode = store.read(report.episode_node)
    assert episode is not None
    episode.body += f"\n\nDiscussed: [[{fact.slug}]]"
    store.write(episode)
    index.update_record(episode)

    links = LinkManager(index.connection, store.wiki_dir)
    links.sync_node(episode)

    provenance = transcript_hook.get_provenance(fact.slug)
    assert provenance is not None
    assert provenance.confidence == "inferred"
    assert provenance.transcript_files == [str(transcript_hook.get_transcript_path("sess-prov"))]
    assert provenance.linked_episodes == [report.episode_node]

    direct = transcript_hook.get_provenance(report.episode_node)
    assert direct is not None
    assert direct.confidence == "direct"


def test_transcript_list_sessions(hook: tuple[TranscriptHook, WikiStore, IndexManager]) -> None:
    transcript_hook, _, _ = hook
    for sid in ("sess-one", "sess-two", "sess-three"):
        transcript_hook.ingest(session_input(sid))

    sessions = transcript_hook.list_sessions()
    assert [session.session_id for session in sessions] == [
        "sess-one",
        "sess-three",
        "sess-two",
    ]
    assert all(session.turn_count == 3 for session in sessions)
    assert all(session.episode_slug for session in sessions)
