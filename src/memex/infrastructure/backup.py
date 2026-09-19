"""Backup and restore via tar.gz archives (spec §7 Utility 12).

Restore validates every archive member against path traversal and symlink
attacks before extraction, and moves current data aside instead of deleting.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path

from memex.domain.errors import BackupError
from memex.domain.models import BackupReport, RestoreReport, utc_now_iso

ARCHIVE_VERSION = "1.0"
_ALLOWED_PREFIXES = ("docs/", "wiki/", "transcripts/")  # wiki/: pre-0.2 archives
_ALLOWED_NAMES = ("docs", "wiki", "transcripts", "mem.db", "manifest.json")


class BackupRestore:
    """Archive wiki/, transcripts/, and (optionally) mem.db."""

    def __init__(self, data_dir: Path, db_path: Path) -> None:
        self.data_dir = data_dir
        self.db_path = db_path

    def _pages_dir(self) -> Path:
        """docs/ layout, falling back to a not-yet-migrated wiki/ dir."""
        docs = self.data_dir / "docs"
        return docs if docs.is_dir() else self.data_dir / "wiki"

    def backup(self, output_path: Path, *, include_mem_db: bool = True) -> BackupReport:
        started = time.perf_counter()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wiki_count = self._count_files(self._pages_dir(), "*.md")
        transcript_count = self._count_files(self.data_dir / "transcripts", "*")
        db_count = 1 if (include_mem_db and self.db_path.exists()) else 0

        try:
            with tarfile.open(output_path, "w:gz") as archive:
                for name in (self._pages_dir().name, "transcripts"):
                    directory = self.data_dir / name
                    if directory.is_dir():
                        archive.add(directory, arcname=name)
                if db_count:
                    snapshot = self._snapshot_db()
                    try:
                        archive.add(snapshot, arcname="mem.db")
                    finally:
                        snapshot.unlink(missing_ok=True)
                manifest = {
                    "version": ARCHIVE_VERSION,
                    "backed_up_at": utc_now_iso(),
                    "memex_version": _version(),
                    "file_counts": {
                        "wiki": wiki_count,
                        "transcripts": transcript_count,
                        "mem_db": db_count,
                    },
                }
                self._add_text(archive, "manifest.json", json.dumps(manifest, indent=2))
        except (OSError, tarfile.TarError) as exc:
            raise BackupError(f"backup failed: {exc}") from exc

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return BackupReport(
            archive_path=str(output_path),
            size_bytes=output_path.stat().st_size,
            file_counts={"wiki": wiki_count, "transcripts": transcript_count, "mem_db": db_count},
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    def verify(self, archive_path: Path) -> bool:
        """True when the archive parses and carries a valid manifest."""
        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                names = set(archive.getnames())
                if "manifest.json" not in names:
                    return False
                extracted = archive.extractfile("manifest.json")
                if extracted is None:
                    return False
                manifest: dict[str, object] = json.loads(extracted.read().decode("utf-8"))
                return manifest.get("version") == ARCHIVE_VERSION
        except (OSError, tarfile.TarError, json.JSONDecodeError):
            return False

    def restore(self, input_path: Path) -> RestoreReport:
        """Extract a verified archive over the current data directory."""
        warnings: list[str] = []
        if not input_path.exists():
            raise BackupError(f"archive not found: {input_path}")
        if not self.verify(input_path):
            raise BackupError("archive failed verification (missing manifest or bad version)")

        with tempfile.TemporaryDirectory(prefix="memex-restore-") as tmp:
            staging = Path(tmp)
            try:
                with tarfile.open(input_path, "r:gz") as archive:
                    self._safe_extract(archive, staging)
            except (OSError, tarfile.TarError) as exc:
                raise BackupError(f"restore failed during extraction: {exc}") from exc

            backup_dir: Path | None = None
            moved = [
                name
                for name in ("wiki", "transcripts", "mem.db")
                if (self.data_dir / name).exists()
            ]
            if moved:
                backup_dir = self.data_dir / f"pre-restore-{utc_now_iso().replace(':', '')}"
                backup_dir.mkdir(parents=True)
                for name in moved:
                    shutil.move(str(self.data_dir / name), str(backup_dir / name))
                for sidecar in self.data_dir.glob("mem.db-*"):
                    shutil.move(str(sidecar), str(backup_dir / sidecar.name))
                warnings.append(f"previous data moved to {backup_dir}")

            for name in ("docs", "wiki", "transcripts"):
                source = staging / name
                if source.is_dir():
                    shutil.copytree(source, self.data_dir / name, dirs_exist_ok=True)
            # Old archives carry wiki/; WikiStore migrates it on next open.
            if (staging / "mem.db").exists():
                shutil.copy2(staging / "mem.db", self.db_path)

            wiki_count = self._count_files(self.data_dir / "docs", "*.md")
            transcript_count = self._count_files(self.data_dir / "transcripts", "*")

        if backup_dir is None:
            warnings.append("no previous data found to preserve")
        return RestoreReport(
            restored=True,
            file_counts={"wiki": wiki_count, "transcripts": transcript_count},
            index_rebuilt=False,
            warnings=warnings,
            previous_backup_dir=str(backup_dir) if backup_dir else None,
        )

    def _snapshot_db(self) -> Path:
        """Consistent mem.db copy via the SQLite backup API (WAL-safe)."""
        snapshot = Path(tempfile.mkstemp(suffix=".db")[1])
        source = sqlite3.connect(self.db_path)
        destination = sqlite3.connect(snapshot)
        try:
            source.backup(destination)
        finally:
            source.close()
            destination.close()
        return snapshot

    @staticmethod
    def _safe_extract(archive: tarfile.TarFile, staging: Path) -> None:
        for member in archive.getmembers():
            name = member.name
            if name.startswith("/") or ".." in Path(name).parts:
                raise BackupError(f"unsafe archive member: {name!r}")
            if member.issym() or member.islnk():
                raise BackupError(f"links are not allowed in archives: {name!r}")
            allowed = name in _ALLOWED_NAMES or name.startswith(_ALLOWED_PREFIXES)
            if not allowed:
                raise BackupError(f"unexpected archive member: {name!r}")
        archive.extractall(staging, filter="data")

    @staticmethod
    def _count_files(directory: Path, pattern: str) -> int:
        if not directory.is_dir():
            return 0
        return sum(1 for path in directory.rglob(pattern) if path.is_file())

    @staticmethod
    def _add_text(archive: tarfile.TarFile, name: str, text: str) -> None:
        import io

        info = tarfile.TarInfo(name=name)
        payload = text.encode("utf-8")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


def _version() -> str:
    from memex import __version__

    return __version__
