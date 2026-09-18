# STUB: AC-0033
import gzip
import hashlib
import json
import re
import socket
import urllib.request
from pathlib import Path

import pytest

from eval.corpus import QuerySpec
from eval.realistic import RealisticCorpusGenerator
from eval.workloads import (
    GUTENBERG_SOURCE_URL,
    GutenbergImportError,
    first_hit_rank,
    import_gutenberg_catalog,
    load_gutenberg_workload,
    load_salesforce_workload,
    ndcg_at_k,
    validate_queries,
)


def test_positive_queries_require_relevance_and_family() -> None:
    with pytest.raises(ValueError, match="query family"):
        validate_queries([QuerySpec("find book", ["book"], "hard", family="")])


def test_realistic_queries_are_answerable_and_family_labeled(tmp_path: Path) -> None:
    corpus = RealisticCorpusGenerator(tmp_path, seed=42).generate(120)

    validate_queries(corpus.queries)

    debug = [query for query in corpus.queries if query.family == "debug-symptom"]
    sessions = [query for query in corpus.queries if query.family == "session-verb"]
    assert debug
    assert sessions
    assert any(len(query.expected_slugs) > 1 for query in debug)
    assert any(len(query.expected_slugs) > 1 for query in sessions)


def test_realistic_architecture_hard_queries_expose_expected_discriminators(
    tmp_path: Path,
) -> None:
    corpus = RealisticCorpusGenerator(tmp_path, seed=42).generate(120)

    hard_architecture = [
        query for query in corpus.queries if query.family == "arch" and query.difficulty == "hard"
    ]

    assert hard_architecture
    for query in hard_architecture:
        query_tokens = set(re.findall(r"[a-z0-9]+", query.query.casefold()))
        for slug in query.expected_slugs:
            slug_tokens = {
                part for part in slug.split("-") if part != "design" and not part.isdigit()
            }
            assert slug_tokens <= query_tokens


def test_realistic_positive_queries_expose_topic_discriminators(tmp_path: Path) -> None:
    corpus = RealisticCorpusGenerator(tmp_path, seed=42).generate(160)

    _assert_queries_cover_expected_title_terms(
        tmp_path,
        [
            query
            for query in corpus.queries
            if query.family == "arch" and query.difficulty == "easy"
        ],
        stop_words={"design"},
    )
    _assert_queries_cover_expected_title_terms(
        tmp_path,
        [
            query
            for query in corpus.queries
            if query.family == "infra" and query.difficulty == "medium"
        ],
    )
    temporal_queries = [
        query
        for query in corpus.queries
        if query.family == "temporal" and query.difficulty == "medium"
    ]
    assert temporal_queries
    for query in temporal_queries:
        title_tokens = re.findall(r"[a-z0-9]+", _page_title(tmp_path, query.expected_slugs[0]))
        query_tokens = set(re.findall(r"[a-z0-9]+", query.query.casefold()))
        assert {title_tokens[0], title_tokens[3]} <= query_tokens
    convention_queries = [
        query for query in corpus.queries if query.family == "conv" and query.difficulty == "medium"
    ]
    assert convention_queries
    for query in convention_queries:
        expected_body = _page_body(tmp_path, query.expected_slugs[0]).casefold()
        convention = expected_body.split("always ", 1)[1].split(". never", 1)[0]
        assert convention in query.query.casefold()


