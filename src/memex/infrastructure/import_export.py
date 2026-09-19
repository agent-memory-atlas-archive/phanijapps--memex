"""JSON import/export of wiki nodes (spec §7 Utility 15, §5.5)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from memex.domain.models import NODE_TYPES, WikiNode, utc_now_iso
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.link_manager import LinkManager
from memex.infrastructure.wiki_store import WikiStore

logger = logging.getLogger("memex")

EXPORT_VERSION = "1.0"


class ImportExport:
    """Export every wiki node as a JSON document; import them back."""

    def __init__(
        self, wiki_store: WikiStore, index_mgr: IndexManager, link_mgr: LinkManager
    ) -> None:
        self._store = wiki_store
        self._index = index_mgr
        self._links = link_mgr

    def export(self, output_path: Path | None = None) -> dict[str, object]:
        document: dict[str, object] = {
            "version": EXPORT_VERSION,
            "exported_at": utc_now_iso(),
            "nodes": [self._node_to_json(node) for node in self._store.list()],
        }
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return document

    def import_file(self, input_path: Path) -> dict[str, object]:
        try:
            data = json.loads(input_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read import file: {exc}") from exc
        return self.import_data(data)

    def import_data(self, data: dict[str, object]) -> dict[str, object]:
        nodes = data.get("nodes")
        if not isinstance(nodes, list):
            raise ValueError("import document must contain a 'nodes' array")
        imported = 0
        skipped: list[str] = []
        errors: list[str] = []
        for item in nodes:
            if not isinstance(item, dict):
                errors.append("non-object node entry skipped")
                continue
            try:
                node = self._node_from_json(item)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            slug = node.slug
            if not slug:
                skipped.append(str(item.get("title", "<untitled>")))
                continue
            stored = self._store.write(node)
            self._index.update_record(stored)
            self._links.sync_node(stored)
            imported += 1
        logger.info("operation=import imported=%d errors=%d", imported, len(errors))
        return {"imported": imported, "skipped": skipped, "errors": errors}

    @staticmethod
    def _node_to_json(node: WikiNode) -> dict[str, object]:
        return {
            "slug": node.slug,
            "type": node.type,
            "title": node.title,
            "tags": node.tags,
            "importance": node.importance,
            "created": node.created,
            "updated": node.updated,
            "body": node.body,
            "links": node.links,
            "transcript_ref": node.transcript_ref,
            "scope": node.scope,
            "project_id": node.project_id,
            "project_label": node.project_label,
        }

    def _node_from_json(self, item: dict[str, object]) -> WikiNode:
        node_type = item.get("type")
        title = item.get("title")
        if not isinstance(node_type, str) or node_type not in NODE_TYPES:
            raise ValueError(f"invalid node type: {node_type!r}")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("node title must be a non-empty string")
        importance = item.get("importance", 0.5)
        if not isinstance(importance, int | float):
            raise ValueError("importance must be numeric")
        slug = item.get("slug")
        transcript_ref = item.get("transcript_ref")
        scope = item.get("scope", "global")
        project_id = item.get("project_id")
        project_label = item.get("project_label")
        if scope not in {"global", "project"}:
            raise ValueError("scope must be 'global' or 'project'")
        if scope == "project" and not isinstance(project_id, str):
            raise ValueError("project_id is required for project scope")
        if project_id is not None and not isinstance(project_id, str):
            raise ValueError("project_id must be a string or null")
        if project_label is not None and not isinstance(project_label, str):
            raise ValueError("project_label must be a string or null")
        return WikiNode(
            type=node_type,
            title=title,
            body=self._str(item, "body"),
            id=self._str(item, "id"),
            slug=str(slug) if isinstance(slug, str) and slug else "",
            tags=self._str_list(item, "tags"),
            importance=float(importance),
            created=self._str(item, "created") or utc_now_iso(),
            updated=self._str(item, "updated") or utc_now_iso(),
            transcript_ref=transcript_ref if isinstance(transcript_ref, str) else None,
            links=self._str_list(item, "links"),
            scope=str(scope),
            project_id=project_id,
            project_label=project_label,
        )

    @staticmethod
    def _str(item: dict[str, object], key: str) -> str:
        value = item.get(key)
        return value if isinstance(value, str) else ""

    @staticmethod
    def _str_list(item: dict[str, object], key: str) -> list[str]:
        value = item.get(key, [])
        if not isinstance(value, list) or not all(isinstance(entry, str) for entry in value):
            raise ValueError(f"node field {key!r} must be a list of strings")
        return value
