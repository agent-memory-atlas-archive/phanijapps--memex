"""LLM clients (spec §7 Utility 5, updated).

One client covers every OpenAI-compatible endpoint — OpenAI, Ollama, LM
Studio, OpenRouter, or custom — via the official ``openai`` SDK pointed at
the configured ``api_base``. No hand-rolled HTTP.
"""

from __future__ import annotations

from memex.application.ports import LLMClient, LLMResponse
from memex.domain.errors import LLMError
from memex.infrastructure.config import MemexConfig

_PLACEHOLDER_KEY = "not-set"


class OpenAICompatClient:
    """Chat completions over any OpenAI-compatible API."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout: int = 60,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - exercised only in odd envs
            raise LLMError("the 'openai' package is required for LLM calls") from exc
        self._model = model
        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key or _PLACEHOLDER_KEY,
            timeout=timeout,
        )

    def complete(self, system: str, user: str, *, max_tokens: int) -> LLMResponse:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=0,
            )
        except Exception as exc:
            raise LLMError(f"LLM API call failed: {type(exc).__name__}") from exc
        choice = response.choices[0].message.content or ""
        usage = response.usage
        return LLMResponse(
            text=choice,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )


def client_from_config(config: MemexConfig) -> LLMClient:
    """Build the LLM client from the llm config section."""
    llm = config.llm
    return OpenAICompatClient(
        base_url=llm.base_url,
        api_key=llm.api_key,
        model=llm.model,
        timeout=llm.timeout,
    )