def test_gutenberg_import_is_bounded_offline_and_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = tmp_path / "pg_catalog.csv.gz"
    rows = (
        "Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves\n"
        '1342,Text,1998-06-01,Pride and Prejudice,en,"Austen, Jane",Fiction,PR,\n'
        '158,Text,1994-09-01,Emma,en,"Austen, Jane",Fiction,PR,\n'
    )
    with gzip.open(catalog, "wt", encoding="utf-8", newline="") as handle:
        handle.write(rows)
    digest = hashlib.sha256(catalog.read_bytes()).hexdigest()
    provenance = tmp_path / "pg_catalog.provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "canonical_source_url": GUTENBERG_SOURCE_URL,
                "retrieved_at": "2026-09-18",
                "upstream_last_modified": "Fri, 18 Sep 2026 00:00:00 GMT",
                "sha256": digest,
            }
        ),
        encoding="utf-8",
    )
    fixture_root = tmp_path / "fixtures"
    output = fixture_root / "gutenberg-books.jsonl"

    monkeypatch.setattr(socket, "create_connection", _fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", _fail_network)
    first = import_gutenberg_catalog(
        catalog=catalog,
        provenance=provenance,
        output=output,
        fixture_root=fixture_root,
        book_ids=("1342", "158"),
    )
    first_bytes = output.read_bytes()
    second = import_gutenberg_catalog(
        catalog=catalog,
        provenance=provenance,
        output=output,
        fixture_root=fixture_root,
        book_ids=("1342", "158"),
    )

    assert first == second
    assert output.read_bytes() == first_bytes
    loaded = load_gutenberg_workload(output)
    author_queries = [query for query in loaded.queries if query.family == "book-author"]
    assert any(
        set(query.expected_slugs) == {"gutenberg-1342", "gutenberg-158"} for query in author_queries
    )
    assert b"Pride and Prejudice" in first_bytes
    assert b"It is a truth universally acknowledged" not in first_bytes
    assert b'"input_byte_size":' in first_bytes
    assert digest.encode() in first_bytes


def test_gutenberg_import_rejects_schema_and_output_escape(tmp_path: Path) -> None:
    catalog = tmp_path / "pg_catalog.csv.gz"
    with gzip.open(catalog, "wt", encoding="utf-8", newline="") as handle:
        handle.write("Text#,Title,Unexpected\n1,Example,nope\n")
    digest = hashlib.sha256(catalog.read_bytes()).hexdigest()
    provenance = tmp_path / "pg_catalog.provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "canonical_source_url": GUTENBERG_SOURCE_URL,
                "retrieved_at": "2026-09-18",
                "sha256": digest,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(GutenbergImportError, match="schema_invalid"):
        import_gutenberg_catalog(
            catalog=catalog,
            provenance=provenance,
            output=tmp_path / "fixtures" / "books.jsonl",
            fixture_root=tmp_path / "fixtures",
        )
    with pytest.raises(GutenbergImportError, match="path_rejected"):
        import_gutenberg_catalog(
            catalog=catalog,
            provenance=provenance,
            output=tmp_path / "outside.jsonl",
            fixture_root=tmp_path / "fixtures",
        )


def test_gutenberg_import_rejects_unsafe_text_number_before_write(tmp_path: Path) -> None:
    catalog = tmp_path / "pg_catalog.csv.gz"
    with gzip.open(catalog, "wt", encoding="utf-8", newline="") as handle:
        handle.write(
            "Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves\n"
            '"../../escape",Text,1998-06-01,Escaping Book,en,"Austen, Jane",Fiction,PR,\n'
        )
    digest = hashlib.sha256(catalog.read_bytes()).hexdigest()
    provenance = tmp_path / "pg_catalog.provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "canonical_source_url": GUTENBERG_SOURCE_URL,
                "retrieved_at": "2026-09-18",
                "sha256": digest,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "fixtures" / "books.jsonl"

    with pytest.raises(GutenbergImportError, match="schema_invalid"):
        import_gutenberg_catalog(
            catalog=catalog,
            provenance=provenance,
            output=output,
            fixture_root=tmp_path / "fixtures",
        )

    assert not output.exists()


def test_gutenberg_import_rejects_tilde_catalog_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, provenance = _write_valid_gutenberg_inputs(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    catalog_link = home / "pg_catalog.csv.gz"
    catalog_link.symlink_to(catalog)
    monkeypatch.setenv("HOME", str(home))

    with pytest.raises(GutenbergImportError, match="path_rejected"):
        import_gutenberg_catalog(
            catalog=Path("~/pg_catalog.csv.gz"),
            provenance=provenance,
            output=tmp_path / "fixtures" / "books.jsonl",
            fixture_root=tmp_path / "fixtures",
            book_ids=("1342",),
        )


def test_gutenberg_import_rejects_tilde_provenance_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, provenance = _write_valid_gutenberg_inputs(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    provenance_link = home / "pg_catalog.provenance.json"
    provenance_link.symlink_to(provenance)
    monkeypatch.setenv("HOME", str(home))

    with pytest.raises(GutenbergImportError, match="path_rejected"):
        import_gutenberg_catalog(
            catalog=catalog,
            provenance=Path("~/pg_catalog.provenance.json"),
            output=tmp_path / "fixtures" / "books.jsonl",
            fixture_root=tmp_path / "fixtures",
            book_ids=("1342",),
        )


def test_gutenberg_import_requires_exact_provenance_and_selected_ids(tmp_path: Path) -> None:
    catalog = tmp_path / "pg_catalog.csv.gz"
    with gzip.open(catalog, "wt", encoding="utf-8", newline="") as handle:
        handle.write(
            "Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves\n"
            '1342,Text,1998-06-01,Pride and Prejudice,en,"Austen, Jane",Fiction,PR,\n'
        )
    digest = hashlib.sha256(catalog.read_bytes()).hexdigest()
    provenance = tmp_path / "pg_catalog.provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "canonical_source_url": "https://example.invalid/catalog.csv.gz",
                "retrieved_at": "2026-09-18",
                "sha256": digest,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(GutenbergImportError, match="source_unreproducible"):
        import_gutenberg_catalog(
            catalog=catalog,
            provenance=provenance,
            output=tmp_path / "fixtures" / "books.jsonl",
            fixture_root=tmp_path / "fixtures",
            book_ids=("1342",),
        )

    provenance.write_text(
        json.dumps(
            {
                "canonical_source_url": GUTENBERG_SOURCE_URL,
                "retrieved_at": "2026-09-18",
                "sha256": digest,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GutenbergImportError, match="schema_invalid"):
        import_gutenberg_catalog(
            catalog=catalog,
            provenance=provenance,
            output=tmp_path / "fixtures" / "books.jsonl",
            fixture_root=tmp_path / "fixtures",
            book_ids=("84",),
        )


def test_salesforce_fixture_is_fact_only_and_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "create_connection", _fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", _fail_network)

    workload = load_salesforce_workload()

    validate_queries(workload.queries)
    hard_alias = [
        query for query in workload.queries if query.query == "FSC customer financial relationships"
    ]
    assert hard_alias
    assert set(hard_alias[0].expected_slugs) == {
        "salesforce-actionable-segmentation",
        "salesforce-financial-account",
    }
    negative_controls = [query for query in workload.queries if query.negative]
    assert len(negative_controls) == 1
    assert negative_controls[0].corpus == "salesforce"
    assert negative_controls[0].family == "negative-control"
    assert negative_controls[0].expected_slugs == []
    raw_fixture = Path("eval/data/salesforce-facts.jsonl").read_text(encoding="utf-8")
    assert "source_url" in raw_fixture
    assert "page_body" not in raw_fixture
    assert "automated scraping" not in raw_fixture


def test_gutenberg_fixture_load_rejects_unsafe_row_slug(tmp_path: Path) -> None:
    fixture = tmp_path / "gutenberg-books.jsonl"
    _write_workload_row(
        fixture,
        {
            "slug": "../escape",
            "title": "Escaping Book",
            "metadata_only": True,
            "provenance": _valid_gutenberg_provenance(),
        },
    )

    with pytest.raises(ValueError, match="invalid gutenberg fixture slug"):
        load_gutenberg_workload(fixture)


def test_gutenberg_fixture_load_rejects_unsafe_relevant_slug(tmp_path: Path) -> None:
    fixture = tmp_path / "gutenberg-books.jsonl"
    _write_workload_row(
        fixture,
        {
            "slug": "gutenberg-1342",
            "title": "Pride and Prejudice",
            "metadata_only": True,
            "provenance": _valid_gutenberg_provenance(),
            "queries": [
                {
                    "query": "Jane Austen",
                    "relevant_slugs": ["../../escape"],
                    "difficulty": "hard",
                    "family": "book-author",
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="invalid gutenberg relevant_slug"):
        load_gutenberg_workload(fixture)


def test_multi_label_metrics_ignore_negative_queries() -> None:
    assert first_hit_rank(["miss", "target-b"], ["target-a", "target-b"]) == 2
    assert ndcg_at_k(["target-b", "miss", "target-a"], ["target-a", "target-b"], 10) > 0.90
    validate_queries(
        [
            QuerySpec("no known book", [], "hard", family="negative", negative=True),
            QuerySpec("known book", ["book"], "hard", family="book-title"),
        ]
    )


def _fail_network(*args: object, **kwargs: object) -> None:
    del args, kwargs
    raise AssertionError("network access is forbidden")


def _write_valid_gutenberg_inputs(tmp_path: Path) -> tuple[Path, Path]:
    catalog = tmp_path / "pg_catalog.csv.gz"
    with gzip.open(catalog, "wt", encoding="utf-8", newline="") as handle:
        handle.write(
            "Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves\n"
            '1342,Text,1998-06-01,Pride and Prejudice,en,"Austen, Jane",Fiction,PR,\n'
        )
    digest = hashlib.sha256(catalog.read_bytes()).hexdigest()
    provenance = tmp_path / "pg_catalog.provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "canonical_source_url": GUTENBERG_SOURCE_URL,
                "retrieved_at": "2026-09-18",
                "sha256": digest,
            }
        ),
        encoding="utf-8",
    )
    return catalog, provenance


def _valid_gutenberg_provenance() -> dict[str, object]:
    return {
        "canonical_source_url": GUTENBERG_SOURCE_URL,
        "retrieved_at": "2026-09-18",
        "input_byte_size": 1,
        "sha256": "0" * 64,
    }


def _write_workload_row(path: Path, row: dict[str, object]) -> None:
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def _assert_queries_cover_expected_title_terms(
    data_dir: Path,
    queries: list[QuerySpec],
    *,
    stop_words: set[str] | None = None,
) -> None:
    assert queries
    ignored = stop_words or set()
    for query in queries:
        title_tokens = set(re.findall(r"[a-z0-9]+", _page_title(data_dir, query.expected_slugs[0])))
        query_tokens = set(re.findall(r"[a-z0-9]+", query.query.casefold()))
        assert title_tokens - ignored <= query_tokens


def _page_title(data_dir: Path, slug: str) -> str:
    text = _page_text(data_dir, slug)
    match = re.search(r"^title: (.+)$", text, flags=re.MULTILINE)
    assert match is not None
    return match.group(1).casefold()


def _page_text(data_dir: Path, slug: str) -> str:
    matches = list((data_dir / "docs").rglob(f"{slug}.md"))
    assert len(matches) == 1
    return matches[0].read_text(encoding="utf-8")


def _page_body(data_dir: Path, slug: str) -> str:
    return _page_text(data_dir, slug).split("---", 2)[2]
