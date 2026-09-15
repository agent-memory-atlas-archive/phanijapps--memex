"""Rule-based extraction from conversation turns (spec §7 Utility 6).

No LLM involved. One node per turn: the first matching category wins
(preference, then procedure, then fact) — predictable beats greedy here;
complex extraction belongs to the consolidator.
"""

from __future__ import annotations

import re

from memex.domain.models import NON_EPISODE_TYPES, TurnStreamEntry, WriteInput

_CUES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "preference",
        (r"i prefer", r"i like", r"my preference", r"i always use"),
        "User preference",
    ),
    (
        "procedure",
        (r"always use", r"never do", r"the rule is", r"don't use", r"do not use"),
        "Rule",
    ),
    (
        "entity",
        (r"remember that", r"remember to", r"you should know", r"important:"),
        "User fact",
    ),
)


class NodeExtractor:
    """Cue-phrase matcher producing WriteInputs from turns."""

    def __init__(self) -> None:
        self._compiled = [
            (node_type, [re.compile(pattern, re.IGNORECASE) for pattern in patterns], label)
            for node_type, patterns, label in _CUES
        ]

    def extract(self, turns: list[TurnStreamEntry]) -> list[WriteInput]:
        extracted: list[WriteInput] = []
        for turn in turns:
            extracted.extend(self.extract_from_turn(turn))
        return extracted

    def extract_from_turn(self, turn: TurnStreamEntry) -> list[WriteInput]:
        if turn.role == "tool":
            return self._from_tool_turn(turn)
        if turn.role not in ("user", "agent"):
            return []
        for node_type, patterns, label in self._compiled:
            for pattern in patterns:
                match = pattern.search(turn.content)
                if match:
                    tail = turn.content[match.start() :].strip().rstrip(".,;:")
                    return [
                        WriteInput(
                            type=node_type if node_type in NON_EPISODE_TYPES else "entity",
                            title=f"{label}: {tail[:80]}",
                            body=turn.content,
                            tags=["auto-extracted"],
                        )
                    ]
        return []

    @staticmethod
    def _from_tool_turn(turn: TurnStreamEntry) -> list[WriteInput]:
        if not turn.tool_name:
            return []
        result = (turn.result or "").strip()
        if not result:
            return []
        return [
            WriteInput(
                type="entity",
                title=f"Tool result: {turn.tool_name}",
                body=result,
                tags=["auto-extracted", "tool-result"],
            )
        ]
