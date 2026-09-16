"""LLM clients (spec §7 Utility 5, updated).

One client covers every OpenAI-compatible endpoint — OpenAI, Ollama, LM
Studio, OpenRouter, or custom — via the official ``openai`` SDK pointed at
the configured ``api_base``. No hand-rolled HTTP.
"""

from __future__ import annotations

import os
import subprocess

from memex.application.ports import LLMClient, LLMResponse
from memex.domain.errors import LLMError
from memex.infrastructure.config import LLMConfig

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


HARNESSES: dict[str, tuple[str, ...]] = {
    "claude": ("claude", "-p", "--output-format", "text"),
    "codex": ("codex", "exec", "--skip-git-repo-check"),
    "pi": ("pi", "-p"),
}
# Agent CLIs take longer than plain HTTP; give them room.
HARNESS_TIMEOUT_FLOOR = 180


class HarnessLLMClient:
    """LLM calls through a coding harness's CLI print mode.

    Consolidation rides the harness's own configured model, credentials,
    and billing — no separate API key. Output is the CLI's stdout; token
    usage is unknown and reported as zero.
    """

    def __init__(self, harness: str, *, model: str | None = None, timeout: int = 60) -> None:
        try:
            base = HARNESSES[harness]
        except KeyError:
            raise LLMError(f"unknown harness provider: {harness!r}") from None
        self._argv = [*base]
        if model:
            self._argv += ["--model", model]
        self._timeout = max(timeout, HARNESS_TIMEOUT_FLOOR)

    def complete(self, system: str, user: str, *, max_tokens: int) -> LLMResponse:
        prompt = f"{system}\n\n{user}"
        try:
            completed = subprocess.run(
                [*self._argv, prompt],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LLMError(f"harness LLM call failed: {type(exc).__name__}") from exc
        if completed.returncode != 0 or not completed.stdout.strip():
            detail = completed.stderr.strip().splitlines()[-1][:120] if completed.stderr else ""
            raise LLMError(f"harness LLM call failed: exit {completed.returncode} {detail}")
        return LLMResponse(text=completed.stdout.strip(), prompt_tokens=0, completion_tokens=0)


def client_from_config(llm: LLMConfig) -> LLMClient:
    """Build the LLM client from explicit LLM settings."""
    if llm.provider in HARNESSES:
        return HarnessLLMClient(llm.provider, model=llm.model, timeout=llm.timeout)
    return OpenAICompatClient(
        base_url=llm.base_url,
        api_key=llm.api_key,
        model=llm.model,
        timeout=llm.timeout,
    )
