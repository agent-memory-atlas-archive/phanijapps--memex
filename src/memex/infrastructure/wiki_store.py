"""Filesystem CRUD for wiki Markdown pages (spec §7 Utility 1).

Pages live at ``docs/{type_dir}/{slug}.md`` with strict front matter.
Reads are side-effect free; access counting lives in the index layer.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from memex.domain.errors import WikiStoreError
from memex.domain.frontmatter import parse_front_matter, serialize_front_matter
from memex.domain.models import NODE_TYPES, PAGE_STATUSES, WikiNode, new_id, utc_now_iso
from memex.domain.slugs import derive_slug, unique_slug

TYPE_DIRS: dict[str, str] = {
    "entity": "entities",
    "preference": "preferences",
    "procedure": "procedures",
    "summary": "summaries",
    "episode": "episodes",
}

_FRONT_MATTER_KEYS: tuple[str, ...] = (
    "id",
    "type",
    "title",
    "tags",
    "importance",
    "created",
    "updated",
    "access_count",
    "last_access",
    "expires_at",
    "valid_from",
    "valid_to",
    "transcript_ref",
    "session_id",
    "links",
    "content_hash",
    "status",
    "occurred_at",
    "source",
    "harness",
    "confidence",
)

_STR_FIELDS: tuple[str, ...] = (
    "title",
    "created",
    "updated",
    "last_access",
    "expires_at",
    "valid_from",
    "valid_to",
    "transcript_ref",
    "session_id",
    "content_hash",
)


def hash_body(body: str) -> str:
    """SHA-256 of the Markdown body, prefixed for inspectability."""
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


NodeList = list[WikiNode]
StrList = list[str]


class WikiStore:
    """CRUD over the wiki directory tree. The filesystem is the truth."""

    LEGACY_DIR = "wiki"  # pre-0.2 layout; migrated in place, never deleted
    PAGES_DIR = "docs"

    def __init__(self, data_dir: Path, *, slug_algo: str = "kebab") -> None:
        self.data_dir = data_dir
        legacy = data_dir / self.LEGACY_DIR
        docs = data_dir / self.PAGES_DIR
        if legacy.is_dir() and not docs.exists():
            legacy.rename(docs)  # one-time migration to the docs layout
        self.wiki_dir = docs
        self.slug_algo = slug_algo
        for type_dir in TYPE_DIRS.values():
            (self.wiki_dir / type_dir).mkdir(parents=True, exist_ok=True)

    def get_path(self, slug: str, node_type: str | None = None) -> Path:
        """Path for a slug; searches type dirs when node_type is omitted."""
        if node_type is not None:
            if node_type not in TYPE_DIRS:
                raise WikiStoreError(f"unknown node type: {node_type!r}")
            return self.wiki_dir / TYPE_DIRS[node_type] / f"{slug}.md"
        for type_dir in TYPE_DIRS.values():
            candidate = self.wiki_dir / type_dir / f"{slug}.md"
            if candidate.exists():
                return candidate
        raise WikiStoreError(f"no wiki page found for slug: {slug!r}")

    def get_slug_from_path(self, path: Path) -> str:
        return path.stem

    def exists(self, slug: str) -> bool:
        try:
            self.get_path(slug)
        except WikiStoreError:
            return False
        return True

    def read(self, slug: str) -> WikiNode | None:
        """Parse a wiki page. Returns None when the slug does not exist."""
        try:
            path = self.get_path(slug)
        except WikiStoreError:
            return None
        return self._read_path(path)

    def write(self, node: WikiNode) -> WikiNode:
        """Persist a node and return it as stored.

        A new node (empty ``slug``) gets a derived, collision-suffixed slug.
        Writing to an existing slug updates it: ``id``, ``created``,
        ``access_count``, and ``last_access`` are preserved from the stored
        page; every other field comes from the input node (spec §7 Utility 1).
        """
        if node.type not in TYPE_DIRS:
            raise WikiStoreError(f"unknown node type: {node.type!r}")
        slug = node.slug or self._new_slug(node.title, node.id)
        existing = self.read(slug)

        stored = node
        stored.slug = slug
        if existing is not None:
            stored.id = existing.id
            stored.created = existing.created
            stored.access_count = existing.access_count
            stored.last_access = existing.last_access
        else:
            stored.id = node.id or new_id()
            if not stored.created:
                stored.created = utc_now_iso()
        stored.updated = utc_now_iso()
        stored.content_hash = hash_body(stored.body)
        stored.links = _merge_links(stored.links, stored.body)

        path = self.get_path(stored.slug, stored.type)
        self._atomic_write(path, serialize_front_matter(_node_to_dict(stored), stored.body))
        stored.file_path = str(path)
        return stored

    def list(self, node_type: str | None = None) -> NodeList:
        """All nodes, optionally filtered by type. Sorted by slug."""
        nodes = self.scan_all()
        if node_type is not None:
            if node_type not in TYPE_DIRS:
                raise WikiStoreError(f"unknown node type: {node_type!r}")
            nodes = [node for node in nodes if node.type == node_type]
        return sorted(nodes, key=lambda node: node.slug)

    def scan_all(self, errors: StrList | None = None) -> NodeList:
        """Traverse every type directory. Malformed pages are skipped and,
        when ``errors`` is provided, reported as messages."""
        nodes: NodeList = []
        for type_dir in TYPE_DIRS.values():
            directory = self.wiki_dir / type_dir
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.md")):
                try:
                    nodes.append(self._read_path(path))
                except WikiStoreError as exc:
                    if errors is None:
                        raise
                    errors.append(str(exc))
        return nodes

    def delete(self, slug: str) -> Path:
        """Delete a page. Raises WikiStoreError when it does not exist."""
        try:
            path = self.get_path(slug)
        except WikiStoreError as exc:
            raise WikiStoreError(f"cannot delete, no wiki page for slug: {slug!r}") from exc
        path.unlink()
        return path

    def move(self, slug: str, new_type: str) -> WikiNode:
        """Move a page to a different node type directory."""
        if new_type not in TYPE_DIRS:
            raise WikiStoreError(f"unknown node type: {new_type!r}")
        node = self.read(slug)
        if node is None:
            raise WikiStoreError(f"cannot move, no wiki page for slug: {slug!r}")
        old_path = self.get_path(slug)
        node.type = new_type
        node.updated = utc_now_iso()
        destination = self.get_path(slug, new_type)
        self._atomic_write(destination, serialize_front_matter(_node_to_dict(node), node.body))
        old_path.unlink()
        node.file_path = str(destination)
        return node

    def _new_slug(self, title: str, node_id: str) -> str:
        base = derive_slug(title, algo=self.slug_algo)
        if not base:
            base = (node_id or new_id())[:8]
        return unique_slug(base, self._taken_slugs())

    def _taken_slugs(self) -> set[str]:
        taken: set[str] = set()
        for type_dir in TYPE_DIRS.values():
            directory = self.wiki_dir / type_dir
            if directory.is_dir():
                taken.update(path.stem for path in directory.glob("*.md"))
        return taken

    def _read_path(self, path: Path) -> WikiNode:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WikiStoreError(f"cannot read wiki page: {exc.strerror}") from exc
        try:
            data, body = parse_front_matter(text)
        except Exception as exc:
            raise WikiStoreError(f"{path.name}: {exc}") from exc
        node = _node_from_dict(data, body)
        node.slug = path.stem
        node.file_path = str(path)
        return node

    def _atomic_write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".md.tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise WikiStoreError(f"cannot write wiki page: {exc.strerror}") from exc


def _merge_links(explicit: list[str], body: str) -> list[str]:
    """Canonical outgoing links: explicit list plus everything parsed from body."""
    from memex.domain.links import parse_links

    merged = list(explicit)
    for parsed in parse_links(body):
        if parsed not in merged:
            merged.append(parsed)
    return merged


def _node_to_dict(node: WikiNode) -> dict[str, object]:
    return {
        "id": node.id,
        "type": node.type,
        "title": node.title,
        "tags": node.tags,
        "importance": node.importance,
        "created": node.created,
        "updated": node.updated,
        "access_count": node.access_count,
        "last_access": node.last_access,
        "expires_at": node.expires_at,
        "valid_from": node.valid_from,
        "valid_to": node.valid_to,
        "transcript_ref": node.transcript_ref,
        "session_id": node.session_id,
        "links": node.links,
        "content_hash": node.content_hash,
        "status": node.status,
        "occurred_at": node.occurred_at,
        "source": node.source,
        "harness": node.harness,
        "confidence": node.confidence,
    }


def _str_value(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise WikiStoreError(f"front matter field {key!r} must be a string or null")
    return value


def _require_str(data: dict[str, object], key: str) -> str:
    value = _str_value(data, key)
    if value is None:
        raise WikiStoreError(f"front matter field {key!r} is required")
    return value


def _list_value(data: dict[str, object], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise WikiStoreError(f"front matter field {key!r} must be a list of strings")
    return value


def _status_value(data: dict[str, object]) -> str:
    value = data.get("status", "active")
    if isinstance(value, str) and value in PAGE_STATUSES:
        return value
    raise WikiStoreError(f"invalid page status: {value!r} (expected one of {PAGE_STATUSES})")


def _node_from_dict(data: dict[str, object], body: str) -> WikiNode:
    unknown = set(data) - set(_FRONT_MATTER_KEYS)
    if unknown:
        raise WikiStoreError(f"unknown front matter keys: {sorted(unknown)}")
    node_type = data.get("type")
    if not isinstance(node_type, str) or node_type not in NODE_TYPES:
        raise WikiStoreError(f"invalid node type: {node_type!r}")
    importance = data.get("importance", 0.5)
    if not isinstance(importance, int | float):
        raise WikiStoreError("front matter field 'importance' must be numeric")
    access_count = data.get("access_count", 0)
    if not isinstance(access_count, int):
        raise WikiStoreError("front matter field 'access_count' must be an integer")
    return WikiNode(
        type=node_type,
        title=_require_str(data, "title"),
        body=body,
        id=_require_str(data, "id"),
        tags=_list_value(data, "tags"),
        importance=float(importance),
        created=_require_str(data, "created"),
        updated=_require_str(data, "updated"),
        access_count=access_count,
        last_access=_str_value(data, "last_access"),
        expires_at=_str_value(data, "expires_at"),
        valid_from=_str_value(data, "valid_from"),
        valid_to=_str_value(data, "valid_to"),
        transcript_ref=_str_value(data, "transcript_ref"),
        session_id=_str_value(data, "session_id"),
        links=_list_value(data, "links"),
        content_hash=_str_value(data, "content_hash") or "",
        status=_status_value(data),
        occurred_at=_str_value(data, "occurred_at"),
        source=_str_value(data, "source"),
        harness=_str_value(data, "harness"),
        confidence=_str_value(data, "confidence"),
    )
