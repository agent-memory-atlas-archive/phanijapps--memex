from memex.domain.models import TurnStreamEntry
from memex.infrastructure.extractor import NodeExtractor


def turn(role: str, content: str, **extra: object) -> TurnStreamEntry:
    fields: dict[str, object] = {
        "role": role,
        "content": content,
        "turn": 1,
        "ts": "2026-09-15T10:00:00Z",
    }
    fields.update(extra)
    return TurnStreamEntry(**fields)  # type: ignore[arg-type]


def test_preference_cue() -> None:
    nodes = NodeExtractor().extract_from_turn(turn("user", "I prefer using ruff for linting"))
    assert len(nodes) == 1
    assert nodes[0].type == "preference"
    assert nodes[0].title.startswith("User preference:")


def test_fact_cue() -> None:
    nodes = NodeExtractor().extract_from_turn(
        turn("agent", "Remember that the deploy uses blue-green")
    )
    assert len(nodes) == 1
    assert nodes[0].type == "entity"


def test_rule_cue() -> None:
    nodes = NodeExtractor().extract_from_turn(turn("user", "Never do force pushes to main"))
    assert len(nodes) == 1
    assert nodes[0].type == "procedure"


def test_preference_wins_over_rule() -> None:
    nodes = NodeExtractor().extract_from_turn(turn("user", "I always use pytest, always use it"))
    assert len(nodes) == 1
    assert nodes[0].type == "preference"


def test_tool_turn_extracts_result() -> None:
    nodes = NodeExtractor().extract_from_turn(
        turn("tool", "output", tool_name="shell", result="exit 0, 3 files changed")
    )
    assert len(nodes) == 1
    assert nodes[0].title == "Tool result: shell"
    assert "3 files changed" in nodes[0].body


def test_tool_turn_without_result_skipped() -> None:
    nodes = NodeExtractor().extract_from_turn(turn("tool", "x", tool_name="shell"))
    assert nodes == []


def test_plain_turn_no_extraction() -> None:
    assert NodeExtractor().extract_from_turn(turn("user", "hello there")) == []


def test_extract_over_list() -> None:
    turns = [
        turn("user", "I prefer dark mode", turn=1),
        turn("agent", "ok noted", turn=2),
    ]
    nodes = NodeExtractor().extract(turns)
    assert len(nodes) == 1
