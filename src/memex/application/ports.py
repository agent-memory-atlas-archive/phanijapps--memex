"""Application ports: protocols the infrastructure implements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Completion text plus token usage for report accounting."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient(Protocol):
    """Minimal chat-completion contract used by the consolidator."""

    def complete(self, system: str, user: str, *, max_tokens: int) -> LLMResponse: ...
