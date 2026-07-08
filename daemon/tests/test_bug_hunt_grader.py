"""End-to-end test for the standalone bug-hunt grader (benchmarks/bug-hunt-fixture/grade.py).

The daemon twin (benchmarks.score_bug_hunt) is unit-tested elsewhere; this exercises the actual
shipped CLI script -- argparse, file loading, grading, and JSON output -- via subprocess, so it is
independent of the daemon app build.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_FIXTURE = Path(__file__).resolve().parents[2] / "benchmarks" / "bug-hunt-fixture"


def test_grade_py_scores_findings(tmp_path: Path) -> None:
    findings = tmp_path / "run-findings.json"
    findings.write_text(
        json.dumps(
            [
                {"surface": "contact form", "text": "empty submit shows success, no validation"},
                {"surface": "header", "text": "mobile nav overlaps logo, unclickable"},
                {"text": "the footer copyright feels dated"},  # matches nothing -> false positive
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(_FIXTURE / "grade.py"),
            "--findings", str(findings),
            "--tokens", "10000",
            "--key", str(_FIXTURE / "answer-key.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["total_bugs"] == 12
    assert report["true_positives"] == 2  # B01 (empty submit) + B04 (mobile nav)
    assert report["false_positives"] == 1
    assert report["bugs_per_1k_tokens"] == 0.2  # 2 / (10000/1000)
    assert report["false_positive_rate"] == round(1 / 3, 4)
    # Per-category breakdown: found 1/2 functional (B01), 1/2 ui (B04), 0/3 accessibility.
    assert report["by_category"]["functional"] == {"found": 1, "total": 2}
    assert report["by_category"]["ui"] == {"found": 1, "total": 2}
    assert report["by_category"]["accessibility"] == {"found": 0, "total": 3}


def test_grade_py_zero_findings_zero_tokens(tmp_path: Path) -> None:
    findings = tmp_path / "empty.json"
    findings.write_text("[]", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(_FIXTURE / "grade.py"),
            "--findings", str(findings),
            "--tokens", "0",
            "--key", str(_FIXTURE / "answer-key.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["true_positives"] == 0
    assert report["false_positives"] == 0
    assert report["bugs_per_1k_tokens"] is None  # no tokens -> undefined efficiency
    assert len(report["missed"]) == 12
