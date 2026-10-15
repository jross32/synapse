"""Safety regression tests for the non-destructive Downloads archive audit."""
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from disk_space_archive_audit import copy_verified, scan_downloads


def test_scan_only_direct_download_installers(tmp_path):
    source, dest = tmp_path / "Downloads", tmp_path / "USB"
    source.mkdir()
    dest.mkdir()
    (source / "legitimate-installer.exe").write_bytes(b"x" * (25 * 1024 * 1024))
    (source / "private-data.json").write_bytes(b"x" * (25 * 1024 * 1024))
    (source / "repository").mkdir()
    (source / "repository" / "code.zip").write_bytes(b"x" * (25 * 1024 * 1024))
    result = scan_downloads(source, dest)
    assert [x["name"] for x in result["candidates"]] == ["legitimate-installer.exe"]
    assert (source / "legitimate-installer.exe").exists()


def test_copy_verifies_hash_and_never_deletes_original(tmp_path):
    source, dest = tmp_path / "Downloads", tmp_path / "USB"
    source.mkdir()
    dest.mkdir()
    installer = source / "installer.exe"
    installer.write_bytes(b"example installer content" * 1300000)
    receipt = copy_verified(installer, dest, source)
    assert receipt["copy_verified"] is True
    assert receipt["source_preserved"] is True
    assert installer.read_bytes() == (dest / "installer.exe").read_bytes()
    with pytest.raises(FileExistsError):
        copy_verified(installer, dest, source)


def test_refuses_non_installer_files(tmp_path):
    source, dest = tmp_path / "Downloads", tmp_path / "USB"
    source.mkdir()
    dest.mkdir()
    document = source / "account.db"
    document.write_bytes(b"x" * (25 * 1024 * 1024))
    with pytest.raises(ValueError):
        copy_verified(document, dest, source)


def test_refuses_destination_inside_source(tmp_path):
    source = tmp_path / "Downloads"
    source.mkdir()
    sub = source / "USB"
    sub.mkdir()
    with pytest.raises(ValueError):
        scan_downloads(source, sub)
