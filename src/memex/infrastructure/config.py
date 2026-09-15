"""memex.toml loading with defaults and environment overrides (spec §10)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from memex.domain.errors import ConfigError

PROVIDERS: tuple[str, ...] = ("openai", "ollama", "lmstudio", "openrouter", "custom")
PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}
LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR")
SLUG_ALGOS: tuple[str, ...] = ("kebab", "sha1")


@dataclass(frozen=True, slots=True)
class LLMConfig:
    provider: str = "openai"
    model: str = "gpt-4o"
    api_base: str | None = None
    api_key: str | None = None
    timeout: int = 60
    max_tokens: int = 4096

    @property
    def base_url(self) -> str:
        """Effective API base: explicit override or the provider default."""
        if self.api_base:
            return self.api_base
        if self.provider == "custom":
            raise ConfigError("llm.api_base is required when provider is 'custom'")
        return PROVIDER_BASE_URLS[self.provider]


@dataclass(frozen=True, slots=True)
class ConsolidationConfig:
    """Optional overrides for the consolidate operation.

    Lets episode distillation run on a cheaper (low-effort) model than
    the main ``[llm]`` block. Every field falls back to ``[llm]`` when
    unset.
    """

    provider: str | None = None
    model: str | None = None
    api_base: str | None = None
    api_key: str | None = None


@dataclass(frozen=True, slots=True)
class BM25Config:
    # k1/b are parsed for forward compatibility; SQLite FTS5 bm25() uses
    # compile-time defaults and cannot be tuned from SQL.
    k1: float = 1.5
    b: float = 0.75
    default_top_k: int = 10


@dataclass(frozen=True, slots=True)
class RecencyDecayConfig:
    enabled: bool = True
    half_life_days: int = 30


@dataclass(frozen=True, slots=True)
class IndexConfig:
    watch_poll_interval: int = 60
    auto_rebuild_on_startup: bool = False


@dataclass(frozen=True, slots=True)
class WikiConfig:
    default_importance: float = 0.5
    max_body_chars: int = 50000
    slug_algo: str = "kebab"


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    level: str = "INFO"
    file: Path | None = None


@dataclass(frozen=True, slots=True)
class MemexConfig:
    app_name: str = "memex"
    data_dir: Path = Path.home() / ".memex"
    llm: LLMConfig = LLMConfig()
    consolidation: ConsolidationConfig = ConsolidationConfig()
    bm25: BM25Config = BM25Config()
    recency_decay: RecencyDecayConfig = RecencyDecayConfig()
    index: IndexConfig = IndexConfig()
    wiki: WikiConfig = WikiConfig()
    logging: LoggingConfig = LoggingConfig()

    def consolidation_llm(self) -> LLMConfig:
        """Effective LLM settings for consolidation: overrides over [llm]."""
        override = self.consolidation
        base = self.llm
        return LLMConfig(
            provider=override.provider or base.provider,
            model=override.model or base.model,
            api_base=override.api_base or base.api_base,
            api_key=override.api_key or base.api_key,
            timeout=base.timeout,
            max_tokens=base.max_tokens,
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mem.db"

    @property
    def wiki_dir(self) -> Path:
        return self.data_dir / "wiki"

    @property
    def transcripts_dir(self) -> Path:
        return self.data_dir / "transcripts"


def _table(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a TOML table")
    return value


def _get[T](table: dict[str, object], key: str, expected: type[T], section: str) -> T | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, expected):
        raise ConfigError(f"[{section}].{key} must be {expected.__name__}")
    return value


def _or[T](value: T | None, default: T) -> T:
    return default if value is None else value


class ConfigLoader:
    """Loads memex.toml, applies env overrides, and validates the result."""

    def load(self, config_path: Path | None = None) -> MemexConfig:
        data_dir = Path(os.environ.get("MEMEX_DATA_DIR", str(Path.home() / ".memex"))).expanduser()
        path = config_path or data_dir / "memex.toml"
        raw: dict[str, object] = {}
        if path.exists():
            try:
                with path.open("rb") as handle:
                    raw = tomllib.load(handle)
            except tomllib.TOMLDecodeError as exc:
                raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

        data_dir = self._data_dir(raw, data_dir)
        llm = self._llm(raw, data_dir)
        return MemexConfig(
            app_name=str(_get(_table(raw, "app"), "name", str, "app") or "memex"),
            data_dir=data_dir,
            llm=llm,
            consolidation=self._consolidation(raw),
            bm25=BM25Config(
                k1=float(_or(_get(_table(raw, "bm25"), "k1", float, "bm25"), 1.5)),
                b=float(_or(_get(_table(raw, "bm25"), "b", float, "bm25"), 0.75)),
                default_top_k=int(_or(_get(_table(raw, "bm25"), "default_top_k", int, "bm25"), 10)),
            ),
            recency_decay=RecencyDecayConfig(
                enabled=bool(
                    _or(_get(_table(raw, "recency_decay"), "enabled", bool, "recency_decay"), True)
                ),
                half_life_days=int(
                    _or(
                        _get(_table(raw, "recency_decay"), "half_life_days", int, "recency_decay"),
                        30,
                    )
                ),
            ),
            index=IndexConfig(
                watch_poll_interval=int(
                    _or(_get(_table(raw, "index"), "watch_poll_interval", int, "index"), 60)
                ),
                auto_rebuild_on_startup=bool(
                    _or(_get(_table(raw, "index"), "auto_rebuild_on_startup", bool, "index"), False)
                ),
            ),
            wiki=WikiConfig(
                default_importance=float(
                    _or(_get(_table(raw, "wiki"), "default_importance", float, "wiki"), 0.5)
                ),
                max_body_chars=int(
                    _or(_get(_table(raw, "wiki"), "max_body_chars", int, "wiki"), 50000)
                ),
                slug_algo=str(_or(_get(_table(raw, "wiki"), "slug_algo", str, "wiki"), "kebab")),
            ),
            logging=self._logging(raw, data_dir),
        )

    def _data_dir(self, raw: dict[str, object], default: Path) -> Path:
        override = _get(_table(raw, "data_dir"), "path", str, "data_dir")
        return Path(str(override)).expanduser() if override else default

    def _llm(self, raw: dict[str, object], data_dir: Path) -> LLMConfig:
        table = _table(raw, "llm")
        provider = str(
            os.environ.get(
                "MEMEX_LLM_PROVIDER", str(_get(table, "provider", str, "llm") or "openai")
            )
        )
        if provider not in PROVIDERS:
            raise ConfigError(f"llm.provider must be one of {PROVIDERS}, got {provider!r}")
        model = str(
            os.environ.get("MEMEX_LLM_MODEL", str(_get(table, "model", str, "llm") or "gpt-4o"))
        )
        api_key = os.environ.get("MEMEX_API_KEY") or _get(table, "api_key", str, "llm")
        if provider == "custom" and _get(table, "api_base", str, "llm") is None:
            raise ConfigError("llm.api_base is required when provider is 'custom'")
        return LLMConfig(
            provider=provider,
            model=model,
            api_base=str(_or(_get(table, "api_base", str, "llm"), "") or ""),
            api_key=str(api_key) if api_key else None,
            timeout=int(_or(_get(table, "timeout", int, "llm"), 60)),
            max_tokens=int(_or(_get(table, "max_tokens", int, "llm"), 4096)),
        )

    def _consolidation(self, raw: dict[str, object]) -> ConsolidationConfig:
        table = _table(raw, "consolidation")
        provider_env = os.environ.get("MEMEX_CONSOLIDATE_PROVIDER")
        model_env = os.environ.get("MEMEX_CONSOLIDATE_MODEL")
        key_env = os.environ.get("MEMEX_CONSOLIDATE_API_KEY")
        provider = provider_env or _get(table, "provider", str, "consolidation")
        model = model_env or _get(table, "model", str, "consolidation")
        api_key = key_env or _get(table, "api_key", str, "consolidation")
        if provider is not None and provider not in PROVIDERS:
            raise ConfigError(
                f"consolidation.provider must be one of {PROVIDERS}, got {provider!r}"
            )
        return ConsolidationConfig(
            provider=str(provider) if provider else None,
            model=str(model) if model else None,
            api_base=str(_get(table, "api_base", str, "consolidation") or "") or None,
            api_key=str(api_key) if api_key else None,
        )

    def _logging(self, raw: dict[str, object], data_dir: Path) -> LoggingConfig:
        table = _table(raw, "logging")
        level = str(
            os.environ.get("MEMEX_LOG_LEVEL", str(_get(table, "level", str, "logging") or "INFO"))
        ).upper()
        if level not in LOG_LEVELS:
            raise ConfigError(f"logging.level must be one of {LOG_LEVELS}, got {level!r}")
        file_value = _get(table, "file", str, "logging")
        file_path = (
            Path(str(file_value)).expanduser() if file_value else data_dir / "logs/memex.log"
        )
        return LoggingConfig(level=level, file=file_path)
