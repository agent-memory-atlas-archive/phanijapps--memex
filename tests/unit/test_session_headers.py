"""Session headers: extraction, transcript format, reader compatibility."""

import json
from pathlib import Path

import pytest

from memex import Memex
from memex.domain.models import IngestTranscriptInput, TranscriptLinkReport, TurnStreamEntry
from memex.infrastructure.config import MemexConfig as Config
from memex.infrastructure.harness_transcripts import (
    parse_codex_rollout,
    parse_transcript,
    read_transcript_turns,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
RICH = FIXTURES / "codex_rollout_rich.jsonl"


class TestCodexHeaderExtraction:
    def test_header_fields(self) -> None:
        header = parse_codex_rollout(RICH).header
        assert header is not None
        assert header.harness == "codex"
        assert header.session_id == "01a0a73c-73e6-7ed1-90c6-4bf6ccd47614"
        assert header.started_at == "2026-09-15T22:42:32Z"
        assert header.ended_at == "2026-09-15T23:10:05Z"
        assert header.duration_s == pytest.approx(1652.954, rel=0.01)

        meta = header.meta
        assert meta["cli_version"] == "0.154.0"
        assert meta["provider"] == "openai"
        assert meta["cwd"] == "/home/user/projects/agentzero"
        assert meta["models"] == ["gpt-5.6-sol"]
        assert meta["reasoning_efforts"] == ["medium", "high"]
        assert meta["resumed"] is True
        git = meta["git"]
        assert isinstance(git, dict)
        assert git["branch"] == "fix/planner-ward-autospawn"
        assert git["commit_hash"] == "abc999"  # latest meta wins after resume

    def test_thread_totals_are_latest_not_summed(self) -> None:
        header = parse_codex_rollout(RICH).header
        assert header is not None
        usage = header.meta["token_usage"]
        assert isinstance(usage, dict)
        # Latest thread_token_usage (71759 in), never the sum of records.
        assert usage["input_tokens"] == 71759
        assert usage["total_tokens"] == 72103

    def test_per_turn_usage_attached_to_agent_turns(self) -> None:
        turns = parse_codex_rollout(RICH).turns
        agents = [turn for turn in turns if turn.role == "agent"]
        assert agents[0].token_usage == {
            "input_tokens": 21759,
            "cached_input_tokens": 6784,
            "output_tokens": 244,
            "total_tokens": 22003,
        }
        assert agents[1].token_usage == {
            "input_tokens": 50000,
            "output_tokens": 100,
            "total_tokens": 50100,
        }
        assert all(turn.token_usage is None for turn in turns if turn.role != "agent")

    def test_turn_only_rollout_still_parses(self) -> None:
        parsed = parse_codex_rollout(FIXTURES / "codex_rollout.jsonl")
        assert parsed.turns  # older fixture: turn-only path kept working
        header = parsed.header
        assert header is not None  # synthesized from filename
        assert header.session_id


class TestTranscriptWriter:
    def _ingest(self, data_dir: Path, path: Path = RICH) -> tuple[Memex, TranscriptLinkReport]:
        memex = Memex(Config(data_dir=data_dir))
        parsed = parse_transcript("codex", path)
        report = memex.ingest_transcript(
            IngestTranscriptInput(
                session_id=parsed.header.session_id if parsed.header else "s",
                turns=parsed.turns,
                header=parsed.header,
            )
        )
        return memex, report

    def test_header_is_first_line_and_totals_current(self, data_dir: Path) -> None:
        _memex, report = self._ingest(data_dir)
        lines = (data_dir / f"transcripts/{report.session_id}.jsonl").read_text().splitlines()
        header = json.loads(lines[0])
        assert header["type"] == "memex_session_header"
        assert header["session_id"] == report.session_id
        assert header["meta"]["token_usage"]["input_tokens"] == 71759
        # turns follow, skipping the header
        assert all("role" in json.loads(line) for line in lines[1:])

    def test_recapture_refreshes_header_totals(self, data_dir: Path, tmp_path: Path) -> None:
        # Simulate a later notify: same rollout with one more usage record.
        memex, report = self._ingest(data_dir)
        grown = tmp_path / "grown.jsonl"
        grown.write_text(
            RICH.read_text()
            + json.dumps(
                {
                    "timestamp": "2026-09-15T23:11:00.000Z",
                    "type": "token_usage_record",
                    "payload": {
                        "turn_id": "t3",
                        "turn_token_usage": {"input_tokens": 900, "total_tokens": 950},
                        "thread_token_usage": {"input_tokens": 90000, "total_tokens": 90500},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        memex.ingest_transcript(
            IngestTranscriptInput(session_id=report.session_id, header=None, turns=[]),
            overwrite=True,
        )
        parsed = parse_transcript("codex", grown)
        memex.ingest_transcript(
            IngestTranscriptInput(
                session_id=report.session_id,
                turns=parsed.turns,
                header=parsed.header,
            ),
            overwrite=True,
        )
        lines = (data_dir / f"transcripts/{report.session_id}.jsonl").read_text().splitlines()
        assert json.loads(lines[0])["meta"]["token_usage"]["input_tokens"] == 90000
        episodes = list((data_dir / "docs/episodes").glob("*.md"))
        assert len(episodes) == 1  # idempotent, no duplicate episode


class TestReaders:
    def test_reader_skips_header(self, data_dir: Path) -> None:
        _memex, report = TestTranscriptWriter()._ingest(data_dir)
        turns = read_transcript_turns(data_dir / f"transcripts/{report.session_id}.jsonl")
        assert turns and all(isinstance(turn, TurnStreamEntry) for turn in turns)

    def test_old_turn_only_transcripts_readable(self, tmp_path: Path) -> None:
        legacy = tmp_path / "legacy.jsonl"
        legacy.write_text(
            json.dumps({"role": "user", "content": "old", "turn": 1, "ts": ""}) + "\n",
            encoding="utf-8",
        )
        turns = read_transcript_turns(legacy)
        assert len(turns) == 1 and turns[0].content == "old"

    def test_cli_load_turns_skips_header(
        self, tmp_path: Path, data_dir: Path, capture: dict[str, str]
    ) -> None:
        from memex import cli

        _memex, report = TestTranscriptWriter()._ingest(data_dir)
        source = data_dir / f"transcripts/{report.session_id}.jsonl"
        code = cli.main(
            [
                "--data-dir",
                str(tmp_path / "other"),
                "ingest-transcript",
                "--session-id",
                "roundtrip",
                "--turns-file",
                str(source),
            ]
        )
        assert code == 0
        payload = json.loads(capture["out"])
        assert payload["turn_count"] > 0
