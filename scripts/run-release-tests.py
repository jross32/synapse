"""Run every daemon test in isolated workers and retain a machine-readable release result."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--junit", type=Path, default=ROOT / ".tmp" / "release-daemon-tests.xml")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("Choose one to four isolated test workers")
    args.junit.parent.mkdir(parents=True, exist_ok=True)
    args.junit.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "scripts") + os.pathsep + str(ROOT / "daemon")
    command = [sys.executable, "-m", "pytest", "-n", str(args.workers), "--dist=loadfile",
               "-p", "release_test_network", "--tb=short", "-q",
               "--junitxml=" + str(args.junit), "daemon/tests"]
    result = subprocess.run(command, cwd=ROOT, env=environment)
    report = {"exit_code": result.returncode, "workers": args.workers,
              "junit": str(args.junit), "scope": "complete daemon suite; cloud calls mocked/blocked"}
    if args.junit.exists():
        suites = ET.parse(args.junit).getroot()
        report["tests"] = sum(int(s.get("tests", "0")) for s in suites.iter("testsuite"))
        report["failures"] = sum(int(s.get("failures", "0")) for s in suites.iter("testsuite"))
        report["errors"] = sum(int(s.get("errors", "0")) for s in suites.iter("testsuite"))
        report["skipped"] = sum(int(s.get("skipped", "0")) for s in suites.iter("testsuite"))
    report_path = args.junit.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    if not args.junit.exists() or report.get("tests", 0) == 0:
        return result.returncode or 1
    return result.returncode

if __name__ == "__main__":
    raise SystemExit(main())
