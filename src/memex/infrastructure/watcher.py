"""mtime-polling watcher for external wiki edits (spec §7 Utility 9)."""

from __future__ import annotations

import threading
from pathlib import Path

from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.link_manager import LinkManager
from memex.infrastructure.wiki_store import WikiStore, hash_body


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
    ) -> None:
        self._wiki_dir = wiki_dir
        self._index = index_mgr
        self._store = wiki_store
        self._links = link_mgr
        self.poll_interval = poll_interval
        self._mtimes: dict[str, float] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.snapshot()

    def snapshot(self) -> None:
        self._mtimes = {
            path.stem: path.stat().st_mtime
            for path in self._wiki_dir.rglob("*.md")
            if path.is_file()
        }

    def check(self) -> list[str]:
        """Slugs whose mtime differs from the last snapshot, plus deletions."""
        changed: list[str] = []
        current = {
            path.stem: path.stat().st_mtime
            for path in self._wiki_dir.rglob("*.md")
            if path.is_file()
        }
        for slug, mtime in current.items():
            if self._mtimes.get(slug) != mtime:
                changed.append(slug)
        for slug in self._mtimes:
            if slug not in current:
                changed.append(slug)
        self._mtimes = current
        return sorted(changed)

    def reindex_changed(self) -> int:
        """Re-index pages whose content actually changed. Returns the count.

        Change detection hashes the body text on read: a hand-edited page
        keeps a stale front-matter hash, so the index row is compared against
        a freshly computed hash instead.
        """
        count = 0
        for slug in self.check():
            row = self._index.get(slug)
            node = self._store.read(slug)
            if node is None:
                if row is not None:
                    self._index.remove_record(slug)
                    if self._links is not None:
                        self._links.remove_slug(slug)
                continue
            if row is not None and str(row["content_hash"]) == hash_body(node.body):
                continue  # touched but not edited
            stored = self._store.write(node)  # refresh stale front-matter hash
            self._index.update_record(stored)
            if self._links is not None:
                self._links.sync_node(stored)
            count += 1
        return count

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
