"""Tests for the realistic corpus generator."""

from pathlib import Path

from memex.application.memory import Memex
from memex.infrastructure.config import MemexConfig
from memex.infrastructure.eval_realistic import RealisticCorpusGenerator


def _make_gen(tmp_path: Path, seed: int = 42) -> RealisticCorpusGenerator:
    return RealisticCorpusGenerator(tmp_path, seed=seed)


def test_generate_small_corpus(tmp_path: Path) -> None:
    gen = _make_gen(tmp_path)
    result = gen.generate(100)
    assert result.memories_written == 100
    assert len(result.queries) > 0
    assert result.elapsed_ms >= 0


def test_domain_distribution(tmp_path: Path) -> None:
    gen = _make_gen(tmp_path)
    result = gen.generate(1000)
    # Architecture is 25%, debugging 20%
    counts = result.domain_counts
    assert counts.get("entity", 0) >= 400  # arch + debug + api + infra are entities
    assert counts.get("procedure", 0) >= 80  # conventions
    assert counts.get("summary", 0) >= 100  # domain knowledge + temporal
    assert counts.get("episode", 0) >= 40  # sessions
    assert sum(counts.values()) == 1000


def test_files_have_valid_front_matter(tmp_path: Path) -> None:
    from memex.domain.frontmatter import parse_front_matter

    gen = _make_gen(tmp_path)
    gen.generate(50)
    files = list((tmp_path / "docs").rglob("*.md"))
    assert len(files) == 50
    for f in files:
        fm, body = parse_front_matter(f.read_text(encoding="utf-8"))
        assert fm["id"], f"empty id in {f.name}"
        assert fm["title"]
        assert body.strip()
        assert fm["content_hash"]


def test_unique_ids(tmp_path: Path) -> None:
    from memex.domain.frontmatter import parse_front_matter

    gen = _make_gen(tmp_path)
    gen.generate(200)
    ids = set()
    for f in (tmp_path / "docs").rglob("*.md"):
        fm, _ = parse_front_matter(f.read_text(encoding="utf-8"))
        ids.add(fm["id"])
    assert len(ids) == 200


def test_deterministic_with_same_seed(tmp_path: Path) -> None:
    gen1 = _make_gen(tmp_path / "a", seed=7)
    r1 = gen1.generate(100)
    gen2 = _make_gen(tmp_path / "b", seed=7)
    r2 = gen2.generate(100)
    assert [q.query for q in r1.queries] == [q.query for q in r2.queries]


def test_different_seed_produces_different_queries(tmp_path: Path) -> None:
    gen1 = _make_gen(tmp_path / "a", seed=1)
    r1 = gen1.generate(100)
    gen2 = _make_gen(tmp_path / "b", seed=2)
    r2 = gen2.generate(100)
    assert [q.query for q in r1.queries] != [q.query for q in r2.queries]


def test_queries_have_difficulty_labels(tmp_path: Path) -> None:
    gen = _make_gen(tmp_path)
    result = gen.generate(100)
    difficulties = {q.difficulty for q in result.queries}
    assert difficulties <= {"easy", "medium", "hard"}
    assert "easy" in difficulties
    assert "hard" in difficulties


def test_end_to_end_retrieval(tmp_path: Path) -> None:
    """Generate, index, and verify BM25 finds the expected memories."""
    gen = _make_gen(tmp_path)
    corpus = gen.generate(200)

    config = MemexConfig(data_dir=tmp_path)
    memex = Memex(config)
    try:
        memex.rebuild_index(force=True)
        assert memex.index_manager.count() == 200

        # Run a sample of ground-truth queries
        hits = 0
        sampled = corpus.queries[:: max(1, len(corpus.queries) // 50)]
        for q in sampled:
            result = memex.recall(q.query, top_k=10)
            actual = {h.slug for h in result.hits}
            if actual & set(q.expected_slugs):
                hits += 1
        # BM25 should find at least half of realistic queries in top-10
        assert hits / max(1, len(sampled)) >= 0.5
    finally:
        memex.close()


def test_corpus_content_is_diverse(tmp_path: Path) -> None:
    """Bodies should not all be identical — diversity is the point."""
    gen = _make_gen(tmp_path)
    gen.generate(200)
    bodies = set()
    for f in (tmp_path / "docs").rglob("*.md"):
        bodies.add(f.read_text(encoding="utf-8")[:200])
    # At least 100 distinct openings out of 200
    assert len(bodies) >= 100


def test_zero_size_produces_empty_corpus(tmp_path: Path) -> None:
    gen = _make_gen(tmp_path)
    result = gen.generate(0)
    assert result.memories_written == 0
    assert result.queries == []
