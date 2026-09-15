import pytest

from memex.domain.errors import FrontMatterError
from memex.domain.frontmatter import parse_front_matter, serialize_front_matter


class TestParse:
    def test_full_document(self) -> None:
        text = (
            "---\n"
            'id: "abc"\n'
            'type: "entity"\n'
            'title: "Ruff linter"\n'
            'tags: ["tool", "linter"]\n'
            "importance: 0.8\n"
            "access_count: 7\n"
            'created: "2026-09-15T10:00:00Z"\n'
            "expires_at: null\n"
            "---\n"
            "# Body here\n"
        )
        data, body = parse_front_matter(text)
        assert data["id"] == "abc"
        assert data["tags"] == ["tool", "linter"]
        assert data["importance"] == 0.8
        assert data["access_count"] == 7
        assert data["expires_at"] is None
        assert body == "# Body here\n"

    def test_empty_list(self) -> None:
        data, _ = parse_front_matter('---\nid: "a"\nlinks: []\n---\nbody')
        assert data["links"] == []

    def test_missing_open_delimiter(self) -> None:
        with pytest.raises(FrontMatterError, match="delimiter"):
            parse_front_matter("id: x\n---\n")

    def test_missing_close_delimiter(self) -> None:
        with pytest.raises(FrontMatterError, match="closing"):
            parse_front_matter('---\nid: "a"\n')

    def test_malformed_line(self) -> None:
        with pytest.raises(FrontMatterError, match="malformed"):
            parse_front_matter("---\nnope\n---\nbody")

    def test_duplicate_key(self) -> None:
        with pytest.raises(FrontMatterError, match="duplicate"):
            parse_front_matter('---\nid: "a"\nid: "b"\n---\nbody')

    def test_unquoted_string_rejected(self) -> None:
        with pytest.raises(FrontMatterError, match="unsupported value"):
            parse_front_matter("---\ntitle: bare words\n---\nbody")

    def test_unescaped_quote_rejected(self) -> None:
        with pytest.raises(FrontMatterError, match="quote"):
            parse_front_matter('---\ntitle: "a"b"\n---\nbody')


class TestSerialize:
    def test_roundtrip(self) -> None:
        data: dict[str, object] = {
            "id": "abc",
            "type": "entity",
            "title": 'Quoted "title"',
            "tags": ["a", "b"],
            "importance": 0.5,
            "created": "2026-09-15T10:00:00Z",
            "updated": "2026-09-15T10:00:00Z",
            "access_count": 0,
            "last_access": None,
            "links": [],
            "content_hash": "sha256:00",
        }
        text = serialize_front_matter(data, "body text")
        parsed, body = parse_front_matter(text)
        assert parsed == data
        assert body == "body text"

    def test_null_renders(self) -> None:
        text = serialize_front_matter({"expires_at": None}, "b")
        assert "expires_at: null" in text

    def test_escapes_in_list_items(self) -> None:
        text = serialize_front_matter({"links": ['say "hi"']}, "b")
        assert 'say \\"hi\\"' in text
