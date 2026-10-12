from pathlib import Path
import pytest
from synapse_daemon.hybrid_storage import scan_tree, propose_archives, migration_preview, disk_capacity

def test_inventory_excludes_live_dependency_dirs(tmp_path):
    (tmp_path / "src.py").write_text("hello")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "big.zip").write_bytes(b"x" * 100)
    result = scan_tree(tmp_path)
    assert result.file_count == 1
    assert result.bytes_total == 5
    assert result.excluded_directories == 1

def test_archive_candidates_and_preview_are_read_only(tmp_path):
    archive = tmp_path / "old.zip"
    archive.write_bytes(b"1234567890")
    (tmp_path / ".env").write_text("secret")
    (tmp_path / "src.py").write_text("code")
    preview = migration_preview(tmp_path, min_size_bytes=5)
    assert preview["mode"] == "dry_run"
    assert preview["potential_reclaim_bytes"] == 10
    assert preview["cloud_upload_performed"] is False
    assert preview["local_files_removed"] is False
    assert archive.exists()
    assert len(preview["candidates"]) == 1
    assert disk_capacity(tmp_path)["total"] > 0

def test_invalid_provider_rejected(tmp_path):
    with pytest.raises(ValueError):
        migration_preview(tmp_path, provider="unsupported")

def test_no_symlink_escape(tmp_path):
    target = tmp_path / "actual.zip"
    target.write_bytes(b"123456")
    symlink = tmp_path / "linked.zip"
    try:
        symlink.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not available")
    result = scan_tree(tmp_path)
    assert result.file_count == 1
    assert result.skipped_links == 1
