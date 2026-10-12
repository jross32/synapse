from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from synapse_daemon.release_pipeline import ReleasePipeline, REQUIRED_PROOFS, validate_proof


def source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    (root / "installer/premium-shell").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "installer/premium-shell/build-current-release.ps1").write_text("# fixture")
    (root / "scripts/publish-release-stage.cjs").write_text("// fixture")
    (root / "package.json").write_text(json.dumps({"version": "1.2.3"}))
    return root


def harness(tmp_path: Path, fail_stage: str | None = None):
    root = source(tmp_path)
    calls = []
    manager = None
    artifact = b"premium installer fixture"
    digest = hashlib.sha256(artifact).hexdigest()

    def execute(command, cwd, log):
        stage = log.stem
        calls.append(stage)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("a" * 64 if stage == "source-freeze" else "b" * 40 if stage == "git-source" else " M renderer/App.tsx" if stage == "git-status" else "PASS")
        if stage == "daemon-tests":
            (log.parent / "daemon-tests.xml").write_text('<testsuites><testsuite tests="7" failures="0" errors="0"/></testsuites>')
        if stage == fail_stage:
            return 1
        if stage == "publication-stage":
            staging = Path(command[-1])
            (staging / "releases").mkdir(parents=True)
            (staging / "releases/Synapse.Setup.1.2.3.exe").write_bytes(artifact)
            (staging / "publication-receipt.json").write_text(json.dumps({"version": "1.2.3", "sourceDigest": "a" * 64, "installerSha256": digest, "installerSize": len(artifact), "feedUrl": "https://download.whatapc.com/updates.json"}))
        return 0

    manager = ReleasePipeline(tmp_path / "data", root, execute)
    (root / "installer/release-python.local.json").write_text(json.dumps({"pythonExecutable": __import__("sys").executable}))
    manager._validate_trusted_signature = lambda *args: None
    return manager, calls, digest


def proof(version: str, digest: str, root: Path):
    checks = {}
    for key in REQUIRED_PROOFS:
        evidence = root / (key + ".txt")
        evidence.write_text("independent lifecycle fixture " + key)
        checks[key] = {"ok": True, "evidence": {"path": str(evidence), "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}}
        if key == "live_daemon_version":
            checks[key]["version"] = version
        if key == "windows_signature":
            checks[key].update(authenticode_status="Valid", thumbprint="a" * 40)
    return {"schema": "synapse.release-proof/v1", "version": version, "installer_sha256": digest, "checks": checks}


def test_ordered_native_execution_and_durable_source_evidence(tmp_path):
    manager, calls, digest = harness(tmp_path)
    row = manager.request("1.2.3", instruction="Use the laptop source and premium installer")
    manager._build(row["id"])
    final = manager.get(row["id"])
    assert calls == ["git-source", "version-sync", "git-status", "publisher", "python-environment", "source-freeze", "host-tests", "provenance-tests", "browser-tests", "native-publication-tests", "daemon-tests", "build-package", "updater-gate", "publication-stage"]
    assert final["status"] == "awaiting_verification"
    assert final["git_dirty"] is True
    assert final["git_revision"] == "b" * 40
    assert final["source_digest"] == "a" * 64
    assert final["artifact"]["installerSha256"] == digest
    assert [event["sequence"] for event in final["events"]] == list(range(1, len(final["events"]) + 1))
    reopened = ReleasePipeline(tmp_path / "data", manager.default_source, manager.executor)
    assert reopened.get(row["id"])["instruction"] == row["instruction"]


def test_publication_requires_exact_proof_and_explicit_intent(tmp_path):
    manager, calls, digest = harness(tmp_path)
    row = manager.request("1.2.3")
    manager._build(row["id"])
    with pytest.raises(ValueError, match="Explicit publication"):
        manager.publish(row["id"])
    invalid = proof("1.2.3", "0" * 64, tmp_path)
    evidence = tmp_path / "proof.json"
    evidence.write_text(json.dumps(invalid))
    with pytest.raises(ValueError, match="different artifact"):
        manager.attach_proof(row["id"], str(evidence))
    evidence.write_text(json.dumps(proof("1.2.3", digest, tmp_path)))
    assert manager.attach_proof(row["id"], str(evidence))["status"] == "verified"
    with pytest.raises(ValueError, match="Explicit publication"):
        manager.publish(row["id"])
    assert manager.request_publication(row["id"])["status"] == "ready_to_publish"
    blocked = manager.publish(row["id"])
    assert blocked["publication_blocker"] == "publisher_not_configured"
    assert "deployment" not in calls


def test_resume_skips_completed_stages_and_rejects_source_drift(tmp_path, monkeypatch):
    manager, calls, digest = harness(tmp_path, "host-tests")
    row = manager.request("1.2.3")
    manager._build(row["id"])
    assert manager.get(row["id"])["status"] == "failed"
    import synapse_daemon.release_pipeline as module
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="changed"))
    with pytest.raises(ValueError, match="changed since freeze"):
        manager.resume(row["id"])
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="a" * 64))
    class ImmediateThread:
        def __init__(self, target, args, **kwargs):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)
    monkeypatch.setattr(module.threading, "Thread", ImmediateThread)
    manager.resume(row["id"])
    assert calls.count("git-source") == 1
    assert calls.count("publisher") == 1
    assert calls.count("host-tests") == 2


