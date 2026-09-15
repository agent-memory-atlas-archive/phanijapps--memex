from memex.domain.links import parse_links


def test_basic_links() -> None:
    assert parse_links("See [[ruff-linter]] and [[python-3-12]]") == [
        "ruff-linter",
        "python-3-12",
    ]


def test_case_insensitive_normalized() -> None:
    assert parse_links("[[Ruff Linter]]") == ["ruff-linter"]
    assert parse_links("[[RUFF]] and [[ruff]]") == ["ruff"]


def test_deduplicates_preserving_order() -> None:
    assert parse_links("[[b]] [[a]] [[b]]") == ["b", "a"]


def test_no_links() -> None:
    assert parse_links("plain text with [brackets] only") == []


def test_punctuation_only_link_dropped() -> None:
    assert parse_links("[[!!!]]") == []
