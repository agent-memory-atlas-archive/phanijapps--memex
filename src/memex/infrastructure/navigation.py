"""Generated OKF-style directory navigation over the memory tree.

``index.md`` files are disposable navigation views derived entirely from
memory pages: deterministic bytes, no timestamps, rebuilt on demand. The
root index carries ``okf_version: "0.2"`` front matter; descendant indexes
are body-only. ``log.md`` is never generated, never modified, never removed.
"""

from __future__ import annotations

import os
import posixpath
from dataclasses import dataclass, field
from pathlib import Path

from memex.domain.errors import MemexError
from memex.domain.models import NODE_TYPES, WikiNode
from memex.domain.reserved import RESERVED_FILENAMES, classify_reserved, is_structural
from memex.infrastructure.wiki_store import TYPE_DIRS

_CATEGORIES = ("written", "removed", "collision", "write_failed")
_DIAGNOSTIC_CATEGORIES = ("missing", "stale", "orphan", "collision")
_INDEX_NAME = "index.md"
_OKF_VERSION = "0.2"
_ESCAPE_CHARS = frozenset("\\`*_[]<>")


class NavigationError(MemexError):
    """Bounded navigation failure; never carries memory content."""


@dataclass(slots=True)
class NavigationChange:
    """One bounded navigation outcome: category plus docs-relative path."""

    category: str
    path: str


@dataclass(slots=True)
class NavigationReport:
    """Outcomes of a regeneration or refresh run. Bounded fields only."""

    changes: list[NavigationChange] = field(default_factory=list)

    def by_category(self, category: str) -> list[NavigationChange]:
        return [change for change in self.changes if change.category == category]


def _escape(text: str) -> str:
    """Render page text as inert Markdown: no markup, no HTML passthrough."""
    return "".join("\\" + ch if ch in _ESCAPE_CHARS else ch for ch in text)


