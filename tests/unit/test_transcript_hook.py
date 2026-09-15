from pathlib import Path

import pytest

from memex.domain.models import IngestTranscriptInput, TurnStreamEntry, WikiNode
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.link_manager import LinkManager
from memex.infrastructure.transcript_hook import TranscriptHook
from memex.infrastructure.wiki_store import WikiStore


def _input(session_id: str, turns: int = 2) -> IngestTranscriptInput:
    return IngestTranscriptInput(
        session_id=session_id,
        turns=[
            TurnStreamEntry(
                role="user", content=f"turn {i}", turn=i + 1, ts=f"2026-09-15T10:00:0{i}Z"
            )
            for i in range(turns)
        ],
    )


@pytest.fixture
def hook(data_dir: Path) -> TranscriptHook:
    store = WikiStore(data_dir)
    index = IndexManager(data_dir / "mem.db")
    links = LinkManager(index.connection, store.wiki_dir)
    return TranscriptHook(data_dir, store, index, links)


def test_duplicate_ingest_requires_overwrite(hook: TranscriptHook) -> None:
    hook.ingest(_input("sess-x"))
    with pytest.raises(FileExistsError, match="sess-x"):
        hook.ingest(_input("sess-x"))
    hook.ingest(_input("sess-x"), overwrite=True)


def test_invalid_session_id_rejected() -> None:
    with pytest.raises(ValueError, match="session_id"):
        _input("../escape")
    with pytest.raises(ValueError, match="session_id"):
        _input("")


def test_delete_transcript_removes_everything(hook: TranscriptHook, data_dir: Path) -> None:
    report = hook.ingest(_input("sess-del"))
    hook.delete_transcript("sess-del")

    assert not (data_dir / "transcripts/sess-del.jsonl").exists()
    assert not (data_dir / "transcripts/sess-del.meta.json").exists()
    assert not (data_dir / "wiki/episodes/sess-del.md").exists()
    assert hook.get_provenance(report.episode_node) is None


def test_provenance_missing_node_returns_none(hook: TranscriptHook) -> None:
    assert hook.get_provenance("ghost") is None


def test_provenance_none_confidence(hook: TranscriptHook) -> None:
    store = WikiStore(hook.data_dir)
    index = IndexManager(hook.data_dir / "mem.db")
    node = store.write(
        WikiNode(type="entity", title="Lonely", body="no links no transcript", id="")
    )
    index.update_record(node)
    provenance = hook.get_provenance(node.slug)
    assert provenance is not None
    assert provenance.confidence == "none"


def test_empty_turns_session(hook: TranscriptHook) -> None:
    empty = IngestTranscriptInput(session_id="sess-empty", turns=[])
    report = hook.ingest(empty)
    assert report.turn_count == 0
    summary = hook.list_sessions()[0]
    assert summary.started_at is None
    assert summary.ended_at is None
