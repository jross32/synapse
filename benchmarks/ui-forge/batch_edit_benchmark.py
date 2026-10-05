#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BATCH = REPO / "templates" / "skills" / "ui-forge" / "scripts" / "batch_ast_edit.mjs"


def pointer(relative: str, source: str, needle: str, occurrence: int = 1) -> str:
    start = -1
    cursor = 0
    for _ in range(occurrence):
        start = source.index(needle, cursor)
        cursor = start + len(needle)
    before = source[:start]
    line = before.count("\n") + 1
    column = start - before.rfind("\n")
    return f"{relative}:{line}:{column}"


def run_batch(root: Path, edits: list[dict[str, Any]], dry_run: bool = False) -> tuple[int, dict[str, Any]]:
    spec = root / "batch.json"
    spec.write_text(json.dumps({"edits": edits}, indent=2) + "\n", encoding="utf-8")
    cmd = ["node", str(BATCH), str(root), str(spec)]
    if dry_run:
        cmd.append("--dry-run")
    cp = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, timeout=40)
    try:
        payload = json.loads(cp.stdout)
    except json.JSONDecodeError:
        payload = {"ok": False, "parse_error": cp.stdout, "stderr": cp.stderr}
    return cp.returncode, payload


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ui-forge-batch-") as tmp:
        root = Path(tmp)
        (root / "src").mkdir(parents=True)
        app = 'export function App(){return <div><button className="a">One</button><button className="b">Two</button><button className={kind}>Three</button></div>}\n'
        other = 'export function Other(){return <button className="other">Other</button>}\n'
        app_path = root / "src" / "App.jsx"
        other_path = root / "src" / "Other.jsx"
        app_path.write_text(app, encoding="utf-8")
        other_path.write_text(other, encoding="utf-8")

        first = pointer("src/App.jsx", app, "<button", 1)
        second = pointer("src/App.jsx", app, "<button", 2)
        dynamic = pointer("src/App.jsx", app, "<button", 3)
        other_ptr = pointer("src/Other.jsx", other, "<button", 1)

        positive_edits = [
            {"source": first, "operation": {"type": "set_text", "value": "First"}},
            {"source": second, "operation": {"type": "set_text", "value": "Second"}},
            {"source": other_ptr, "operation": {"type": "class_tokens", "add": ["selected"], "remove": []}},
        ]
        code, positive = run_batch(root, positive_edits)
        positive_app = app_path.read_text(encoding="utf-8")
        positive_other = other_path.read_text(encoding="utf-8")
        exact_app = app.replace(">One</button>", ">First</button>").replace(">Two</button>", ">Second</button>")
        exact_other = other.replace('className="other"', 'className="other selected"')

        checks: dict[str, bool] = {
            "multi_edit_apply_succeeds": code == 0 and positive.get("ok") is True,
            "same_file_reverse_order_preserves_pointers": positive_app == exact_app,
            "cross_file_edit_succeeds": positive_other == exact_other and positive.get("file_count") == 2,
            "batch_reports_atomic": positive.get("atomic") is True and positive.get("rolled_back") is False,
        }

        # Mixed safe/unsafe validation must leave every file byte-identical.
        app_path.write_text(app, encoding="utf-8")
        other_path.write_text(other, encoding="utf-8")
        negative_edits = [
            {"source": first, "operation": {"type": "set_text", "value": "ShouldNotLand"}},
            {"source": dynamic, "operation": {"type": "class_tokens", "add": ["hot"], "remove": []}},
        ]
        neg_code, negative = run_batch(root, negative_edits)
        checks["mixed_unsafe_batch_fails"] = neg_code != 0 and negative.get("ok") is False
        checks["mixed_unsafe_batch_writes_nothing"] = app_path.read_text(encoding="utf-8") == app and other_path.read_text(encoding="utf-8") == other
        checks["validation_failure_is_explicit"] = negative.get("error") == "batch validation failed; nothing was written"

        duplicate_edits = [
            {"source": first, "operation": {"type": "set_text", "value": "A"}},
            {"source": first, "operation": {"type": "set_text", "value": "B"}},
        ]
        dup_code, duplicate = run_batch(root, duplicate_edits)
        checks["duplicate_source_is_refused"] = dup_code != 0 and "duplicate source pointers" in duplicate.get("error", "")
        checks["duplicate_refusal_writes_nothing"] = app_path.read_text(encoding="utf-8") == app

        dry_code, dry = run_batch(root, positive_edits, dry_run=True)
        checks["dry_run_is_non_mutating"] = dry_code == 0 and dry.get("dry_run") is True and app_path.read_text(encoding="utf-8") == app

        result = {
            "schema": "ui-forge-batch-edit-benchmark-v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "checks": checks,
            "passed": sum(checks.values()),
            "total": len(checks),
            "overall_pass": all(checks.values()),
            "positive": positive,
            "negative": negative,
            "claims": {
                "atomic_batch_gate_proven": checks["batch_reports_atomic"] and checks["mixed_unsafe_batch_writes_nothing"],
                "same_file_pointer_stability_proven": checks["same_file_reverse_order_preserves_pointers"],
                "not_a_full_ui_forge_or_lovable_claim": True,
            },
        }
        print(json.dumps(result, indent=2))
        out = Path(__file__).resolve().parent / "results"
        out.mkdir(parents=True, exist_ok=True)
        (out / "batch-edit-latest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