class NavigationGenerator:
    """Deterministic ``index.md`` generation for the docs tree."""

    def __init__(self, wiki_dir: Path) -> None:
        self._wiki_dir = wiki_dir

    def regenerate(self, nodes: list[WikiNode]) -> NavigationReport:
        """Rewrite every needed index; remove obsolete generated ones.

        Obsolete indexes are removed only when they are structural files; a
        legacy page or any unrecognized file at an index path is reported as
        a collision and never touched.
        """
        report = NavigationReport()
        needed = self._needed_dirs(nodes)
        for directory in sorted(needed):
            self._write_index(directory, self.render(directory, nodes), report)
        for target in sorted(self._wiki_dir.rglob(_INDEX_NAME)):
            if target.parent in needed:
                continue
            self._remove_index(target.parent, report)
        return report

    def refresh(self, nodes: list[WikiNode], changed_dir: Path) -> NavigationReport:
        """Refresh indexes on the ancestor chain of one mutated directory.

        Best effort: filesystem failures become ``write_failed`` entries and
        never raise, so an authoritative page mutation stays successful.
        """
        report = NavigationReport()
        if not self._inside(changed_dir):
            return report
        needed = self._needed_dirs(nodes)
        chain: list[Path] = []
        current = changed_dir
        while current != self._wiki_dir:
            chain.append(current)
            current = current.parent
        chain.append(self._wiki_dir)  # the root index always belongs to the tree
        for directory in chain:
            if directory in needed:
                self._write_index(directory, self.render(directory, nodes), report)
            else:
                self._remove_index(directory, report)
        return report

    def diagnose(self, nodes: list[WikiNode]) -> list[NavigationChange]:
        """Compare the expected tree with on-disk indexes (read-only).

        Categories: ``missing`` (needed index absent), ``stale`` (bytes
        differ), ``orphan`` (structural index where no pages remain), and
        ``collision`` (legacy page blocking a needed index path).
        """
        changes: list[NavigationChange] = []
        needed = self._needed_dirs(nodes)
        for directory in sorted(needed):
            target = directory / _INDEX_NAME
            rel = self._rel(target)
            if not target.exists():
                changes.append(NavigationChange("missing", rel))
                continue
            if not is_structural(target):
                changes.append(NavigationChange("collision", rel))
                continue
            if target.read_text(encoding="utf-8") != self.render(directory, nodes):
                changes.append(NavigationChange("stale", rel))
        for target in sorted(self._wiki_dir.rglob(_INDEX_NAME)):
            if target.parent in needed or not is_structural(target):
                continue
            changes.append(NavigationChange("orphan", self._rel(target)))
        return changes

    def render(self, directory: Path, nodes: list[WikiNode]) -> str:
        """Deterministic bytes of one directory's index.

        Page entries are listed under node-type headings (``NODE_TYPES``
        order) sorted by slug, then child-directory links sorted by name.
        Every link is relative to this index's directory and resolved under
        the docs root before use.
        """
        if not self._inside(directory):
            raise NavigationError("navigation directory escapes the docs root")
        rel = directory.relative_to(self._wiki_dir).as_posix()
        lines = ["# index" if directory == self._wiki_dir else f"# {rel}"]
        direct = [
            node for node in nodes if node.file_path and Path(node.file_path).parent == directory
        ]
        for node_type in NODE_TYPES:
            pages = sorted(
                (node for node in direct if node.type == node_type), key=lambda n: n.slug
            )
            if not pages:
                continue
            lines.append("")
            lines.append(f"## {TYPE_DIRS[node_type].capitalize()}")
            for page in pages:
                link = self._link(directory, Path(page.file_path or ""))
                entry = f"- [{_escape(page.title)}]({link})"
                if page.description:
                    entry += f" — {_escape(page.description)}"
                lines.append(entry)
        children = sorted(
            child
            for child in directory.iterdir()
            if child.is_dir() and self._subtree_has_pages(child, nodes)
        )
        if children:
            lines.append("")
            lines.append("## Subdirectories")
            for child in children:
                lines.append(f"- [{child.name}/]({child.name}/{_INDEX_NAME})")
        body = "\n".join(lines) + "\n"
        if directory == self._wiki_dir:
            return f'---\nokf_version: "{_OKF_VERSION}"\n---\n{body}'
        return body

    def _needed_dirs(self, nodes: list[WikiNode]) -> set[Path]:
        """Directories needing an index: ancestors of page directories.

        An empty store needs none: navigation exists to disclose pages, and
        requiring a root index would fail ``verify`` on every fresh store
        until an explicit rebuild runs.
        """
        needed: set[Path] = set()
        for node in nodes:
            if not node.file_path:
                continue
            page_dir = Path(node.file_path).parent
            if not self._inside(page_dir):
                raise NavigationError("navigation target escapes the docs root")
            needed.add(self._wiki_dir)
            current = page_dir
            while current != self._wiki_dir:
                needed.add(current)
                current = current.parent
        return needed

    def _write_index(self, directory: Path, text: str, report: NavigationReport) -> None:
        target = directory / _INDEX_NAME
        rel = self._rel(target)
        if target.exists() and not is_structural(target):
            report.changes.append(NavigationChange("collision", rel))
            return
        tmp = target.with_name(target.name + ".tmp")
        try:
            directory.mkdir(parents=True, exist_ok=True)
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, target)
        except OSError:
            tmp.unlink(missing_ok=True)
            report.changes.append(NavigationChange("write_failed", rel))
            return
        report.changes.append(NavigationChange("written", rel))

    def _remove_index(self, directory: Path, report: NavigationReport) -> None:
        target = directory / _INDEX_NAME
        if not target.exists():
            return
        rel = self._rel(target)
        if not is_structural(target):
            report.changes.append(NavigationChange("collision", rel))
            return
        try:
            target.unlink()
        except OSError:
            report.changes.append(NavigationChange("write_failed", rel))
            return
        report.changes.append(NavigationChange("removed", rel))

    def _link(self, directory: Path, page_path: Path) -> str:
        resolved = page_path.resolve(strict=False)
        root = self._wiki_dir.resolve(strict=False)
        try:
            page_rel = resolved.relative_to(root)
            dir_rel = directory.resolve(strict=False).relative_to(root)
        except ValueError:
            raise NavigationError("navigation link target escapes the docs root") from None
        link = posixpath.relpath(page_rel.as_posix(), dir_rel.as_posix())
        if link.startswith(".."):
            raise NavigationError("navigation link target escapes the docs root")
        return link

    def _subtree_has_pages(self, directory: Path, nodes: list[WikiNode]) -> bool:
        resolved = directory.resolve(strict=False)
        for node in nodes:
            if not node.file_path or not self._inside(Path(node.file_path)):
                continue
            if Path(node.file_path).resolve(strict=False).is_relative_to(resolved):
                return True
        return False

    def _inside(self, path: Path) -> bool:
        try:
            path.resolve(strict=False).relative_to(self._wiki_dir.resolve(strict=False))
        except ValueError:
            return False
        return True

    def _rel(self, path: Path) -> str:
        return path.relative_to(self._wiki_dir).as_posix()


__all__ = [
    "RESERVED_FILENAMES",
    "NavigationChange",
    "NavigationError",
    "NavigationGenerator",
    "NavigationReport",
    "classify_reserved",
]
