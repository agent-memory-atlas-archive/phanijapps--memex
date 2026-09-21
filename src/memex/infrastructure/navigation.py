"""Generated OKF-style directory navigation over the memory tree.

``index.md`` files are disposable navigation views derived entirely from
memory pages: deterministic bytes, no timestamps, rebuilt on demand. The
root index carries ``okf_version: "0.2"`` front matter; descendant indexes
are body-only. ``log.md`` is never generated, never modified, never removed.
"""

from __future__ import annotations

import itertools
import os
import posixpath
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from memex.domain.errors import MemexError
from memex.domain.models import NODE_TYPES, WikiNode
from memex.domain.reserved import OKF_VERSION, is_structural
from memex.infrastructure.wiki_store import TYPE_DIRS

_INDEX_NAME = "index.md"
_ESCAPE_CHARS = frozenset("\\`*_[]<>")

# Bounded per-directory page listing (WikiStore.scan_dir shaped); refresh
# parses only the mutated chain's own pages through it, never the store.
ScanDir = Callable[[Path, list[str] | None], list[WikiNode]]


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

    CATEGORIES: ClassVar[tuple[str, ...]] = ("written", "removed", "collision", "write_failed")

    changes: list[NavigationChange] = field(default_factory=list)

    def by_category(self, category: str) -> list[NavigationChange]:
        return [change for change in self.changes if change.category == category]

    def category_counts(self) -> dict[str, int]:
        return {category: len(self.by_category(category)) for category in self.CATEGORIES}


def _escape(text: str) -> str:
    """Render page text as inert Markdown: no markup, no HTML passthrough."""
    return "".join("\\" + ch if ch in _ESCAPE_CHARS else ch for ch in text)


class NavigationGenerator:
    """Deterministic ``index.md`` generation for the docs tree."""

    def __init__(self, wiki_dir: Path) -> None:
        self._wiki_dir = wiki_dir
        self._tmp_seq = itertools.count()

    def regenerate(self, nodes: list[WikiNode]) -> NavigationReport:
        """Rewrite every needed index; remove obsolete generated ones.

        Obsolete indexes are removed only when they are structural files; a
        legacy page or any unrecognized file at an index path is reported as
        a collision and never touched.
        """
        self._guard_nodes_inside(nodes)
        report = NavigationReport()
        self._sweep_stale_tmps()
        needed = self._needed_dirs()
        for directory in sorted(needed):
            self._write_index(directory, self.render(directory, nodes), report)
        for target in sorted(self._wiki_dir.rglob(_INDEX_NAME)):
            if target.parent in needed:
                continue
            self._remove_index(target.parent, report)
        return report

    def refresh(self, changed_dir: Path, scan_dir: ScanDir) -> NavigationReport:
        """Refresh indexes on the ancestor chain of one mutated directory.

        Parses only pages directly inside the chain's directories through
        ``scan_dir``, so one mutation's refresh cost never scales with the
        whole store; page existence elsewhere is a filesystem fact, not a
        parse. Best effort: filesystem failures become ``write_failed``
        entries and never raise, so an authoritative page mutation stays
        successful.
        """
        report = NavigationReport()
        if not self._inside(changed_dir):
            return report
        scan_errors: list[str] = []
        for directory in self._chain(changed_dir):
            if self._subtree_has_pages(directory):
                pages = scan_dir(directory, scan_errors)
                self._write_index(directory, self.render(directory, pages), report)
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
        needed = self._needed_dirs()
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
            if child.is_dir() and self._subtree_has_pages(child)
        )
        if children:
            lines.append("")
            lines.append("## Subdirectories")
            for child in children:
                lines.append(f"- [{child.name}/]({child.name}/{_INDEX_NAME})")
        body = "\n".join(lines) + "\n"
        if directory == self._wiki_dir:
            return f'---\nokf_version: "{OKF_VERSION}"\n---\n{body}'
        return body

    def _needed_dirs(self) -> set[Path]:
        """Directories needing an index: ancestors of page-holding directories.

        A page is a non-structural ``*.md`` in a type-directory position; the
        same predicate governs generation, refresh, and child links so the
        surfaces cannot disagree. An empty store needs none: navigation
        exists to disclose pages, and requiring a root index would fail
        ``verify`` on every fresh store until an explicit rebuild runs.
        """
        needed: set[Path] = set()
        for type_name in TYPE_DIRS.values():
            for path in self._wiki_dir.rglob(f"{type_name}/*.md"):
                if is_structural(path):
                    continue
                needed.add(self._wiki_dir)
                current = path.parent
                while current != self._wiki_dir:
                    needed.add(current)
                    current = current.parent
        return needed

    def _sweep_stale_tmps(self) -> None:
        """Remove index tmp files stranded by a hard kill mid-write."""
        for target in self._wiki_dir.rglob(f"{_INDEX_NAME}.*.tmp"):
            try:
                target.unlink()
            except OSError:
                continue  # bounded best effort; the file is inert to memory

    def _write_index(self, directory: Path, text: str, report: NavigationReport) -> None:
        target = directory / _INDEX_NAME
        rel = self._rel(target)
        if target.exists() and not is_structural(target):
            report.changes.append(NavigationChange("collision", rel))
            return
        # Process- and thread-unique temp name: concurrent index writes in
        # one directory cannot interleave each other's write/replace pair.
        tmp = target.with_name(f"{target.name}.{os.getpid()}.{next(self._tmp_seq)}.tmp")
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

    def _subtree_has_pages(self, directory: Path) -> bool:
        """Filesystem fact: does this subtree hold a memory page?

        A page is a non-structural ``*.md`` either directly in ``directory``
        when it is itself a type directory, or in a type-directory position
        below it. Existence only — no page parsing, so refresh cost stays
        bounded by directory walking rather than content.
        """
        if not directory.is_dir():
            return False
        if directory.name in TYPE_DIRS.values() and any(
            not is_structural(path) for path in directory.glob("*.md")
        ):
            return True
        return any(
            not is_structural(path)
            for type_name in TYPE_DIRS.values()
            for path in directory.rglob(f"{type_name}/*.md")
        )

    def _chain(self, changed_dir: Path) -> list[Path]:
        """The changed directory and every ancestor up to the docs root."""
        chain: list[Path] = []
        current = changed_dir
        while current != self._wiki_dir:
            chain.append(current)
            current = current.parent
        chain.append(self._wiki_dir)  # the root index always belongs to the tree
        return chain

    def _guard_nodes_inside(self, nodes: list[WikiNode]) -> None:
        """Reject caller-supplied pages whose paths escape the docs root."""
        for node in nodes:
            if node.file_path and not self._inside(Path(node.file_path)):
                raise NavigationError("navigation target escapes the docs root")

    def _inside(self, path: Path) -> bool:
        try:
            path.resolve(strict=False).relative_to(self._wiki_dir.resolve(strict=False))
        except ValueError:
            return False
        return True

    def _rel(self, path: Path) -> str:
        return path.relative_to(self._wiki_dir).as_posix()


__all__ = [
    "NavigationChange",
    "NavigationError",
    "NavigationGenerator",
    "NavigationReport",
]
