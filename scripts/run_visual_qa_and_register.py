#!/usr/bin/env python3
"""Run the standard browser audit and register its report with Synapse Quality OS.

Requires an existing local daemon API token in SYNAPSE_TOKEN.
Does not use paid AI providers or external model credits.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--subject-type", default="agent_work_item")
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--synapse-url", required=True, help="Running local Synapse daemon base URL")
    args = parser.parse_args()
    token = os.environ.get("SYNAPSE_TOKEN")
    if not token:
        parser.error("SYNAPSE_TOKEN is required to register evidence")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "visual-qa.mjs"), args.url, str(output)],
        cwd=str(ROOT), check=False,
    )
    report = output / "report.json"
    if not report.is_file():
        print("Browser audit did not produce report.json; no passing proof recorded.", file=sys.stderr)
        return 2
    payload = json.dumps({
        "subject_type": args.subject_type,
        "subject_id": args.subject_id,
        "report_path": str(report),
    }).encode()
    req = Request(
        args.synapse_url.rstrip("/") + "/api/v1/visual-audits/import",
        data=payload,
        headers={"Content-Type": "application/json", "X-Synapse-Token": token},
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as response:
            evidence = json.load(response)
    except Exception as exc:
        print(f"Could not register browser evidence: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "evidence_id": evidence.get("id"),
        "verdict": evidence.get("verdict"),
        "report": str(report),
    }))
    return 0 if result.returncode == 0 and evidence.get("verdict") == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
