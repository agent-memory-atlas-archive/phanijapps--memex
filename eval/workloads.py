"""Offline workload fixtures and query validation for retrieval evaluation."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from eval.corpus import CorpusResult, QuerySpec

GUTENBERG_SOURCE_URL = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv.gz"
GUTENBERG_MAX_COMPRESSED_BYTES = 16 * 1024 * 1024
GUTENBERG_MAX_EXPANDED_BYTES = 128 * 1024 * 1024
GUTENBERG_MAX_ROWS = 100_000
GUTENBERG_MAX_CELL_BYTES = 64 * 1024
GUTENBERG_ALLOWED_COLUMNS = frozenset(
    {
        "Text#",
        "Type",
        "Issued",
        "Title",
        "Language",
        "Authors",
        "Subjects",
        "LoCC",
        "Bookshelves",
    }
)
SALESFORCE_FIXTURE = Path(__file__).resolve().parent / "data" / "salesforce-facts.jsonl"
GUTENBERG_FIXTURE = Path(__file__).resolve().parent / "data" / "gutenberg-books.jsonl"

type ImportCategory = Literal[
    "path_rejected",
    "source_too_large",
    "source_unreproducible",
    "schema_invalid",
    "serialization_failed",
]


@dataclass(frozen=True, slots=True)
class GutenbergProvenance:
    canonical_source_url: str
    retrieved_at: str
    upstream_last_modified: str | None
    input_byte_size: int
    sha256: str

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "canonical_source_url": self.canonical_source_url,
            "retrieved_at": self.retrieved_at,
            "upstream_last_modified": self.upstream_last_modified,
            "input_byte_size": self.input_byte_size,
            "sha256": self.sha256,
        }


class GutenbergImportError(ValueError):
    """Bounded error category for local Gutenberg import failures."""

    def __init__(self, category: ImportCategory, reason: str) -> None:
        super().__init__(f"{category}: {' '.join(reason.split())[:120]}")
        self.category = category


def validate_queries(queries: Sequence[QuerySpec]) -> None:
    """Reject underidentified positives and unlabeled query families."""
    for query in queries:
        if not query.family:
            raise ValueError("query family is required")
        if query.negative:
            continue
        if not query.expected_slugs:
            raise ValueError("positive query requires relevant slugs")


def ndcg_at_k(actual_slugs: Sequence[str], relevant_slugs: Sequence[str], k: int) -> float:
    """Compute binary-relevance nDCG at k for a multi-label query."""
    if k < 1:
        raise ValueError("k must be positive")
    relevant = set(relevant_slugs)
    if not relevant:
        return 0.0
    dcg = 0.0
    for rank, slug in enumerate(actual_slugs[:k], start=1):
        if slug in relevant:
            dcg += 1.0 / _log2(rank + 1)
    ideal_hits = min(len(relevant), k)
    ideal = sum(1.0 / _log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / ideal if ideal else 0.0


def first_hit_rank(actual_slugs: Sequence[str], relevant_slugs: Sequence[str]) -> int | None:
    """Return the first one-based rank matching any relevant slug."""
    relevant = set(relevant_slugs)
    return next((rank for rank, slug in enumerate(actual_slugs, start=1) if slug in relevant), None)


def load_gutenberg_workload(path: Path = GUTENBERG_FIXTURE) -> CorpusResult:
    """Load the committed metadata-only Gutenberg workload without network access."""
    return _load_jsonl_workload(path, corpus="gutenberg", default_family="book-metadata")


def load_salesforce_workload(path: Path = SALESFORCE_FIXTURE) -> CorpusResult:
    """Load curated Salesforce Financial Services fact cards without network access."""
    return _load_jsonl_workload(path, corpus="salesforce", default_family="product-alias")


def import_gutenberg_catalog(
    *,
    catalog: Path,
    provenance: Path,
    output: Path,
    fixture_root: Path | None = None,
    book_ids: Sequence[str] | None = None,
) -> GutenbergProvenance:
    """Import a maintainer-supplied local Project Gutenberg catalog fixture."""
    root = (fixture_root or Path(__file__).resolve().parent / "data").resolve()
    output_path = _confined_output(output, root)
    catalog_path = _regular_file(catalog, suffix=".csv.gz")
    compressed_size = catalog_path.stat().st_size
    if compressed_size > GUTENBERG_MAX_COMPRESSED_BYTES:
        raise GutenbergImportError("source_too_large", "compressed catalog exceeds limit")
    provenance_data = _load_provenance(provenance)
    digest = _sha256(catalog_path)
    if provenance_data["sha256"] != digest:
        raise GutenbergImportError("source_unreproducible", "provenance digest mismatch")

    rows = [row for row in _read_catalog_rows(catalog_path) if row.get("Type", "Text") == "Text"]
    rows = _select_book_rows(rows, book_ids)
    author_index = _author_index(rows)
    imported = [_book_record(row, author_index) for row in rows]
    source = GutenbergProvenance(
        canonical_source_url=str(provenance_data["canonical_source_url"]),
        retrieved_at=str(provenance_data["retrieved_at"]),
        upstream_last_modified=cast(str | None, provenance_data.get("upstream_last_modified")),
        input_byte_size=compressed_size,
        sha256=digest,
    )
    _write_jsonl(output_path, imported, source)
    return source


def _load_jsonl_workload(path: Path, *, corpus: str, default_family: str) -> CorpusResult:
    rows = _read_jsonl(path)
    if corpus == "gutenberg":
        _validate_gutenberg_provenance(rows)
    if corpus == "salesforce":
        _validate_salesforce_cards(rows)
    queries: list[QuerySpec] = []
    for row in rows:
        slug = _required_str(row, "slug")
        for query in cast(list[Mapping[str, object]], row.get("queries", [])):
            slugs = [str(value) for value in cast(list[object], query.get("relevant_slugs", []))]
            queries.append(
                QuerySpec(
                    _required_str(query, "query"),
                    slugs,
                    _required_str(query, "difficulty"),
                    family=str(query.get("family", default_family)),
                    corpus=corpus,
                    negative=bool(query.get("negative", False)),
                )
            )
        if not row.get("queries"):
            queries.append(
                QuerySpec(
                    _required_str(row, "title"),
                    [slug],
                    "easy",
                    family=default_family,
                    corpus=corpus,
                )
            )
    validate_queries(queries)
    return CorpusResult(
        memories_written=len(rows), queries=queries, domain_counts={corpus: len(rows)}
    )


def _validate_gutenberg_provenance(rows: Sequence[Mapping[str, object]]) -> None:
    for row in rows:
        provenance = row.get("provenance")
        if not isinstance(provenance, Mapping):
            raise ValueError("Gutenberg fixture requires provenance")
        if provenance.get("canonical_source_url") != GUTENBERG_SOURCE_URL:
            raise ValueError("Gutenberg fixture source URL is invalid")
        if not isinstance(provenance.get("retrieved_at"), str):
            raise ValueError("Gutenberg fixture retrieval date is required")
        if not isinstance(provenance.get("input_byte_size"), int):
            raise ValueError("Gutenberg fixture byte size is required")
        digest = provenance.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("Gutenberg fixture SHA-256 digest is required")
        if row.get("metadata_only") is not True:
            raise ValueError("Gutenberg fixture must contain metadata only")


def _validate_salesforce_cards(rows: Sequence[Mapping[str, object]]) -> None:
    for row in rows:
        if row.get("metadata_only") is not True:
            raise ValueError("Salesforce fixture must contain factual metadata only")
        if "page_body" in row or "body" in row:
            raise ValueError("Salesforce fixture must not store source page bodies")
        for key in ("source_url", "access_date", "product_context"):
            if not isinstance(row.get(key), str) or not str(row[key]).strip():
                raise ValueError(f"Salesforce fixture requires {key}")


def _regular_file(path: Path, *, suffix: str) -> Path:
    expanded = path.expanduser()
    resolved = _expanded_regular_file(expanded, error=f"expected regular {suffix} file")
    if resolved.suffixes[-2:] != [".csv", ".gz"]:
        raise GutenbergImportError("path_rejected", f"expected regular {suffix} file")
    return resolved


def _confined_output(path: Path, root: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    if not resolved.is_relative_to(root):
        raise GutenbergImportError("path_rejected", "output must stay beneath fixture root")
    return resolved


def _load_provenance(path: Path) -> dict[str, object]:
    resolved = _expanded_regular_file(
        path.expanduser(),
        error="provenance must be a regular file",
    )
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GutenbergImportError("source_unreproducible", "invalid provenance JSON") from exc
    if not isinstance(data, dict):
        raise GutenbergImportError("source_unreproducible", "provenance must be an object")
    if data.get("canonical_source_url") != GUTENBERG_SOURCE_URL:
        raise GutenbergImportError("source_unreproducible", "provenance source URL mismatch")
    retrieved_at = data.get("retrieved_at")
    if not isinstance(retrieved_at, str) or not retrieved_at.strip():
        raise GutenbergImportError("source_unreproducible", "provenance retrieval date is required")
    try:
        datetime.strptime(retrieved_at, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise GutenbergImportError("source_unreproducible", "invalid retrieval date") from exc
    digest = data.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise GutenbergImportError("source_unreproducible", "provenance SHA-256 is required")
    last_modified = data.get("upstream_last_modified")
    if last_modified is not None and not isinstance(last_modified, str):
        raise GutenbergImportError("source_unreproducible", "invalid upstream Last-Modified value")
    return data


def _expanded_regular_file(path: Path, *, error: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise GutenbergImportError("path_rejected", error)
    return path.resolve(strict=True)


def _read_catalog_rows(catalog_path: Path) -> list[dict[str, str]]:
    expanded = _read_gzip_limited(catalog_path)
    try:
        text = expanded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GutenbergImportError("schema_invalid", "catalog must decode as UTF-8") from exc
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise GutenbergImportError("schema_invalid", "catalog header is missing")
    fields = set(reader.fieldnames)
    if not fields or not fields <= GUTENBERG_ALLOWED_COLUMNS:
        raise GutenbergImportError("schema_invalid", "catalog contains unsupported columns")
    rows: list[dict[str, str]] = []
    for index, row in enumerate(reader, start=1):
        if index > GUTENBERG_MAX_ROWS:
            raise GutenbergImportError("schema_invalid", "catalog row limit exceeded")
        clean = {key: value or "" for key, value in row.items() if key is not None}
        if any(len(value.encode("utf-8")) > GUTENBERG_MAX_CELL_BYTES for value in clean.values()):
            raise GutenbergImportError("schema_invalid", "catalog cell exceeds limit")
        rows.append(clean)
    return rows


def _read_gzip_limited(path: Path) -> bytes:
    chunks: list[bytes] = []
    total = 0
    try:
        with gzip.open(path, "rb") as handle:
            while chunk := handle.read(1024 * 1024):
                total += len(chunk)
                if total > GUTENBERG_MAX_EXPANDED_BYTES:
                    raise GutenbergImportError("source_too_large", "expanded catalog exceeds limit")
                chunks.append(chunk)
    except OSError as exc:
        raise GutenbergImportError("schema_invalid", "catalog is not valid gzip") from exc
    return b"".join(chunks)


def _author_index(rows: Sequence[Mapping[str, str]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for row in rows:
        book_id = _required_str(row, "Text#")
        slug = f"gutenberg-{book_id}"
        for author in _authors(row):
            index.setdefault(_author_query_name(author), []).append(slug)
    return {author: sorted(slugs) for author, slugs in index.items()}


def _authors(row: Mapping[str, str]) -> list[str]:
    return [part.strip() for part in row.get("Authors", "").split(";") if part.strip()]


def _author_query_name(author: str) -> str:
    parts = [
        part.strip()
        for part in author.split(",")
        if part.strip() and not part.strip().replace("-", "").isdigit()
    ]
    if len(parts) >= 2:
        return " ".join([*parts[1:], parts[0]])
    return parts[0] if parts else author.strip()


def _select_book_rows(
    rows: Sequence[dict[str, str]],
    book_ids: Sequence[str] | None,
) -> list[dict[str, str]]:
    if book_ids is None:
        return list(rows)
    requested = [book_id.strip() for book_id in book_ids if book_id.strip()]
    if not requested:
        raise GutenbergImportError("schema_invalid", "at least one selected book id is required")
    by_id = {_required_str(row, "Text#"): row for row in rows}
    missing = sorted(set(requested) - set(by_id))
    if missing:
        raise GutenbergImportError("schema_invalid", "selected book id is missing")
    return [by_id[book_id] for book_id in requested]


def _book_record(
    row: Mapping[str, str],
    author_index: Mapping[str, Sequence[str]],
) -> dict[str, object]:
    book_id = _required_str(row, "Text#")
    title = _required_str(row, "Title")
    authors = _authors(row)
    author_query = _author_query_name(authors[0]) if authors else ""
    slug = f"gutenberg-{book_id}"
    relevant = [slug]
    author_slugs = list(author_index.get(author_query, relevant)) if author_query else relevant
    return {
        "slug": slug,
        "book_id": book_id,
        "title": title,
        "authors": authors,
        "language": row.get("Language", ""),
        "subjects": row.get("Subjects", ""),
        "metadata_only": True,
        "queries": [
            {
                "query": title,
                "relevant_slugs": relevant,
                "difficulty": "easy",
                "family": "book-title",
            },
            *[
                {
                    "query": author_query,
                    "relevant_slugs": author_slugs,
                    "difficulty": "medium",
                    "family": "book-author",
                }
                for _author in authors[:1]
            ],
            {
                "query": _hard_metadata_query(title, author_query),
                "relevant_slugs": relevant,
                "difficulty": "hard",
                "family": "book-metadata",
            },
        ],
    }


def _hard_metadata_query(title: str, author_query: str) -> str:
    title_terms = [
        term.strip(" ,;:").casefold()
        for term in title.replace("-", " ").split()
        if term.strip(" ,;:").casefold() not in {"a", "an", "and", "or", "of", "the"}
    ]
    selected_terms = " ".join(dict.fromkeys(title_terms[:4]))
    return " ".join(part for part in [author_query, selected_terms] if part).strip()


def _write_jsonl(
    output_path: Path,
    rows: Sequence[Mapping[str, object]],
    provenance: GutenbergProvenance,
) -> None:
    payloads = [{**dict(row), "provenance": provenance.to_dict()} for row in rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=output_path.parent, delete=False, newline="\n"
        ) as handle:
            temp_path = Path(handle.name)
            for payload in payloads:
                handle.write(
                    json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
                    + "\n"
                )
        shutil.move(str(temp_path), output_path)
        temp_path = None
    except (TypeError, OSError) as exc:
        raise GutenbergImportError("serialization_failed", "failed to write JSONL") from exc
    finally:
        if temp_path is not None:
            with suppress(OSError):
                temp_path.unlink(missing_ok=True)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                rows.append(cast(dict[str, object], json.loads(line)))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid workload fixture: {path}") from exc
    return rows


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GutenbergImportError("schema_invalid", f"missing required field {key}")
    return value.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _log2(value: int) -> float:
    return (value.bit_length() - 1) if value > 0 and value & (value - 1) == 0 else _slow_log2(value)


def _slow_log2(value: int) -> float:
    import math

    return math.log2(value)
