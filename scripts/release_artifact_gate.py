"""Fail-closed, read-only Synapse Windows release artifact validation.

This tool does NOT generate, publish, sign, or install a release. In particular
the filename or version string of an old installer is not evidence that the
latest daemon build is inside it.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path


class ReleaseGateError(ValueError):
    pass


def _digest(path: Path, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as src:
        for part in iter(lambda: src.read(1024 * 1024), b""):
            hasher.update(part)
    return hasher.hexdigest()


def _scalar(text: str, field: str) -> str:
    matches = re.findall(r"(?m)^" + re.escape(field) + r":\s*['\"]?([^'\"\r\n]+)['\"]?\s*$", text)
    if len(matches) != 1:
        raise ReleaseGateError(f"Expected exactly one {field} in latest.yml")
    return matches[0].strip()


def verify_windows_release(
    artifact: Path, latest: Path, proof: Path, *,
    expected_version: str, expected_commit: str,
    website_metadata: Path | None = None,
) -> dict:
    """Require matching local installer, feed, independent smoke proof, and build SHA."""
    artifact, latest, proof = map(Path, (artifact, latest, proof))
    if not re.fullmatch(r"\d+\.\d+\.\d+", expected_version):
        raise ReleaseGateError("Expected a three-part numeric release version")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ReleaseGateError("Expected a complete 40-character source commit")
    if artifact.suffix.lower() != ".exe" or not artifact.is_file():
        raise ReleaseGateError("Windows installer artifact is missing")
    if artifact.stat().st_size < 1024 * 1024:
        raise ReleaseGateError("Windows installer is unexpectedly small")

    yaml = latest.read_text(encoding="utf-8")
    version = _scalar(yaml, "version")
    if version != expected_version:
        raise ReleaseGateError("Update feed advertises the wrong release version")
    advertised_path = _scalar(yaml, "path")
    if Path(advertised_path).name != artifact.name:
        raise ReleaseGateError("Updater path does not match the actual installer filename")
    feed_urls = re.findall(r"(?m)^\s*-\s*url:\s*(.+?)\s*$", yaml)
    if len(feed_urls) != 1 or feed_urls[0].strip("'\"") != artifact.name:
        raise ReleaseGateError("Updater files URL does not match the actual installer filename")
    advertised_size = re.findall(r"(?m)^\s*size:\s*(\d+)\s*$", yaml)
    if len(advertised_size) != 1 or int(advertised_size[0]) != artifact.stat().st_size:
        raise ReleaseGateError("Update feed installer size mismatch")
    advertised_sha = _scalar(yaml, "sha512")
    digest = _digest(artifact, "sha512")
    try:
        decoded = base64.b64decode(advertised_sha, validate=True)
    except ValueError as exc:
        raise ReleaseGateError("Invalid update feed SHA512") from exc
    if decoded.hex() != digest:
        raise ReleaseGateError("Update feed installer SHA512 mismatch")

    evidence = json.loads(proof.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict) or evidence.get("status") != "verified":
        raise ReleaseGateError("Independent installer smoke verification is required")
    if evidence.get("version") != expected_version:
        raise ReleaseGateError("Installer smoke proof version mismatch")
    if evidence.get("source_commit") != expected_commit:
        raise ReleaseGateError("Installer was not verified against the requested source commit")
    sha256 = _digest(artifact, "sha256")
    if evidence.get("artifact_sha256") != sha256:
        raise ReleaseGateError("Installer bytes changed after smoke verification")
    if evidence.get("account_preserved") is not True or evidence.get("device_identity_preserved") is not True:
        raise ReleaseGateError("Account/device identity preservation not verified")
    if evidence.get("mcp_connector_url_preserved") is not True:
        raise ReleaseGateError("Existing MCP connector URL preservation not verified")

    if website_metadata is not None:
        meta = json.loads(Path(website_metadata).read_text(encoding="utf-8"))
        if meta.get("version") != expected_version:
            raise ReleaseGateError("Website release version mismatch")
        windows = [a for a in meta.get("artifacts", []) if a.get("platform") == "windows"]
        if len(windows) != 1:
            raise ReleaseGateError("Website must list exactly one Windows artifact")
        row = windows[0]
        if row.get("status") != "ready" or row.get("sha256") != sha256:
            raise ReleaseGateError("Website installer checksum/status mismatch")
        if row.get("source_commit") != expected_commit:
            raise ReleaseGateError("Website installer provenance does not match the source commit")
        if row.get("size_bytes") != artifact.stat().st_size:
            raise ReleaseGateError("Website installer byte size mismatch")
        if Path(row.get("url", "")).name != artifact.name:
            raise ReleaseGateError("Website points to a different Windows installer")

    return {"status": "verified", "version": version, "source_commit": expected_commit,
            "sha256": sha256, "sha512": digest, "size_bytes": artifact.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--latest", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--website-metadata", type=Path)
    args = parser.parse_args()
    try:
        output = verify_windows_release(
            args.artifact, args.latest, args.proof,
            expected_version=args.expected_version,
            expected_commit=args.expected_commit,
            website_metadata=args.website_metadata,
        )
    except (ReleaseGateError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
