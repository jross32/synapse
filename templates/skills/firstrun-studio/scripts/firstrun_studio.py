#!/usr/bin/env python3
"""Deterministic helpers for the FirstRun Studio Synapse skill pack.

The script does not design UI. It makes the workflow reproducible:
- scaffold a target project's FirstRun brief packet
- validate a brief before implementation
- score a human/AI quality audit against the published rubric
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DIMENSIONS = (
    "promise_continuity",
    "activation_clarity",
    "friction_discipline",
    "trust",
    "auth_robustness",
    "state_completeness",
    "accessibility",
    "responsive_quality",
    "visual_system_coherence",
    "contextual_guidance",
    "originality_brand_fit",
    "measurement_iteration",
)

CRITICAL_GATES = (
    "keyboard_auth",
    "password_manager_and_paste",
    "verification_recovery",
    "double_submit_safe",
    "mobile_primary_action_accessible",
    "reaches_real_value",
    "original_not_proprietary_clone",
    "no_sensitive_data_exposure",
)

REQUIRED_BRIEF_FIELDS = (
    "product",
    "audience",
    "primary_job",
    "public_promise",
    "activation_event",
    "first_authenticated_destination",
    "existing_auth",
    "required_identity_data",
    "deferrable_setup",
    "brand_traits",
    "technical_constraints",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


def validate_brief(data: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in REQUIRED_BRIEF_FIELDS if not data.get(key)]
    activation = data.get("activation_event")
    if isinstance(activation, dict):
        if not activation.get("action") or not activation.get("visible_proof"):
            missing.append("activation_event.action+visible_proof")
    elif activation and "->" not in str(activation):
        missing.append("activation_event must describe action -> visible proof")
    return {
        "ok": not missing,
        "missing": missing,
        "required_count": len(REQUIRED_BRIEF_FIELDS),
    }


def score_audit(data: dict[str, Any]) -> dict[str, Any]:
    dimensions = data.get("dimensions") or {}
    gates = data.get("critical_gates") or {}
    browser = data.get("browser_proof") or {}

    missing_dimensions = [key for key in DIMENSIONS if key not in dimensions]
    invalid_dimensions = [
        key for key in DIMENSIONS
        if key in dimensions and (not isinstance(dimensions[key], (int, float)) or not 0 <= dimensions[key] <= 5)
    ]
    failed_gates = [key for key in CRITICAL_GATES if gates.get(key) is not True]
    values = [float(dimensions[key]) for key in DIMENSIONS if key in dimensions and key not in invalid_dimensions]
    total = round(sum(values), 1)

    if total >= 54:
        band = "exceptional"
    elif total >= 48:
        band = "professional"
    elif total >= 42:
        band = "strong_needs_polish"
    elif total >= 36:
        band = "usable_baseline"
    else:
        band = "rework"

    every_dimension_3_plus = (
        not missing_dimensions
        and not invalid_dimensions
        and all(float(dimensions[key]) >= 3 for key in DIMENSIONS)
    )
    desktop_mobile_proof = browser.get("desktop") is True and browser.get("mobile") is True
    professional_claim_allowed = (
        total >= 48
        and every_dimension_3_plus
        and not failed_gates
        and desktop_mobile_proof
    )

    return {
        "score": total,
        "max_score": 60,
        "band": band,
        "professional_claim_allowed": professional_claim_allowed,
        "missing_dimensions": missing_dimensions,
        "invalid_dimensions": invalid_dimensions,
        "failed_critical_gates": failed_gates,
        "browser_proof": {
            "desktop": browser.get("desktop") is True,
            "mobile": browser.get("mobile") is True,
        },
    }


def scaffold(product: str, out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    brief_path = out_dir / "firstrun-brief.json"
    audit_path = out_dir / "firstrun-audit.json"
    journey_path = out_dir / "FIRSTRUN-JOURNEY.md"

    if brief_path.exists() or audit_path.exists() or journey_path.exists():
        raise FileExistsError("Refusing to overwrite an existing FirstRun packet.")

    brief = {
        "product": product,
        "audience": "",
        "primary_job": "",
        "public_promise": "",
        "activation_event": {"action": "", "visible_proof": ""},
        "first_authenticated_destination": "",
        "existing_auth": {"provider": "", "methods": []},
        "required_identity_data": [],
        "deferrable_setup": [],
        "trust_concerns": [],
        "mobile_constraints": [],
        "brand_traits": [],
        "existing_design_system": [],
        "technical_constraints": [],
    }
    audit = {
        "dimensions": {key: 0 for key in DIMENSIONS},
        "critical_gates": {key: False for key in CRITICAL_GATES},
        "browser_proof": {"desktop": False, "mobile": False},
        "notes": [],
    }
    journey = f"""# FirstRun journey - {product}

Activation event: **TBD**

## State map

```mermaid
stateDiagram-v2
  [*] --> PUBLIC
  PUBLIC --> AUTH_CHOICE
  AUTH_CHOICE --> IDENTITY
  IDENTITY --> MINIMUM_SETUP
  MINIMUM_SETUP --> FIRST_VALUE
  FIRST_VALUE --> ACTIVATED
  ACTIVATED --> [*]
```

## Screen notes

Replace the generic states with the shortest product-specific route to first value.
"""

    brief_path.write_text(json.dumps(brief, indent=2) + "\n", encoding="utf-8")
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    journey_path.write_text(journey, encoding="utf-8")
    return {
        "brief": str(brief_path),
        "audit": str(audit_path),
        "journey": str(journey_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="firstrun_studio")
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="Create a FirstRun planning packet.")
    p_new.add_argument("--product", required=True)
    p_new.add_argument("--out", required=True, type=Path)

    p_validate = sub.add_parser("validate", help="Validate a FirstRun brief JSON file.")
    p_validate.add_argument("path", type=Path)

    p_score = sub.add_parser("score", help="Score a FirstRun audit JSON file.")
    p_score.add_argument("path", type=Path)

    args = parser.parse_args()
    if args.command == "new":
        result = scaffold(args.product, args.out)
    elif args.command == "validate":
        result = validate_brief(_read_json(args.path))
    else:
        result = score_audit(_read_json(args.path))

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
