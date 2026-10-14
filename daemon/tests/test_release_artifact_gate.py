"""Release gate refuses stale or unverified Windows installer metadata."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release_artifact_gate.py"
spec = importlib.util.spec_from_file_location("release_artifact_gate", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
COMMIT = "a" * 40


@pytest.fixture
def release(tmp_path):
    artifact = tmp_path / "Synapse Setup 0.2.219.exe"
    artifact.write_bytes(b"synthetic-installer-only-for-tests" * 40000)
    digest = hashlib.sha512(artifact.read_bytes()).digest()
    latest = tmp_path / "latest.yml"
    latest.write_text(
        f"version: 0.2.219\nfiles:\n  - url: {artifact.name}\n"
        f"    sha512: {base64.b64encode(digest).decode()}\n"
        f"    size: {artifact.stat().st_size}\n"
        f"path: {artifact.name}\n"
        f"sha512: {base64.b64encode(digest).decode()}\n", encoding="utf-8",
    )
    proof = tmp_path / "proof.json"
    proof.write_text(json.dumps({
        "status": "verified", "version": "0.2.219", "source_commit": COMMIT,
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "account_preserved": True, "device_identity_preserved": True,
        "mcp_connector_url_preserved": True,
    }), encoding="utf-8")
    site = tmp_path / "releases.json"
    site.write_text(json.dumps({
        "version": "0.2.219", "artifacts": [{
            "platform": "windows", "status": "ready",
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "size_bytes": artifact.stat().st_size, "url": "/releases/" + artifact.name,
            "source_commit": COMMIT,
        }],
    }), encoding="utf-8")
    return artifact, latest, proof, site


def check(release, **overrides):
    artifact, latest, proof, site = release
    return gate.verify_windows_release(
        artifact, latest, proof,
        expected_version="0.2.219",
        expected_commit=overrides.get("commit", COMMIT),
        website_metadata=site,
    )


def test_verified_release_passes(release):
    assert check(release)["status"] == "verified"


def test_old_commit_cannot_be_rebranded_as_new_build(release):
    with pytest.raises(gate.ReleaseGateError, match="source commit"):
        check(release, commit="b" * 40)


def test_changed_installer_bytes_are_rejected(release):
    artifact = release[0]
    artifact.write_bytes(artifact.read_bytes() + b"evil")
    with pytest.raises(gate.ReleaseGateError, match="size mismatch"):
        check(release)


def test_changed_update_filename_is_rejected(release):
    latest = release[1]
    latest.write_text(latest.read_text().replace("path: Synapse Setup", "path: Synapse-Setup"))
    with pytest.raises(gate.ReleaseGateError, match="filename"):
        check(release)


def test_missing_identity_preservation_proof_is_rejected(release):
    proof = release[2]
    evidence = json.loads(proof.read_text())
    evidence["device_identity_preserved"] = False
    proof.write_text(json.dumps(evidence))
    with pytest.raises(gate.ReleaseGateError, match="identity preservation"):
        check(release)


def test_website_different_installer_checksum_is_rejected(release):
    site = release[3]
    metadata = json.loads(site.read_text())
    metadata["artifacts"][0]["sha256"] = "f" * 64
    site.write_text(json.dumps(metadata))
    with pytest.raises(gate.ReleaseGateError, match="checksum"):
        check(release)


def test_nested_update_files_url_must_match_installer(release):
    latest = release[1]
    text = latest.read_text()
    latest.write_text(text.replace("- url: Synapse Setup", "- url: Old Synapse Setup"))
    with pytest.raises(gate.ReleaseGateError, match="files URL"):
        check(release)


def test_unsigned_preview_is_not_stable_download(release):
    site = release[3]
    site.write_text(json.dumps({
        "version": "0.1.217", "artifacts": [{
            "platform": "windows", "status": "ready",
            "url": "/releases/old.exe",
        }],
        "previews": [{
            "version": "0.2.219", "status": "available-unsigned-preview",
            "signed": False, "full_install_e2e_verified": False,
        }],
    }))
    with pytest.raises(gate.ReleaseGateError, match="Website release version"):
        check(release)


def test_website_source_commit_must_match_verified_installer(release):
    site = release[3]
    meta = json.loads(site.read_text())
    meta["artifacts"][0]["source_commit"] = "b" * 40
    site.write_text(json.dumps(meta))
    with pytest.raises(gate.ReleaseGateError, match="provenance"):
        check(release)
