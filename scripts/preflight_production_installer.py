"""Read-only fail-closed preflight before building or promoting Synapse installer."""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

def assess_release(*, free_bytes: int, source_clean: bool,
                   publisher_configured: bool, daemon_fresh: bool,
                   current_version: str, target_version: str,
                   code_signing_cert: bool, unsigned_preview: bool = False) -> dict:
    blockers=[]
    if free_bytes < 5 * 1024**3:
        blockers.append("At least 5 GiB of free disk space required for isolated installer build")
    if not source_clean:
        blockers.append("Packaging sources contain uncommitted or untracked changes")
    if not publisher_configured:
        blockers.append("Trusted bundled Ed25519 publisher public key or feed missing")
    if not daemon_fresh:
        blockers.append("Bundled daemon build is stale relative to integration sources")
    if current_version != target_version:
        blockers.append("Installer target version disagrees with source version")
    if not code_signing_cert and not unsigned_preview:
        blockers.append("Trusted Windows code-signing certificate unavailable; stable release blocked")
    return {"status": "READY_FOR_BUILD" if not blockers else "BLOCKED",
            "blockers": blockers, "unsigned_preview_only": unsigned_preview and not code_signing_cert}

def _git_clean(paths: list[str]) -> bool:
    result=subprocess.run(["git","status","--porcelain","--"]+paths,
                          cwd=ROOT,capture_output=True,text=True,timeout=10)
    return result.returncode==0 and not result.stdout.strip()

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--target-version",required=True)
    parser.add_argument("--unsigned-preview",action="store_true")
    parser.add_argument("--has-trusted-code-signing-cert",action="store_true")
    args=parser.parse_args()
    package=json.loads((ROOT/"package.json").read_text(encoding="utf-8"))
    config=ROOT/"dist-electron"/"update-publisher.json"
    trust=False
    try:
        metadata=json.loads(config.read_text(encoding="utf-8"))
        url=urlparse(metadata.get("feed_url",""))
        trust=(metadata.get("schema")==1 and url.scheme=="https"
               and metadata.get("public_key","").startswith("-----BEGIN PUBLIC KEY-----"))
    except (OSError,ValueError,TypeError):
        pass
    sources=[ROOT/"daemon"/"synapse_daemon"/"__init__.py",
             ROOT/"daemon"/"synapse_daemon"/"mcp_connector.py",
             ROOT/"daemon"/"synapse_daemon"/"device_transfer_service.py"]
    bundled=ROOT/"installer"/"daemon-dist"/"synapse-daemon.exe"
    daemon_fresh=bundled.is_file() and all(bundled.stat().st_mtime>=p.stat().st_mtime
                                           for p in sources if p.exists())
    status=assess_release(
        free_bytes=shutil.disk_usage(ROOT).free,
        source_clean=_git_clean(["electron/","renderer/","installer/","package.json",
                                 "daemon/synapse_daemon/","daemon/synapse_accounts/"]),
        publisher_configured=trust,
        daemon_fresh=daemon_fresh,
        current_version=package["version"],
        target_version=args.target_version,
        code_signing_cert=args.has_trusted_code_signing_cert,
        unsigned_preview=args.unsigned_preview)
    print(json.dumps(status,indent=2))
    return 0 if status["status"]=="READY_FOR_BUILD" else 1

if __name__=="__main__":
    raise SystemExit(main())
