"""Stable installer release preflight is fail-closed."""
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("release_preflight",ROOT/"scripts"/"preflight_production_installer.py")
preflight=importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)

def test_valid_release_may_build():
    result=preflight.assess_release(
        free_bytes=8*1024**3,source_clean=True,publisher_configured=True,
        daemon_fresh=True,current_version="0.2.220",target_version="0.2.220",
        code_signing_cert=True)
    assert result["status"]=="READY_FOR_BUILD"

def test_unsigned_preview_never_becomes_trusted_stable():
    no_cert=preflight.assess_release(
        free_bytes=8*1024**3,source_clean=True,publisher_configured=True,
        daemon_fresh=True,current_version="0.2.220",target_version="0.2.220",
        code_signing_cert=False)
    assert "code-signing" in " ".join(no_cert["blockers"])
    preview=preflight.assess_release(
        free_bytes=8*1024**3,source_clean=True,publisher_configured=True,
        daemon_fresh=True,current_version="0.2.220",target_version="0.2.220",
        code_signing_cert=False,unsigned_preview=True)
    assert preview["unsigned_preview_only"] is True

def test_stale_or_dirty_or_low_disk_blocks_build():
    result=preflight.assess_release(
        free_bytes=2*1024**3,source_clean=False,publisher_configured=False,
        daemon_fresh=False,current_version="0.2.218",target_version="0.2.220",
        code_signing_cert=False)
    assert len(result["blockers"])==6
