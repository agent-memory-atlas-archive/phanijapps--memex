import json
from pathlib import Path

import pytest

from memex.domain.models import IngestTranscriptInput, TurnStreamEntry, WikiNode
from memex.infrastructure.harness.transcript_hook import TranscriptHook
from memex.infrastructure.search.index_manager import IndexManager
from memex.infrastructure.search.link_manager import LinkManager
from memex.infrastructure.store.wiki_store import WikiStore


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
    hook.delete_transcript("sess-del", confirm=True)

    assert not list((data_dir / "transcripts").rglob("sess-del.jsonl"))
    assert not list((data_dir / "transcripts").rglob("sess-del.meta.json"))
    episode = hook.get_episode_by_session(report.episode_node)
    assert episode is not None
    assert episode.transcript_ref is not None
    assert episode.transcript_ref.startswith("retired:")


def test_clear_ignores_tampered_metadata_session_id_outside_transcript_tree(
    hook: TranscriptHook, data_dir: Path
) -> None:
    outside = data_dir / "sensitive.jsonl"
    outside.write_text("do not delete", encoding="utf-8")
    meta = data_dir / "transcripts" / "2026-09-15" / "safe.meta.json"
    meta.parent.mkdir(parents=True)
    meta.write_text(json.dumps({"session_id": "../sensitive"}), encoding="utf-8")

    assert hook.clear_transcripts(confirm=True) == 1
    assert outside.read_text(encoding="utf-8") == "do not delete"


def test_transcript_paths_reject_path_like_session_ids(hook: TranscriptHook) -> None:
    with pytest.raises(ValueError, match="session_id"):
        hook.get_transcript_path("../outside")


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


def test_list_sessions_reports_token_usage(hook: TranscriptHook) -> None:
    usage = {"input_tokens": 12, "output_tokens": 34, "cache_read_input_tokens": 56}
    hook.ingest(
        IngestTranscriptInput(
            session_id="sess-tokens",
            turns=[TurnStreamEntry(role="user", content="hi", turn=1)],
            token_usage=usage,
        )
    )
    summary = hook.list_sessions()[0]
    assert summary.token_usage == usage


def test_list_sessions_token_usage_absent_stays_none(hook: TranscriptHook) -> None:
    hook.ingest(_input("sess-no-tokens"))
    assert hook.list_sessions()[0].token_usage is None
