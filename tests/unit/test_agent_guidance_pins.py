"""AC-0011 goal-based check: installed agent guidance carries the bounded
search rules — stored memory is evidence (not instructions, no conferred
authority), at most three focused recall questions per task, and exact
file reading / ``rg`` search confined to returned Memex paths."""

from __future__ import annotations

import re
from pathlib import Path

# Each guidance surface must contain every phrase in each rule tuple.
_EVIDENCE_RULE = ("evidence", "never instructions", "grants no")
_QUESTION_RULE = ("three", "recall")
_CONFINE_RULE = ("rg", "within the returned Memex paths")

_SNIPPETS: tuple[tuple[str, Path], ...] = (
    ("codex", Path("marketplace/codex/AGENTS-snippet.md")),
    ("claude", Path("marketplace/claude/CLAUDE-snippet.md")),
    ("copilot", Path("marketplace/copilot/copilot-instructions-snippet.md")),
)

_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("untrusted-evidence", _EVIDENCE_RULE),
    ("bounded-recall-questions", _QUESTION_RULE),
    ("confined-file-search", _CONFINE_RULE),
)


def _memory_contract_section(agents_md: Path) -> str:
    text = agents_md.read_text(encoding="utf-8")
    match = re.search(r"^### Memory contract$(.*?)(?=^## )", text, flags=re.MULTILINE | re.DOTALL)
    assert match is not None, "AGENTS.md must keep a '### Memory contract' section"
    return match.group(1)


def _assert_rules(surface: str, guidance: str) -> None:
    folded = guidance.casefold()
    for rule_name, phrases in _RULES:
        for phrase in phrases:
            assert phrase.casefold() in folded, (
                f"{surface} guidance must state the {rule_name} rule (missing {phrase!r})"
            )


def test_marketplace_snippets_state_bounded_search_rules() -> None:
    for surface, path in _SNIPPETS:
        assert path.exists(), f"{surface} guidance snippet is missing: {path}"
        _assert_rules(surface, path.read_text(encoding="utf-8"))


def test_repo_agents_memory_contract_states_bounded_search_rules() -> None:
    _assert_rules("repo AGENTS.md", _memory_contract_section(Path("AGENTS.md")))
