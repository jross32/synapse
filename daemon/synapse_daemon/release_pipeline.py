"""Durable, source-backed Synapse release requests and ordered build/publication runs."""
from __future__ import annotations

import json
import hashlib
import urllib.request
import urllib.parse
import os
import re
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .subprocess_utils import headless_creationflags

REQUIRED_PROOFS = ("windows_clean_install", "windows_upgrade", "windows_repair", "windows_uninstall", "windows_rollback", "background_startup", "account_sign_up", "account_sign_in", "account_sync", "two_device_sync", "live_daemon_version", "windows_signature")
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_proof(proof: dict[str, Any], version: str, artifact_sha256: str) -> None:
    if proof.get("schema") != "synapse.release-proof/v1" or proof.get("version") != version:
        raise ValueError("Installer proof schema/version does not match this release")
    if proof.get("installer_sha256") != artifact_sha256:
        raise ValueError("Installer proof belongs to different artifact bytes")
    checks = proof.get("checks", {})
    for key in REQUIRED_PROOFS:
        check = checks.get(key, {})
        evidence = check.get("evidence", {})
        if check.get("ok") is not True or not isinstance(evidence, dict) or not isinstance(evidence.get("path"), str) or not re.fullmatch(r"[a-f0-9]{64}", str(evidence.get("sha256", ""))):
            raise ValueError("Missing real lifecycle proof: " + key)
        path = Path(evidence["path"])
        if not path.is_file() or path.stat().st_size == 0 or _sha256(path) != evidence["sha256"]:
            raise ValueError("Lifecycle evidence file/hash mismatch: " + key)
    if checks["windows_signature"].get("authenticode_status") != "Valid":
        raise ValueError("Trusted Windows signature proof is missing")
    if checks["live_daemon_version"].get("version") != version:
        raise ValueError("Live daemon version differs from the requested release")