def test_source_lock_blocks_overlapping_builds(tmp_path):
    manager, calls, digest = harness(tmp_path)
    first = manager.request("1.2.3")
    second = manager.request("1.2.3")
    manager._claim(first)
    with pytest.raises(ValueError, match="locked"):
        manager._claim(second)
    manager._release(first)
    manager._claim(second)
    manager._release(second)


def test_recovery_never_blindly_repeats_external_deployment(tmp_path):
    manager, calls, digest = harness(tmp_path)
    row = manager.request("1.2.3")
    manager._update(row["id"], status="running")
    manager._event(row["id"], "deployment", "running")
    reopened = ReleasePipeline(tmp_path / "data", manager.default_source, manager.executor)
    assert reopened.get(row["id"])["status"] == "interrupted"
    assert reopened.resume(row["id"])["status"] == "awaiting_live_verification"
    assert calls == []


def test_proof_checks_live_daemon_version_and_actual_evidence(tmp_path):
    value = proof("1.2.3", "a" * 64, tmp_path)
    value["checks"]["account_sync"]["evidence"] = {}
    with pytest.raises(ValueError, match="account_sync"):
        validate_proof(value, "1.2.3", "a" * 64)
    value = proof("1.2.3", "a" * 64, tmp_path)
    value["checks"]["live_daemon_version"]["version"] = "0.1.209"
    with pytest.raises(ValueError, match="daemon version"):
        validate_proof(value, "1.2.3", "a" * 64)


def test_native_pipeline_live_openapi_and_ai_discovery(tmp_path):
    from fastapi.testclient import TestClient
    from synapse_daemon.app import build_app
    from synapse_daemon.storage import Storage
    from synapse_daemon.ws import EventBus

    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    try:
        app = build_app(storage, EventBus())
        client = TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})
        with client:
            schema = client.get("/api/v1/openapi.json").json()
            context = client.get("/api/v1/ai/context").json()
            assert "/api/v1/release-pipeline" in schema["paths"]
            assert "/api/v1/release-pipeline/{run_id}/start" in schema["paths"]
            assert "/api/v1/release-pipeline/{run_id}/resume" in schema["paths"]
            assert "/api/v1/release-pipeline/{run_id}/proof" in schema["paths"]
            assert "/api/v1/release-pipeline/{run_id}/publish" in schema["paths"]
            assert "/api/v1/release-pipeline/{run_id}/verify-live" in schema["paths"]
            advertised = {item["path"] for item in context["endpoints_for_ai"]}
            assert "/api/v1/release-pipeline" in advertised
            assert "/api/v1/release-pipeline/{run_id}/start" in advertised
            assert "/api/v1/release-pipeline/{run_id}/resume" in advertised
            assert "/api/v1/release-pipeline/{run_id}/publish" in advertised
            assert client.get("/api/v1/release-pipeline").json()["execution"].startswith("local daemon")
    finally:
        storage.close()

def test_cross_daemon_data_dirs_share_source_lock(tmp_path):
    manager, calls, digest = harness(tmp_path)
    other = ReleasePipeline(tmp_path / "different-data", manager.default_source, manager.executor)
    first = manager.request("1.2.3")
    second = other.request("1.2.3")
    manager._claim(first)
    with pytest.raises(ValueError, match="locked"):
        other._claim(second)
    manager._release(first)


def test_full_daemon_junit_failure_blocks_build(tmp_path):
    manager, calls, digest = harness(tmp_path)
    original = manager.executor
    def bad_junit(command, cwd, log):
        result = original(command, cwd, log)
        if log.stem == "daemon-tests":
            (log.parent / "daemon-tests.xml").write_text('<testsuites><testsuite tests="7" failures="1" errors="0"/></testsuites>')
        return result
    manager.executor = bad_junit
    row = manager.request("1.2.3")
    manager._build(row["id"])
    assert manager.get(row["id"])["status"] == "failed"
    assert "build-package" not in calls


def test_unsigned_installer_cannot_pass_operator_receipt(tmp_path):
    manager, calls, digest = harness(tmp_path)
    row = manager.request("1.2.3")
    manager._build(row["id"])
    def deny(*args):
        raise ValueError("Windows trusted signature does not match")
    manager._validate_trusted_signature = deny
    evidence = tmp_path / "proof.json"
    evidence.write_text(json.dumps(proof("1.2.3", digest, tmp_path)))
    with pytest.raises(ValueError, match="trusted signature"):
        manager.attach_proof(row["id"], str(evidence))
    assert manager.get(row["id"])["status"] == "awaiting_verification"
