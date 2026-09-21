"""mtime-polling watcher for external wiki edits (spec §7 Utility 9)."""

from __future__ import annotations

import threading
from pathlib import Path

from memex.domain.models import WikiNode
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.link_manager import LinkManager
from memex.infrastructure.navigation import NavigationGenerator
from memex.infrastructure.wiki_store import WikiStore, hash_body

ChangeKey = tuple[str, str, str, str]


class IndexWatcher:
    """Detects externally edited wiki pages and re-indexes them.

    No inotify: cross-platform mtime polling. A changed mtime with an
    unchanged content hash means the file was touched, not edited, and is
    skipped.
    """

    def __init__(
        self,
        wiki_dir: Path,
        index_mgr: IndexManager,
        wiki_store: WikiStore,
        poll_interval: int = 60,
        link_mgr: LinkManager | None = None,
        *,
        navigation: NavigationGenerator | None = None,
    ) -> None:
        self._wiki_dir = wiki_dir
        self._index = index_mgr
        self._store = wiki_store
        self._links = link_mgr
        self._navigation = navigation
        self.poll_interval = poll_interval
        self._mtimes: dict[ChangeKey, float] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.snapshot()

    def snapshot(self) -> None:
        self._mtimes = self._current_mtimes()

    def check(self) -> list[str]:
        """Slugs whose mtime differs from the last snapshot, plus deletions."""
        changed: list[ChangeKey] = []
        current = self._current_mtimes()
        for key, mtime in current.items():
            if self._mtimes.get(key) != mtime:
                changed.append(key)
        for key in self._mtimes:
            if key not in current:
                changed.append(key)
        self._mtimes = current
        return [_format_key(key) for key in sorted(changed)]

    def reindex_changed(self) -> int:
        """Re-index pages whose content actually changed. Returns the count.

        Change detection hashes the body text on read: a hand-edited page
        keeps a stale front-matter hash, so the index row is compared against
        a freshly computed hash instead.
        """
        count = 0
        changed = self._changed_keys()
        changed_dirs: list[Path] = []
        for scope, project_id, node_type, slug in changed:
            row = self._index.get(slug, scope=scope, project_id=project_id, node_type=node_type)
            node = self._store.read(slug, node_type, scope=scope, project_id=project_id or None)
            if node is None:
                if row is not None:
                    self._index.remove_record(
                        slug, scope=scope, project_id=project_id, node_type=node_type
                    )
                    if self._links is not None:
                        self._links.remove_slug(
                            slug, source_scope=scope, source_project_id=project_id
                        )
                    if row["file_path"]:
                        changed_dirs.append(Path(str(row["file_path"])).parent)
                continue
            if (
                row is not None
                and str(row["content_hash"]) == hash_body(node.body)
                and str(row["description"] or "") == node.description
            ):
                continue  # touched but not edited
            changed_dirs.append(Path(str(node.file_path)).parent)
            stored = self._store.write(node)  # refresh stale front-matter hash
            self._index.update_record(stored)
            if self._links is not None:
                self._links.sync_node(stored)
            count += 1
        self._refresh_navigation(changed_dirs)
        return count

    def _refresh_navigation(self, changed_dirs: list[Path]) -> None:
        """Best-effort navigation refresh; never fails re-indexing."""
        if self._navigation is None or not changed_dirs:
            return
        nodes = self._store.scan_all()
        for directory in dict.fromkeys(changed_dirs):
            try:
                self._navigation.refresh(nodes, directory)
            except OSError:
                # Navigation is disposable: verification reports the drift.
                continue

    def _changed_keys(self) -> list[ChangeKey]:
        current = self._current_mtimes()
        changed = [key for key, mtime in current.items() if self._mtimes.get(key) != mtime]
        changed.extend(key for key in self._mtimes if key not in current)
        self._mtimes = current
        return sorted(changed)

    def _current_mtimes(self) -> dict[ChangeKey, float]:
        mtimes: dict[ChangeKey, float] = {}
        for node in self._store.scan_all():
            if node.file_path is None:
                continue
            path = Path(node.file_path)
            if path.is_file():
                mtimes[_node_key(node)] = path.stat().st_mtime
        return mtimes

    def start_polling(self) -> None:
        if self.poll_interval <= 0 or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop_polling(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _poll_loop(self) -> None:
        while not self._stop.wait(self.poll_interval):
            self.reindex_changed()


def _node_key(node: WikiNode) -> ChangeKey:
    return (
        node.scope,
        node.project_id or "",
        node.type,
        node.slug,
    )


def _format_key(key: ChangeKey) -> str:
    return key[3]