class ReleasePipeline:
    """The daemon owns this ledger; execution is local and independent of ChatGPT."""
    def __init__(self, data_dir: Path, default_source: Path, executor: Callable[..., int] | None = None) -> None:
        self.directory = Path(data_dir) / "release-pipeline"
        self.default_source = Path(default_source)
        self.executor = executor or self._execute
        self.active: set[str] = set()
        self.on_change: Callable[[dict[str, Any]], None] | None = None
        self.directory.mkdir(parents=True, exist_ok=True)
        # A daemon restart cannot imply that a detached build completed.
        for file in self.directory.glob("*.json"):
            if file.name == "policy.json":
                continue
            row = json.loads(file.read_text(encoding="utf-8"))
            if row.get("status") == "running":
                row["status"] = "interrupted"
                row["events"].append({"sequence": len(row["events"]) + 1, "time": _now(), "stage": "recovery", "status": "interrupted", "message": "Daemon restarted; inspect artifacts and resume explicitly."})
                _save(file, row)

    def _notify(self, row: dict[str, Any]) -> None:
        if self.on_change:
            self.on_change({"id": row["id"], "version": row["version"], "status": row["status"], "event_count": len(row["events"])})

    def _path(self, run_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise KeyError(run_id)
        return self.directory / (run_id + ".json")

    def get(self, run_id: str) -> dict[str, Any]:
        with _LOCK:
            path = self._path(run_id)
            if not path.exists():
                raise KeyError(run_id)
            return json.loads(path.read_text(encoding="utf-8"))

    def list(self) -> list[dict[str, Any]]:
        with _LOCK:
            rows = [json.loads(file.read_text(encoding="utf-8")) for file in self.directory.glob("*.json") if file.name != "policy.json"]
            return sorted(rows, key=lambda row: row["created_at"], reverse=True)

    def request(self, version: str, source_root: str | None = None, publish_requested: bool = False, instruction: str = "") -> dict[str, Any]:
        if version != "next" and not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ValueError("Release version must be major.minor.patch or next")
        policy_path = self.directory / "policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.is_file() else {}
        remembered = policy.get("source_root")
        if not source_root and not remembered:
            prior = self.list()
            remembered = prior[0]["source_root"] if prior else None
        source = Path(source_root or remembered or self.default_source).resolve()
        if not (source / "installer/premium-shell/build-current-release.ps1").is_file():
            raise ValueError("Selected source tree does not contain the unified release pipeline")
        package = json.loads((source / "package.json").read_text(encoding="utf-8-sig"))
        source_version = package.get("version")
        if not isinstance(source_version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", source_version):
            raise ValueError("Source version metadata is invalid")
        if version == "next":
            major, minor, patch = map(int, source_version.split("."))
            version = f"{major}.{minor}.{patch + 1}"
        if tuple(map(int, version.split("."))) < tuple(map(int, source_version.split("."))):
            raise ValueError("Release version cannot downgrade the current source")
        with _LOCK:
            for row in self.list():
                if os.path.normcase(row["source_root"]) == os.path.normcase(str(source)) and row["status"] == "running":
                    raise ValueError("Another release is already building this source tree")
            run_id = uuid.uuid4().hex
            row = {"schema": "synapse.release-run/v1", "id": run_id, "created_at": _now(), "version": version, "source_version": source_version, "source_root": str(source), "publish_requested": publish_requested, "instruction": instruction[:4000], "status": "requested", "events": [], "proof": None, "artifact": None}
            _save(self._path(run_id), row)
            return row

    def _event(self, run_id: str, stage: str, status: str, **details: Any) -> None:
        with _LOCK:
            row = self.get(run_id)
            row["events"].append({"sequence": len(row["events"]) + 1, "time": _now(), "stage": stage, "status": status, **details})
            _save(self._path(run_id), row)
            self._notify(row)

    def _update(self, run_id: str, **updates: Any) -> dict[str, Any]:
        with _LOCK:
            row = self.get(run_id)
            row.update(updates)
            _save(self._path(run_id), row)
            self._notify(row)
            return row

    def plan(self, run_id: str) -> list[dict[str, Any]]:
        row = self.get(run_id)
        staging = self.directory / "staging" / run_id
        return [
            {"stage": "git-source", "command": ["git", "rev-parse", "HEAD"]},
            {"stage": "version-sync", "command": ["node", "scripts/sync-release-version.cjs", row["version"], "--expected", row["source_version"]]},
            {"stage": "git-status", "command": ["git", "status", "--porcelain"]},
            {"stage": "publisher", "command": ["node", "scripts/prepare-release-publisher.cjs"]},
            {"stage": "python-environment", "command": ["node", "scripts/release-python.cjs", "--ensure"]},
            {"stage": "source-freeze", "command": ["node", "-e", "console.log(require('./installer/premium-shell/build-provenance.cjs').sourceDigest())"]},
            {"stage": "host-tests", "command": ["node", "installer/premium-shell/test-host-release.cjs"]},
            {"stage": "provenance-tests", "command": ["node", "installer/premium-shell/test-release-provenance.cjs"]},
            {"stage": "browser-tests", "command": ["node", "installer/premium-shell/test-native-gate.cjs"]},
            {"stage": "native-publication-tests", "command": ["node", "scripts/test-native-publication.cjs"]},
            {"stage": "daemon-tests", "command": ["<release-python>", "scripts/run-release-tests.py", "--junit", str(self.directory / "logs" / run_id / "daemon-tests.xml")]},
            {"stage": "build-package", "command": ["powershell.exe", "-NoProfile", "-File", "installer/premium-shell/build-current-release.ps1", "-Version", row["version"]]},
            {"stage": "updater-gate", "command": ["node", "scripts/preflight-desktop-updater.cjs"]},
            {"stage": "publication-stage", "command": ["node", "scripts/stage-release-publication.cjs", row["version"], str(staging)]},
        ]

    def _execute(self, command: list[str], cwd: Path, log_path: Path) -> int:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(cwd / "daemon")
        if (cwd / "installer/release-python.local.json").is_file() or environment.get("SYNAPSE_RELEASE_PYTHON"):
            environment["SYNAPSE_RELEASE_PYTHON"] = str(self._release_python(cwd))
        environment["SYNAPSE_PLAYWRIGHT_MODULE"] = str(cwd / "node_modules/playwright")
        child = subprocess.Popen(command, cwd=str(cwd), env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", creationflags=headless_creationflags())
        run_id = log_path.parent.name
        try:
            row = self.get(run_id)
            lock = self._lock_path(row["source_root"])
            if lock.exists():
                owner = json.loads(lock.read_text(encoding="utf-8"))
                owner["child_pid"] = child.pid
                import psutil
                owner["child_pid_created_at"] = psutil.Process(child.pid).create_time()
                _save(lock, owner)
            self._update(run_id, active_pid=child.pid, active_command=command)
        except KeyError:
            pass
        try:
            stdout, stderr = child.communicate(timeout=7200)
        except subprocess.TimeoutExpired:
            import psutil
            process = psutil.Process(child.pid)
            for descendant in process.children(recursive=True):
                descendant.terminate()
            process.terminate()
            stdout, stderr = child.communicate(timeout=20)
            stderr += "\nRelease stage exceeded its two-hour execution limit."
        output = (stdout + "\n" + stderr)[-1024 * 1024:]
        # Known secret environment values never enter a persisted build/deploy log.
        for name, value in environment.items():
            if len(value) > 6 and re.search(r"token|secret|password|private|credential|api_key", name, re.I):
                output = output.replace(value, "[redacted]")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output, encoding="utf-8")
        self._update(run_id, active_pid=None, active_command=None)
        return child.returncode

    def _release_python(self, source: Path) -> Path:
        configured = os.environ.get("SYNAPSE_RELEASE_PYTHON")
        if not configured:
            local = source / "installer/release-python.local.json"
            if local.is_file():
                configured = json.loads(local.read_text(encoding="utf-8-sig")).get("pythonExecutable")
        if not configured or not Path(configured).is_file():
            raise ValueError("Prepare the pinned release Python environment; shared venv fallback is forbidden")
        return Path(configured).resolve()

    def _lock_path(self, source: str) -> Path:
        # Source-local ownership protects the same checkout across daemon data dirs.
        return Path(os.path.normcase(str(Path(source).resolve()))) / ".synapse-release-lock.json"

    def _claim(self, row: dict[str, Any]) -> None:
        lock = self._lock_path(row["source_root"])
        lock.parent.mkdir(parents=True, exist_ok=True)
        if lock.exists():
            owner = json.loads(lock.read_text(encoding="utf-8"))
            import psutil
            for key in ("owner_pid", "child_pid"):
                pid = owner.get(key)
                if isinstance(pid, int) and psutil.pid_exists(pid):
                    try:
                        if psutil.Process(pid).create_time() == owner.get(key + "_created_at"):
                            raise ValueError("Source is locked by an active release/build process")
                    except psutil.AccessDenied:
                        raise ValueError("Source lock process identity cannot be checked safely")
            lock.unlink()
        try:
            with lock.open("x", encoding="utf-8") as stream:
                import psutil
                json.dump({"run_id": row["id"], "source_root": os.path.normcase(str(Path(row["source_root"]).resolve())), "owner_pid": os.getpid(), "owner_pid_created_at": psutil.Process(os.getpid()).create_time(), "child_pid": None}, stream)
        except FileExistsError:
            raise ValueError("Another release claimed this source tree")

    def _release(self, row: dict[str, Any]) -> None:
        lock = self._lock_path(row["source_root"])
        if lock.exists():
            owner = json.loads(lock.read_text(encoding="utf-8"))
            if owner.get("run_id") == row["id"]:
                lock.unlink()

    def resume(self, run_id: str) -> dict[str, Any]:
        with _LOCK:
            row = self.get(run_id)
            if row["status"] == "awaiting_live_verification":
                return row  # Never repeat a deployment whose external result is unknown.
            if row["status"] in {"verified", "ready_to_publish", "awaiting_verification", "published"}:
                return row
            if row["status"] not in {"failed", "interrupted"}:
                raise ValueError("This run cannot be resumed while active")
            if any(event["stage"] == "deployment" and event["status"] == "running" for event in row["events"]):
                return self._update(run_id, status="awaiting_live_verification")
            source = Path(row["source_root"])
            if row.get("source_digest"):
                result = subprocess.run(["node", "-e", "console.log(require('./installer/premium-shell/build-provenance.cjs').sourceDigest())"], cwd=source, capture_output=True, text=True, timeout=30, creationflags=headless_creationflags())
                if result.returncode or result.stdout.strip() != row["source_digest"]:
                    raise ValueError("Release source changed since freeze; request a fresh run")
            self._claim(row)
            self._update(run_id, status="running")
            self.active.add(run_id)
            threading.Thread(target=self._build, args=(run_id,), daemon=True).start()
            return self.get(run_id)

    def start(self, run_id: str) -> dict[str, Any]:
        with _LOCK:
            row = self.get(run_id)
            if row["status"] != "requested":
                raise ValueError("Only a new requested run can build; interrupted runs require a fresh request")
            if any(other["status"] == "running" and os.path.normcase(other["source_root"]) == os.path.normcase(row["source_root"]) for other in self.list()):
                raise ValueError("Another release is building the same source tree")
            self._claim(row)
            self._update(run_id, status="running")
            self.active.add(run_id)
            threading.Thread(target=self._build, args=(run_id,), name="synapse-release-" + run_id[:8], daemon=True).start()
            return self.get(run_id)

    def _build(self, run_id: str) -> None:
        try:
            row = self.get(run_id)
            source = Path(row["source_root"])
            completed = set()
            for event in row["events"]:
                if event["status"] != "passed" or event["stage"] == "daemon-test-evidence":
                    continue
                if event.get("source_digest") and event["source_digest"] != row.get("source_digest"):
                    raise ValueError("Completed stage belongs to different source evidence")
                if event.get("log_sha256"):
                    log = Path(event["log_path"])
                    if not log.is_file() or _sha256(log) != event["log_sha256"]:
                        raise ValueError("Completed stage log evidence changed")
                if event["stage"] == "daemon-tests":
                    junit = self.directory / "logs" / run_id / "daemon-tests.xml"
                    if not event.get("junit_sha256") or not junit.is_file() or _sha256(junit) != event["junit_sha256"]:
                        raise ValueError("Completed daemon suite evidence is missing or changed")
                completed.add(event["stage"])
            for step in self.plan(run_id):
                if step["stage"] in completed:
                    continue
                if step["stage"] == "publication-stage" and (self.directory / "staging" / run_id / "publication-receipt.json").exists():
                    receipt = json.loads((self.directory / "staging" / run_id / "publication-receipt.json").read_text(encoding="utf-8"))
                    installer = self.directory / "staging" / run_id / "releases" / ("Synapse.Setup." + row["version"] + ".exe")
                    if receipt.get("sourceDigest") != self.get(run_id).get("source_digest") or _sha256(installer) != receipt.get("installerSha256"):
                        raise ValueError("Interrupted staged publication is inconsistent")
                    self._event(run_id, step["stage"], "passed", recovered=True)
                    continue
                if step["stage"] == "daemon-tests":
                    step["command"][0] = str(self._release_python(source))
                self._event(run_id, step["stage"], "running", command=step["command"])
                log = self.directory / "logs" / run_id / (step["stage"] + ".log")
                exit_code = self.executor(step["command"], source, log)
                if exit_code:
                    self._event(run_id, step["stage"], "failed", exit_code=exit_code, log_path=str(log))
                    self._update(run_id, status="failed")
                    return
                stage_evidence = {}
                if exit_code == 0 and step["stage"] == "daemon-tests":
                    import xml.etree.ElementTree as ET
                    junit = self.directory / "logs" / run_id / "daemon-tests.xml"
                    suites = ET.parse(junit).getroot()
                    groups = list(suites) if suites.tag == "testsuites" else [suites]
                    tests = sum(int(group.get("tests", "0")) for group in groups)
                    failures = sum(int(group.get("failures", "0")) + int(group.get("errors", "0")) for group in groups)
                    if tests <= 0 or failures:
                        raise ValueError("Full daemon suite did not produce green non-empty JUnit evidence")
                    stage_evidence = {"tests": tests, "junit_sha256": _sha256(junit)}
                if exit_code == 0 and step["stage"] in {"git-source", "git-status", "source-freeze"}:
                    result = log.read_text(encoding="utf-8").strip() if log.exists() else ""
                    if step["stage"] == "source-freeze":
                        if not re.fullmatch(r"[a-f0-9]{64}", result):
                            raise ValueError("Source digest evidence is missing")
                        self._update(run_id, source_digest=result)
                    elif step["stage"] == "git-source":
                        self._update(run_id, git_revision=result)
                    else:
                        self._update(run_id, git_dirty=bool(result), git_status_log=str(log))
                self._event(run_id, step["stage"], "passed", exit_code=0, log_path=str(log), log_sha256=_sha256(log), source_digest=self.get(run_id).get("source_digest"), **stage_evidence)
            receipt = json.loads((self.directory / "staging" / run_id / "publication-receipt.json").read_text(encoding="utf-8"))
            self._update(run_id, artifact=receipt, status="awaiting_verification")
            self._event(run_id, "lifecycle-proof", "blocked", message="Real Windows/account/two-device proof is required. Stable downloads remain unchanged.")
        except Exception as error:
            self._event(run_id, "pipeline", "failed", message=type(error).__name__ + ": " + str(error)[:1000])
            self._update(run_id, status="failed")
        finally:
            self.active.discard(run_id)
            self._release(self.get(run_id))

    def _validate_trusted_signature(self, artifact: Path, proof: dict[str, Any]) -> None:
        if os.name != "nt":
            raise ValueError("Verify Windows Authenticode on a Windows release worker")
        script = "$ErrorActionPreference='Stop'; $signature=Get-AuthenticodeSignature -LiteralPath $env:SYNAPSE_RELEASE_ARTIFACT; @{status=[string]$signature.Status; thumbprint=$signature.SignerCertificate.Thumbprint} | ConvertTo-Json -Compress"
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                env={**os.environ, "SYNAPSE_RELEASE_ARTIFACT": str(artifact)},
                                capture_output=True, text=True, timeout=30, creationflags=headless_creationflags())
        if result.returncode:
            raise ValueError("Windows signature verification failed")
        signature = json.loads(result.stdout)
        expected = proof["checks"]["windows_signature"].get("thumbprint")
        if signature.get("status") != "Valid" or not expected or signature.get("thumbprint", "").lower() != expected.lower():
            raise ValueError("Windows trusted signature does not match the recorded publisher certificate")

    def attach_proof(self, run_id: str, evidence_path: str) -> dict[str, Any]:
        with _LOCK:
            row = self.get(run_id)
            if row["status"] != "awaiting_verification" or not row["artifact"]:
                raise ValueError("Build the artifact before attaching lifecycle proof")
            path = Path(evidence_path).resolve()
            if not path.is_file() or path.stat().st_size > 1024 * 1024:
                raise ValueError("Lifecycle proof must be a local JSON receipt below 1 MB")
            proof = json.loads(path.read_text(encoding="utf-8-sig"))
            validate_proof(proof, row["version"], row["artifact"]["installerSha256"])
            artifact = self.directory / "staging" / run_id / "releases" / ("Synapse.Setup." + row["version"] + ".exe")
            if _sha256(artifact) != row["artifact"]["installerSha256"]:
                raise ValueError("Staged installer changed before lifecycle verification")
            self._validate_trusted_signature(artifact, proof)
            _save(self.directory / "staging" / run_id / "lifecycle-proof.json", proof)
            self._event(run_id, "lifecycle-proof", "passed", evidence_path=str(path), evidence_sha256=_sha256(path), evidence_kind="operator_recorded")
            return self._update(run_id, proof=proof, status="ready_to_publish" if row["publish_requested"] else "verified")

    def publisher_configuration(self) -> dict[str, Any]:
        policy_path = self.directory / "policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.is_file() else {}
        return {key: policy.get(key) for key in ("source_root", "site_root")}

    def configure_publisher(self, source_root: str, site_root: str) -> dict[str, Any]:
        source = Path(source_root).resolve()
        site = Path(site_root).resolve()
        if not (source / "scripts/publish-release-stage.cjs").is_file() or not (site / "index.html").is_file() or not (site / "app.js").is_file():
            raise ValueError("Publisher needs an existing reviewed source tree and download-site root")
        policy = {"schema": "synapse.release-policy/v1", "source_root": str(source), "site_root": str(site),
                  "deploy_command": ["node", str(source / "scripts/publish-release-stage.cjs"), "{staging}", str(site), "--publish-github"],
                  "publication_requires_proof": True, "publication_requires_explicit_request": True}
        with _LOCK:
            _save(self.directory / "policy.json", policy)
        return {key: value for key, value in policy.items() if key != "deploy_command"}

    def request_publication(self, run_id: str) -> dict[str, Any]:
        with _LOCK:
            row = self.get(run_id)
            if row["status"] not in {"verified", "ready_to_publish"} or not row["proof"]:
                raise ValueError("Publication requires verified installer lifecycle proof")
            self._event(run_id, "publication-authority", "requested", message="Explicit publication requested through Synapse")
            return self._update(run_id, publish_requested=True, status="ready_to_publish")

    def publish(self, run_id: str) -> dict[str, Any]:
        with _LOCK:
            row = self.get(run_id)
            if row["status"] != "ready_to_publish" or row["publish_requested"] is not True or not row["proof"]:
                raise ValueError("Explicit publication request and lifecycle proof are required")
            policy_path = self.directory / "policy.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.is_file() else {}
            if policy.get("source_root") and os.path.normcase(str(Path(policy["source_root"]).resolve())) != os.path.normcase(str(Path(row["source_root"]).resolve())):
                raise ValueError("Publisher source tree differs from this run; configure the matching reviewed source")
            command = policy.get("deploy_command")
            if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
                self._event(run_id, "deployment", "blocked", message="Configure a local publisher deploy_command in release-pipeline/policy.json. No external deployment occurred.")
                return self._update(run_id, status="ready_to_publish", publication_blocker="publisher_not_configured")
            self._claim(row)
            self._update(run_id, status="running")
            self.active.add(run_id)
            threading.Thread(target=self._deploy, args=(run_id, command), name="synapse-publish-" + run_id[:8], daemon=True).start()
            return self.get(run_id)

    def _deploy(self, run_id: str, command: list[str]) -> None:
        try:
            row = self.get(run_id)
            staging = self.directory / "staging" / run_id
            artifact_path = staging / "releases" / ("Synapse.Setup." + row["version"] + ".exe")
            validate_proof(row["proof"], row["version"], _sha256(artifact_path))
            self._validate_trusted_signature(artifact_path, row["proof"])
            # Placeholder is one argument; no shell interpolation or command string evaluation.
            actual_command = [part.replace("{staging}", str(staging)).replace("{version}", row["version"]) for part in command]
            self._event(run_id, "deployment", "running")
            exit_code = self.executor(actual_command, Path(row["source_root"]), self.directory / "logs" / run_id / "deployment.log")
            self._event(run_id, "deployment", "passed" if exit_code == 0 else "failed", exit_code=exit_code)
            # A deploy CLI exit alone is not proof of publicly served bytes.
            self._update(run_id, status="awaiting_live_verification" if exit_code == 0 else "failed")
        except Exception as error:
            self._event(run_id, "deployment", "failed", message=type(error).__name__ + ": " + str(error)[:1000])
            self._update(run_id, status="failed")
        finally:
            self.active.discard(run_id)
            self._release(self.get(run_id))

    def verify_live(self, run_id: str) -> dict[str, Any]:
        row = self.get(run_id)
        if row["status"] != "awaiting_live_verification" or not row["artifact"] or not row["proof"]:
            raise ValueError("Deploy with explicit publication authority before live verification")
        staging = self.directory / "staging" / run_id
        expected_update = json.loads((staging / "updates.json").read_text(encoding="utf-8"))
        expected_site = json.loads((staging / "releases.json").read_text(encoding="utf-8"))
        feed_url = row["artifact"]["feedUrl"]

        class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, file, code, message, headers, new_url):  # noqa: ANN001
                parsed = urllib.parse.urlparse(new_url)
                if parsed.scheme != "https" or parsed.username or parsed.password:
                    raise ValueError("Live release verification rejects non-HTTPS redirects")
                return super().redirect_request(request, file, code, message, headers, new_url)

        opener = urllib.request.build_opener(HTTPSRedirect())
        def read(url: str, limit: int) -> bytes:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != "https" or parsed.username or parsed.password:
                raise ValueError("Live publication verification requires credential-free HTTPS")
            with opener.open(url, timeout=30) as response:
                data = response.read(limit + 1)
            if len(data) > limit:
                raise ValueError("Live release response exceeds allowed size")
            return data

        try:
            actual_update = json.loads(read(feed_url, 128 * 1024))
            if actual_update != expected_update:
                raise ValueError("Public signed update feed differs from staged release")
            actual_site = json.loads(read(urllib.parse.urljoin(feed_url, "releases.json"), 128 * 1024))
            if actual_site != expected_site:
                raise ValueError("Public download metadata differs from staged release")
            latest = read(urllib.parse.urljoin(feed_url, "latest.yml"), 128 * 1024)
            if latest != (staging / "latest.yml").read_bytes():
                raise ValueError("Public latest.yml differs from staged release")
            artifact = expected_update["windows"]
            digest = hashlib.sha256()
            received = 0
            with opener.open(artifact["url"], timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > artifact["size"]:
                        raise ValueError("Public installer exceeds declared size")
                    digest.update(chunk)
            if received != artifact["size"] or digest.hexdigest() != artifact["sha256"]:
                raise ValueError("Public installer bytes differ from signed manifest")
            self._event(run_id, "live-verification", "passed", installer_sha256=digest.hexdigest(), size_bytes=received)
            return self._update(run_id, status="published", publication_blocker=None)
        except Exception as error:
            self._event(run_id, "live-verification", "failed", message=type(error).__name__ + ": " + str(error)[:1000])
            return self._update(run_id, status="awaiting_live_verification")
