from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


def _load_locator() -> Any:
    here = Path(__file__).resolve().parent
    path = here / "source_locator.py"
    spec = importlib.util.spec_from_file_location("ui_forge_source_locator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load source_locator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(value: str) -> dict[str, Any]:
    path = Path(value)
    raw = path.read_text(encoding="utf-8") if path.exists() else value
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("selection must be a JSON object")
    return payload


def build_edit_request(
    root: str | Path,
    selection: dict[str, Any],
    instruction: str,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    locator = _load_locator()
    matches = locator.locate_source(root, selection, limit=limit)
    direct = bool(selection.get("ui_forge_source") or selection.get("source"))
    primary = matches[0] if matches else None
    confidence = "high" if direct and primary else "medium" if primary and float(primary.get("match_score", 0)) >= 70 else "low"
    constraints = [
        "preserve working product behavior and data truth",
        "change the smallest owning source/token/prop that explains the requested visual change",
        "do not regenerate unrelated sections",
        "rerender immediately after the edit",
        "verify the selected element plus surrounding layout on the affected viewport",
    ]
    return {
        "schema": "ui-forge-visual-edit-request-v1",
        "instruction": instruction.strip(),
        "selection": selection,
        "source_resolution": {
            "direct_source_tag_present": direct,
            "confidence": confidence,
            "primary": primary,
            "alternates": matches[1:],
        },
        "edit_scope": {
            "preferred_file": primary.get("file") if primary else None,
            "preferred_line": primary.get("line") if primary else None,
            "preferred_column": primary.get("column") if primary else None,
            "must_remain_bounded": True,
        },
        "constraints": constraints,
        "verification": [
            "build_or_run_app",
            "repeat_browser_probe_on_same_element_or_source_tag",
            "check_surrounding_layout_for_regression",
            "check_console_for_runtime_errors",
        ],
        "needs_manual_source_resolution": primary is None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Turn a UI Forge browser selection into a bounded AI edit contract")
    parser.add_argument("root")
    parser.add_argument("selection_json", help="Selection JSON object or path")
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        selection = _read_json(args.selection_json)
        result = build_edit_request(args.root, selection, args.instruction, limit=args.limit)
        serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(serialized, encoding="utf-8")
        print(serialized, end="")
        return 0 if not result["needs_manual_source_resolution"] else 1
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
