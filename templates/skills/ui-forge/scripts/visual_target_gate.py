#!/usr/bin/env python3
"""Fail-closed Visual Target Contract evaluator for UI Forge.

This deliberately does not claim to understand aesthetics from pixels. It verifies
that required references, surfaces, sections, assets, scores, and blocker status are
present in evidence produced by browser + visual review.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "ui-forge-visual-target-v1"
ASSET_RANK = {
    "css-primitive": 0,
    "vector-graphic": 1,
    "device-mockup": 2,
    "production-illustration": 3,
    "3d-render": 3,
    "photoreal-image": 4,
    "motion-asset": 4,
}


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"malformed JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"expected object JSON: {path}")
    return payload


def _exists(project_root: Path, value: str) -> bool:
    if not value:
        return False
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path.exists() and path.is_file()


def evaluate(contract: dict[str, Any], evidence: dict[str, Any], project_root: Path) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if contract.get("schema") != SCHEMA:
        issues.append({"code": "contract_schema", "message": f"contract schema must be {SCHEMA}"})

    references = contract.get("references")
    if not isinstance(references, list) or not references:
        issues.append({"code": "references_missing", "message": "at least one locked visual reference is required"})
    else:
        for ref in references:
            if not isinstance(ref, dict):
                issues.append({"code": "reference_invalid", "message": "reference entries must be objects"})
                continue
            path = str(ref.get("path") or "")
            external_id = str(ref.get("design_reference_id") or "")
            if not path and not external_id:
                issues.append({"code": "reference_unresolved", "message": f"reference {ref.get('id','?')} has neither path nor design_reference_id"})
            elif path and not _exists(project_root, path):
                issues.append({"code": "reference_file_missing", "message": f"reference file does not exist: {path}"})

    evidence_surfaces = {
        str(item.get("surface_id")): item
        for item in evidence.get("surfaces", [])
        if isinstance(item, dict) and item.get("surface_id")
    }

    min_score = float(contract.get("global", {}).get("minimum_visual_score", 0) or 0)
    forbid_placeholders = bool(contract.get("global", {}).get("forbid_placeholder_surfaces", False))

    for surface in contract.get("surfaces", []):
        if not isinstance(surface, dict):
            issues.append({"code": "surface_invalid", "message": "surface entries must be objects"})
            continue
        sid = str(surface.get("id") or "")
        if not sid:
            issues.append({"code": "surface_id_missing", "message": "surface missing id"})
            continue
        proof = evidence_surfaces.get(sid)
        if proof is None:
            issues.append({"code": "surface_unproven", "message": f"{sid}: no evidence"})
            continue

        shot = str(proof.get("screenshot") or "")
        if not shot or not _exists(project_root, shot):
            issues.append({"code": "screenshot_missing", "message": f"{sid}: screenshot missing: {shot or '<none>'}"})

        expected_route = str(surface.get("route") or "")
        actual_route = str(proof.get("route") or "")
        if expected_route and actual_route and expected_route != actual_route:
            issues.append({"code": "route_mismatch", "message": f"{sid}: expected route {expected_route}, got {actual_route}"})
        elif expected_route and not actual_route:
            issues.append({"code": "route_unproven", "message": f"{sid}: route evidence missing"})

        required_sections = {str(x) for x in surface.get("required_sections", [])}
        found_sections = {str(x) for x in proof.get("sections_present", [])}
        for missing in sorted(required_sections - found_sections):
            issues.append({"code": "section_missing", "message": f"{sid}: required section missing: {missing}"})

        proof_assets = {
            str(x.get("id")): x
            for x in proof.get("assets", [])
            if isinstance(x, dict) and x.get("id")
        }
        for req in surface.get("required_assets", []):
            if not isinstance(req, dict) or not req.get("id"):
                issues.append({"code": "asset_requirement_invalid", "message": f"{sid}: malformed asset requirement"})
                continue
            aid = str(req["id"])
            if req.get("required", True) is False:
                continue
            actual = proof_assets.get(aid)
            if actual is None:
                issues.append({"code": "asset_missing", "message": f"{sid}: required asset missing: {aid}"})
                continue
            status = str(actual.get("status") or "")
            if status not in {"resolved", "approved"}:
                issues.append({"code": "asset_unresolved", "message": f"{sid}: {aid} status is {status or '<none>'}"})
            minimum_kind = str(req.get("minimum_kind") or req.get("kind") or "")
            actual_kind = str(actual.get("kind") or "")
            if minimum_kind:
                min_rank = ASSET_RANK.get(minimum_kind)
                actual_rank = ASSET_RANK.get(actual_kind)
                if min_rank is None:
                    warnings.append({"code": "asset_kind_unknown", "message": f"{sid}: unknown minimum asset kind {minimum_kind}"})
                elif actual_rank is None or actual_rank < min_rank:
                    issues.append({
                        "code": "asset_downgrade",
                        "message": f"{sid}: {aid} requires {minimum_kind} or better, evidence says {actual_kind or '<none>'}",
                    })
            source_path = str(actual.get("path") or "")
            if source_path and not _exists(project_root, source_path):
                issues.append({"code": "asset_file_missing", "message": f"{sid}: asset file missing for {aid}: {source_path}"})

        visible = [str(x).strip().lower() for x in proof.get("visible_signals", []) if str(x).strip()]
        forbidden = [str(x).strip().lower() for x in surface.get("forbidden_signals", []) if str(x).strip()]
        for signal in forbidden:
            if any(signal in text for text in visible):
                issues.append({"code": "forbidden_signal", "message": f"{sid}: visible prototype signal remains: {signal}"})

        if forbid_placeholders and bool(proof.get("placeholder_surface", False)):
            issues.append({"code": "placeholder_surface", "message": f"{sid}: required surface is still a placeholder"})

        score_raw = proof.get("visual_score")
        if min_score > 0:
            if score_raw is None:
                issues.append({"code": "visual_score_missing", "message": f"{sid}: visual review score missing"})
            else:
                try:
                    score = float(score_raw)
                except (TypeError, ValueError):
                    issues.append({"code": "visual_score_invalid", "message": f"{sid}: visual review score is invalid"})
                else:
                    if score < min_score:
                        issues.append({"code": "visual_score_low", "message": f"{sid}: visual score {score:g} < required {min_score:g}"})

        for gap in proof.get("unresolved_differences", []):
            if isinstance(gap, dict):
                required = gap.get("required", True)
                text = str(gap.get("message") or gap.get("id") or "unresolved difference")
            else:
                required = True
                text = str(gap)
            if required:
                issues.append({"code": "unresolved_difference", "message": f"{sid}: {text}"})

    for blocker in evidence.get("blockers", []):
        if isinstance(blocker, dict):
            if blocker.get("resolved") is True:
                continue
            message = str(blocker.get("message") or blocker.get("id") or "unresolved blocker")
        else:
            message = str(blocker)
        if message:
            issues.append({"code": "blocker", "message": message})

    surface_total = max(1, len(contract.get("surfaces", [])))
    proven = surface_total - len({
        issue["message"].split(":", 1)[0]
        for issue in issues
        if issue["code"] in {"surface_unproven", "screenshot_missing", "placeholder_surface"}
    })
    completeness = max(0.0, min(100.0, 100.0 * proven / surface_total))

    return {
        "schema": "ui-forge-visual-target-report-v1",
        "pass": not issues,
        "project_id": contract.get("project_id", ""),
        "issue_count": len(issues),
        "warning_count": len(warnings),
        "surface_count": len(contract.get("surfaces", [])),
        "completeness_percent": round(completeness, 2),
        "issues": issues,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a UI Forge Visual Target Contract.")
    parser.add_argument("contract", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = evaluate(_load(args.contract), _load(args.evidence), args.project_root.resolve())
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
