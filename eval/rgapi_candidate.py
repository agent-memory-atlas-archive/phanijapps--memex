"""Optional rgapi-backed candidate search for offline retrieval evaluation."""

from __future__ import annotations

import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval.candidates import RankedCandidate

RGAPI_VERSION = "0.1.22"
QUERY_TOKEN_RE = re.compile(r"[a-z0-9]+")
MAX_PATTERN_BYTES = 1024
SEARCH_TIMEOUT_MS = 100
MAX_RESULTS = 10_000

_SANITIZED_STOP_REASONS = {
    "dependency_unavailable",
    "invalid_query",
    "path_rejected",
    "incomplete_search",
    "measurement_failed",
}


@dataclass(frozen=True, slots=True)
class RgapiCandidateResult:
    ranked: tuple[RankedCandidate, ...]
    complete: bool
    stop_reason: str | None = None

    @property
    def actual_slugs(self) -> list[str]:
        return [candidate.slug for candidate in self.ranked]

    def ranker_metadata(self) -> dict[str, object]:
        return {
            "name": "rgapi-0.1.22",
            "complete": self.complete,
            "stop_reason": self.stop_reason,
            "timeout_ms": SEARCH_TIMEOUT_MS,
            "max_results": MAX_RESULTS,
            "pattern_byte_limit": MAX_PATTERN_BYTES,
        }


def rank_rgapi_candidate(query: str, docs_dir: Path, *, top_k: int) -> RgapiCandidateResult:
    """Return deterministic Markdown slugs from the optional in-process rgapi binding."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    try:
        import rgapi  # type: ignore[import-not-found]
    except ImportError:
        return _incomplete("dependency_unavailable")

    pattern = safe_rgapi_pattern(query)
    docs_root = _resolved_docs_root(docs_dir)
    if docs_root is None:
        return _incomplete("path_rejected")

    try:
        rows = rgapi.rg(
            pattern,
            root=docs_root,
            paths=True,
            include="*.md",
            follow_links=False,
            same_file_system=True,
            max_results=MAX_RESULTS,
            timeout_ms=SEARCH_TIMEOUT_MS,
            case_sensitive=False,
        )
    except Exception:
        return _incomplete("measurement_failed")

    complete, stop_reason = _completion_state(rows)
    validated = _validated_markdown_paths(rows, docs_root)
    if validated is None:
        return _incomplete("path_rejected")
    if not complete:
        return RgapiCandidateResult((), complete=False, stop_reason=stop_reason)

    slugs = sorted({path.stem for path in validated})
    ranked = tuple(
        RankedCandidate(slug=slug, rank=rank) for rank, slug in enumerate(slugs[:top_k], start=1)
    )
    return RgapiCandidateResult(ranked=ranked, complete=True)


def safe_rgapi_pattern(query: str) -> str:
    """Build a bounded literal regex from the same token language as FTS5 recall."""
    tokens = QUERY_TOKEN_RE.findall(query.lower())
    if not tokens:
        raise ValueError("query contains no searchable terms")
    parts: list[str] = []
    for token in tokens:
        parts.append(re.escape(token))
        pattern = "|".join(parts)
        if len(pattern.encode("utf-8")) > MAX_PATTERN_BYTES:
            raise ValueError("query pattern exceeds 1024 bytes")
    return "|".join(parts)


def _completion_state(rows: Any) -> tuple[bool, str | None]:
    stop_reason = getattr(rows, "stop_reason", None)
    complete = bool(getattr(rows, "complete", stop_reason is None))
    if complete and stop_reason is None:
        return True, None
    return False, _sanitize_stop_reason(stop_reason)


def _validated_markdown_paths(rows: Any, docs_root: Path) -> tuple[Path, ...] | None:
    paths: list[Path] = []
    for row in rows:
        rel = Path(str(row))
        if rel.is_absolute() or ".." in rel.parts or rel.suffix != ".md":
            return None
        candidate = docs_root / rel
        try:
            resolved = candidate.resolve(strict=True)
            metadata = candidate.lstat()
        except (OSError, RuntimeError):
            return None
        if (
            candidate.is_symlink()
            or _is_junction(candidate)
            or not resolved.is_relative_to(docs_root)
            or not stat.S_ISREG(metadata.st_mode)
        ):
            return None
        paths.append(resolved)
    return tuple(paths)


def _resolved_docs_root(docs_dir: Path) -> Path | None:
    try:
        docs_root = docs_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not docs_root.is_dir():
        return None
    if _is_junction(docs_root):
        return None
    return docs_root


def _is_junction(path: Path) -> bool:
    return path.is_junction()


def _sanitize_stop_reason(reason: object) -> str:
    if reason in {"timeout", "max_results"}:
        return "incomplete_search"
    if isinstance(reason, str) and reason in _SANITIZED_STOP_REASONS:
        return reason
    return "incomplete_search"


def _incomplete(stop_reason: str) -> RgapiCandidateResult:
    return RgapiCandidateResult((), complete=False, stop_reason=stop_reason)
