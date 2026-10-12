from pathlib import Path

import pytest

from synapse_daemon.workspace_sync_core import (
    Outbox, SyncConflict, atomic_write_verified, checksum, file_manifest, safe_relative_path,
)


@pytest.mark.parametrize("bad", ["", "../secret", "a/../secret", "/absolute", "C:/absolute", "a\\b", "a//b", ".git/config", "nested/.git/config"])
def test_unsafe_path_rejected(bad):
    with pytest.raises(ValueError):
        safe_relative_path(bad)


def test_manifest_and_verified_atomic_write(tmp_path: Path):
    file = tmp_path / "code.py"
    file.write_bytes(b"old")
    manifest = file_manifest(tmp_path, "code.py")
    assert manifest.digest == checksum(b"old")
    assert atomic_write_verified(tmp_path, "code.py", b"new",
                                 expected_digest=manifest.digest,
                                 advertised_digest=checksum(b"new")) == checksum(b"new")
    assert file.read_bytes() == b"new"


def test_changed_file_is_preserved(tmp_path: Path):
    f = tmp_path / "code.py"
    f.write_bytes(b"other agent wrote")
    with pytest.raises(SyncConflict):
        atomic_write_verified(tmp_path, "code.py", b"new",
                              expected_digest=checksum(b"old"),
                              advertised_digest=checksum(b"new"))
    assert f.read_bytes() == b"other agent wrote"


def test_bad_transfer_preserves_file(tmp_path: Path):
    f = tmp_path / "code.py"
    f.write_bytes(b"original")
    with pytest.raises(ValueError):
        atomic_write_verified(tmp_path, "code.py", b"tampered",
                              expected_digest=checksum(b"original"),
                              advertised_digest=checksum(b"valid"))
    assert f.read_bytes() == b"original"


def test_outbox_persists_across_restart(tmp_path: Path):
    path = tmp_path / "outbox.db"
    queue = Outbox(path)
    digest = checksum(b"file")
    item = queue.enqueue("app", "desktop", "src/main.py", digest)
    assert len(Outbox(path).pending()) == 1
    queue.failed_attempt(item, now=100)
    assert Outbox(path).pending(now=100) == []
    assert len(Outbox(path).pending(now=110)) == 1
    assert not queue.acknowledge(item, checksum(b"different"))
    assert queue.acknowledge(item, digest)
    assert Outbox(path).pending(now=1000) == []


def test_symlink_escape_rejected(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"private")
    link = root / "link"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks is restricted")
    with pytest.raises(ValueError):
        file_manifest(root, "link")
