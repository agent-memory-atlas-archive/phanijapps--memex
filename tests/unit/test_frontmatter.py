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


class TestTypedLinks:
    """OKF v0.2 typed links live in inline flow mappings (spec AC-0003)."""

    def test_typed_link_round_trip(self) -> None:
        data: dict[str, object] = {
            "links": [
                {"target": "estate-runtime-edge", "rel": "relates-to"},
                {"target": "pcl-ent-workspace", "rel": "depends-on", "label": 'the "estate"'},
            ]
        }
        text = serialize_front_matter(data, "body")
        assert "links: [{target:" in text
        # One key per line: two typed links still occupy a single front-matter line.
        block = text.split("---\n")[1]
        assert block.strip().count("\n") == 0
        parsed, body = parse_front_matter(text)
        assert parsed == data
        assert body == "body"

    def test_mixed_list_items_are_independent(self) -> None:
        data, _ = parse_front_matter(
            '---\ntags: ["a", "b"]\nlinks: [{target: "x", rel: "y"}]\n---\nbody'
        )
        assert data["tags"] == ["a", "b"]
        assert data["links"] == [{"target": "x", "rel": "y"}]

    def test_comma_inside_quoted_mapping_value(self) -> None:
        data, _ = parse_front_matter('---\nlinks: [{target: "a,b", rel: "c"}]\n---\nbody')
        assert data["links"] == [{"target": "a,b", "rel": "c"}]

    def test_link_entry_rejects_unquoted_value(self) -> None:
        with pytest.raises(FrontMatterError, match="must be quoted"):
            parse_front_matter('---\nlinks: [{target: x, rel: "y"}]\n---\nbody')

    def test_link_entry_rejects_duplicate_key(self) -> None:
        with pytest.raises(FrontMatterError, match="duplicate mapping key"):
            parse_front_matter('---\nlinks: [{target: "a", target: "b"}]\n---\nbody')

    def test_link_entry_rejects_empty_mapping(self) -> None:
        with pytest.raises(FrontMatterError, match="mapping item is empty"):
            parse_front_matter("---\nlinks: [{}]\n---\nbody")

    def test_unbalanced_brace_rejected(self) -> None:
        with pytest.raises(FrontMatterError, match="unbalanced"):
            parse_front_matter('---\nlinks: [{target: "a"]\n---\nbody')

    def test_trailing_comma_rejected(self) -> None:
        with pytest.raises(FrontMatterError, match="empty collection item"):
            parse_front_matter('---\ntags: ["a",]\n---\nbody')

    def test_serializing_non_string_mapping_value_rejected(self) -> None:
        with pytest.raises(FrontMatterError, match="mapping values must be strings"):
            serialize_front_matter({"links": [{"target": "a", "rel": 2}]}, "b")
