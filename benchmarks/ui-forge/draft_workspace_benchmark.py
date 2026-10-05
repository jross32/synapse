#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "templates" / "skills" / "ui-forge" / "scripts" / "draft_workspace.py"


def _load():
    spec = importlib.util.spec_from_file_location("ui_forge_draft_workspace_bench", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def run() -> dict[str, Any]:
    d = _load()
    checks: dict[str, bool] = {}
    observations: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix="ui-forge-drafts-") as temp:
        project = Path(temp) / "project"
        project.mkdir()
        _write(project, "src/App.jsx", "export default function App(){return <h1>Live</h1>}\n")
        _write(project, "src/theme.css", ":root{--accent:#fff}\n")
        _write(project, "package.json", '{"scripts":{"dev":"vite"}}\n')
        _write(project, "server/api.py", "VALUE = 1\n")
        _write(project, ".env", "SECRET=base\n")
        _write(project, "runtime.log", "noise\n")
        _write(project, "service.pid", "1234\n")

        # Two independent drafts from the same live state.
        first = d.create_draft(project, "Direction A")
        second = d.create_draft(project, "Direction B")
        first_ws = Path(first["workspace"])
        second_ws = Path(second["workspace"])
        checks["runtime_artifacts_are_excluded"] = (
            not (first_ws / "runtime.log").exists()
            and not (first_ws / "service.pid").exists()
            and "runtime.log" not in first["base_hashes"]
            and "service.pid" not in first["base_hashes"]
        )
        _write(first_ws, "src/App.jsx", "export default function App(){return <h1>Draft A</h1>}\n")
        _write(second_ws, "src/theme.css", ":root{--accent:#0ff}\n")
        checks["parallel_drafts_leave_live_untouched"] = (
            _read(project, "src/App.jsx").endswith("<h1>Live</h1>}\n")
            and _read(project, "src/theme.css") == ":root{--accent:#fff}\n"
        )

        first_status = d.draft_status(project, first["id"])
        second_status = d.draft_status(project, second["id"])
        checks["changes_are_isolated_and_detected"] = (
            first_status["changes"]["modified"] == ["src/App.jsx"]
            and second_status["changes"]["modified"] == ["src/theme.css"]
        )

        first_accept = d.accept_draft(project, first["id"])
        checks["accept_applies_only_changed_path"] = (
            first_accept["ok"]
            and first_accept["applied_paths"] == ["src/App.jsx"]
            and "Draft A" in _read(project, "src/App.jsx")
            and _read(project, "src/theme.css") == ":root{--accent:#fff}\n"
        )

        # Second draft touched a distinct path, so it can still accept safely even though another
        # live file changed after its base snapshot.
        second_accept = d.accept_draft(project, second["id"])
        checks["nonoverlapping_parallel_accept_succeeds"] = (
            second_accept["ok"]
            and second_accept["applied_paths"] == ["src/theme.css"]
            and _read(project, "src/theme.css") == ":root{--accent:#0ff}\n"
        )

        # Conflict protection on the same path.
        conflict_draft = d.create_draft(project, "Conflict")
        conflict_ws = Path(conflict_draft["workspace"])
        _write(conflict_ws, "src/App.jsx", "export default function App(){return <h1>Draft conflict</h1>}\n")
        _write(project, "src/App.jsx", "export default function App(){return <h1>New live work</h1>}\n")
        conflict_result = d.accept_draft(project, conflict_draft["id"])
        checks["stale_same_path_accept_fails_closed"] = (
            conflict_result["ok"] is False
            and conflict_result["reason"] == "live project changed since draft creation"
            and "New live work" in _read(project, "src/App.jsx")
        )

        # Risk gate: backend/env work may exist in a draft, but normal UI accept refuses it.
        risky = d.create_draft(project, "Risky")
        risky_ws = Path(risky["workspace"])
        _write(risky_ws, "server/api.py", "VALUE = 2\n")
        _write(risky_ws, ".env", "SECRET=changed\n")
        risky_status = d.draft_status(project, risky["id"])
        risky_result = d.accept_draft(project, risky["id"])
        checks["risky_changes_are_classified"] = len(risky_status["risky_changes"]) == 2
        checks["risky_accept_requires_override"] = (
            risky_result["ok"] is False
            and "--allow-risky" in risky_result["reason"]
            and _read(project, "server/api.py") == "VALUE = 1\n"
            and _read(project, ".env") == "SECRET=base\n"
        )

        # Discard is a true no-op on live state.
        discard = d.create_draft(project, "Discard me")
        _write(Path(discard["workspace"]), "src/App.jsx", "discarded\n")
        before_discard = _read(project, "src/App.jsx")
        discarded = d.discard_draft(project, discard["id"])
        checks["discard_never_touches_live"] = discarded["ok"] and _read(project, "src/App.jsx") == before_discard

        observations = {
            "first_accept_backup": first_accept.get("backup"),
            "second_accept_backup": second_accept.get("backup"),
            "conflict": conflict_result.get("conflicts", []),
            "risky_changes": risky_status["risky_changes"],
        }

    return {
        "schema": "ui-forge-draft-workspace-benchmark-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "passed": sum(1 for value in checks.values() if value),
        "total": len(checks),
        "overall_pass": all(checks.values()),
        "observations": observations,
        "claims": {
            "live_isolation_proven": checks.get("parallel_drafts_leave_live_untouched", False),
            "conflict_aware_accept_proven": checks.get("stale_same_path_accept_fails_closed", False),
            "risk_gate_proven": checks.get("risky_accept_requires_override", False),
            "not_a_full_ui_forge_or_lovable_claim": True,
        },
    }


def main() -> int:
    payload = run()
    result_dir = Path(__file__).resolve().parent / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "draft-workspace-latest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
