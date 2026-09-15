import io
import tarfile
from pathlib import Path

import pytest

from memex.domain.errors import BackupError
from memex.domain.models import (
    TurnStreamEntry,
    WriteInput,
)
from memex.infrastructure.backup import BackupRestore


def test_turn_entry_rejects_bad_role() -> None:
    with pytest.raises(ValueError, match="role"):
        TurnStreamEntry(role="system", content="x", turn=1, ts="")


def test_turn_entry_rejects_zero_turn() -> None:
    with pytest.raises(ValueError, match="turn"):
        TurnStreamEntry(role="user", content="x", turn=0, ts="")


def test_turn_entry_rejects_tool_fields_on_user() -> None:
    with pytest.raises(ValueError, match="tool_name"):
        TurnStreamEntry(role="user", content="x", turn=1, ts="", tool_name="shell")


def test_turn_entry_rejects_bad_ts() -> None:
    with pytest.raises(ValueError, match="ts"):
        TurnStreamEntry(role="user", content="x", turn=1, ts="yesterday")


def test_turn_entry_from_dict_requires_fields() -> None:
    with pytest.raises(ValueError, match="required field"):
        TurnStreamEntry.from_dict({"role": "user"})
    with pytest.raises(ValueError, match="must be"):
        TurnStreamEntry.from_dict({"role": "user", "content": "x", "turn": "1"})
    with pytest.raises(ValueError, match="must be a string"):
        TurnStreamEntry.from_dict({"role": "user", "content": "x", "turn": 1, "ts": 5})


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "folder"},
        {"title": "  "},
        {"importance": 1.5},
        {"importance": -0.1},
        {"tags": ["", "dup"]},
        {"tags": ["a", "a"]},
        {"links": ["ok", "ok"]},
        {"links": [" "]},
        {"type": "episode"},  # episode requires session_id
        {"type": "entity", "session_id": " "},
        {"expires_at": "tomorrow"},
        {"valid_from": "2026-13-99T00:00:00Z"},
    ],
)
def test_write_input_validation(overrides: dict[str, object]) -> None:
    fields: dict[str, object] = {"type": "entity", "title": "t", "body": "b"}
    fields.update(overrides)
    with pytest.raises(ValueError):
        WriteInput(**fields)  # type: ignore[arg-type]


def test_consolidate_input_validation() -> None:
    from memex.domain.models import ConsolidateInput

    with pytest.raises(ValueError, match="mode"):
        ConsolidateInput(mode="partial")
    with pytest.raises(ValueError, match="max_episodes"):
        ConsolidateInput(max_episodes=0)


def test_ingest_input_validation() -> None:
    from memex.domain.models import IngestTranscriptInput

    with pytest.raises(ValueError, match="session_id"):
        IngestTranscriptInput(session_id="../bad", turns=[])
    with pytest.raises(ValueError, match="session_id"):
        IngestTranscriptInput(session_id=".hidden", turns=[])


def make_archive(
    path: Path, members: dict[str, bytes], manifest: bytes | None = b'{"version": "1.0"}'
) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        if manifest is not None:
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(manifest)
            archive.addfile(info, io.BytesIO(manifest))


def test_verify_rejects_missing_manifest(tmp_path: Path) -> None:
    archive_path = tmp_path / "bad.tar.gz"
    make_archive(archive_path, {"wiki/a.md": b"x"}, manifest=None)
    assert BackupRestore(tmp_path, tmp_path / "mem.db").verify(archive_path) is False


def test_verify_rejects_wrong_version(tmp_path: Path) -> None:
    archive_path = tmp_path / "bad.tar.gz"
    make_archive(archive_path, {}, manifest=b'{"version": "9.9"}')
    assert BackupRestore(tmp_path, tmp_path / "mem.db").verify(archive_path) is False


def test_verify_rejects_garbage(tmp_path: Path) -> None:
    archive_path = tmp_path / "not-tar.gz"
    archive_path.write_bytes(b"garbage")
    assert BackupRestore(tmp_path, tmp_path / "mem.db").verify(archive_path) is False


def test_restore_rejects_missing_archive(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="archive not found"):
        BackupRestore(tmp_path, tmp_path / "mem.db").restore(tmp_path / "nope.tar.gz")


def test_restore_rejects_traversal_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "evil.tar.gz"
    make_archive(archive_path, {"wiki/../../escape.md": b"x"})
    with pytest.raises(BackupError, match="unsafe archive member"):
        BackupRestore(tmp_path, tmp_path / "mem.db").restore(archive_path)


def test_restore_rejects_symlink_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "evil.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo(name="wiki/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        archive.addfile(info)
        manifest = b'{"version": "1.0"}'
        minfo = tarfile.TarInfo(name="manifest.json")
        minfo.size = len(manifest)
        archive.addfile(minfo, io.BytesIO(manifest))
    with pytest.raises(BackupError, match="links are not allowed"):
        BackupRestore(tmp_path, tmp_path / "mem.db").restore(archive_path)


def test_restore_rejects_unexpected_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "odd.tar.gz"
    make_archive(archive_path, {"secrets.txt": b"x"})
    with pytest.raises(BackupError, match="unexpected archive member"):
        BackupRestore(tmp_path, tmp_path / "mem.db").restore(archive_path)


def test_backup_failure_wrapped(tmp_path: Path) -> None:
    restore = BackupRestore(tmp_path, tmp_path / "mem.db")
    unwritable = tmp_path / "locked" / "out.tar.gz"
    unwritable.parent.mkdir(parents=True)
    unwritable.parent.chmod(0o500)
    try:
        with pytest.raises(BackupError, match="backup failed"):
            restore.backup(unwritable)
    finally:
        unwritable.parent.chmod(0o700)
