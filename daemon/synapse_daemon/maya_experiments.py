"""Safe, measurable experiment drafts for Maya's Growth Director workflow.

Plans are derived from verified *registry* evidence only. They are never actual
experiment results, customer counts, autonomous work or authorization to publish.
Persistence uses the existing auditable staff_events table (no migration).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from . import staff_operations
from .maya_growth import MAYA_ID, build_growth_review


def _snapshot_freshness(value: str | None, *, now: datetime) -> str:
    if not value:
        return "unknown"
    try:
        checked = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if checked.tzinfo is None:
            return "unknown"
        age = (now - checked.astimezone(timezone.utc)).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return "unknown"
    if age < -300:
        return "future_clock_skew"
    return "fresh" if 0 <= age <= 86400 else "stale"


def build_experiment_plan(
    conn: sqlite3.Connection, *, now: datetime | None = None,
) -> dict[str, Any]:
    """Read-only draft. Observed metrics remain None until measured externally."""
    observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    review = build_growth_review(conn)
    # Fresh health evidence outranks an older green registry label; this
    # prioritization is operational readiness only, never predicted sales.
    candidate = next(
        (x for x in review["candidates"]
         if x["registered_status"] == "launched"
         and x["recorded_health"] == "healthy"
         and _snapshot_freshness(x["last_health_at"], now=observed_at) == "fresh"),
        None,
    ) or next(
        (x for x in review["candidates"]
         if x["project_id"] == review["recommended_project_id"]), None,
    )
    if candidate is None:
        return {
            "status": "no_candidate", "project_id": None,
            "source_fingerprint": review["source_fingerprint"],
            "title": "No experiment proposed",
            "hypothesis": None, "metric": None, "funnel_steps": [],
            "baseline": None, "attempts": None, "completions": None,
            "measurement_method": None, "guardrails": [],
            "required_evidence": [], "approval_state": "not_requested",
            "executed": False, "cost_budget_usd": 0,
            "readiness_gate": "needs_commercial_project",
            "next_action": "Identify one real commercial product and its first-value journey.",
        }
    project_id = candidate["project_id"]
    freshness = _snapshot_freshness(candidate["last_health_at"], now=observed_at)
    # The registry can be stale or wrong. Never infer a working funnel from it.
    runtime_ready = (
        candidate["registered_status"] == "launched"
        and candidate["recorded_health"] == "healthy"
        and freshness == "fresh"
    )
    if project_id == "reselltogether":
        steps = [
            "Test-account sign-in",
            "Select and upload garment photos",
            "Save one private closet item",
            "Prepare a complete draft listing",
        ]
        hypothesis = (
            "An authorized tester can turn garment photos into a private, "
            "complete resale listing draft without external publication."
        )
    else:
        # No fabricated product-specific funnel: discovery is the first step.
        steps = [
            "Identify the actual product first-value event from UI/source",
            "Verify a consented test account can start that flow",
            "Complete the observed first-value flow and capture evidence",
        ]
        hypothesis = (
            "An authorized internal tester can complete the project's "
            "documented first-value workflow without an unsafe external action."
        )
    gate = "internal_test_candidate" if runtime_ready else "runtime_preflight_required"
    next_action = (
        "Run one authorized internal first-value test; log each step and failure."
        if runtime_ready else
        "Recheck live HTTP health and the real product UI; capture dated proof before testing conversion."
    )
    plan = {
        "status": "draft_unexecuted",
        "project_id": project_id,
        "source_fingerprint": review["source_fingerprint"],
        "title": "Internal first-value baseline: " + candidate["name"][:100],
        "hypothesis": hypothesis,
        "metric": {
            "name": "First-value journey completion rate",
            "numerator": "Consent-based internal sessions completing the defined final step",
            "denominator": "Consent-based internal sessions attempting step one",
            "unit": "completed / attempted",
        },
        "funnel_steps": steps,
        "baseline": None,
        "attempts": None,
        "completions": None,
        "measurement_method": "Use dated, per-step pass/fail and elapsed-time receipts; do not substitute synthetic traffic for real users.",
        "guardrails": [
            "No live marketplace submission, campaigns, outreach, or paid traffic",
            "Stop on account-isolation, privacy, authentication or data-loss defects",
            "Do not use a real customer's private data without explicit permission",
        ],
        "required_evidence": [
            "Test date, environment and tested product revision",
            "Dated per-step pass/fail and captured error states",
            "Screenshots or trace IDs with secrets/personal data redacted",
            "Actual numerator and denominator, including failures",
        ],
        "approval_state": "not_requested",
        "executed": False,
        "cost_budget_usd": 0,
        "health_freshness": freshness,
        "readiness_gate": gate,
        "next_action": next_action,
    }
    return plan


def record_experiment_plan(conn: sqlite3.Connection) -> dict[str, Any]:
    """Record a single immutable *proposal* receipt; never launch an experiment."""
    member = staff_operations.get_staff(conn, MAYA_ID)
    if member.handle != "maya":
        raise ValueError("Maya staff identity does not match")
    plan = build_experiment_plan(conn)
    if plan["status"] == "no_candidate":
        return {"created": False, "event_id": None, "plan": plan}
    # A material readiness transition (fresh -> stale, ready -> blocked) should
    # be visible as a new review version, but clock ticks alone must not spam.
    material = {key: value for key, value in plan.items() if key != "next_action"}
    fingerprint = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    rows = conn.execute(
        """SELECT id,metadata_json FROM staff_events
           WHERE staff_member_id=? AND event_type='growth_experiment_plan'
           ORDER BY created_at DESC LIMIT 200""", (member.id,),
    ).fetchall()
    for row in rows:
        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except (TypeError, ValueError):
            continue
        if meta.get("plan_fingerprint") == fingerprint:
            return {"created": False, "event_id": row["id"], "plan": plan}
    event = staff_operations.record_event(
        conn, member.id,
        event_type="growth_experiment_plan",
        title="Maya measurable experiment plan (not executed)",
        body_md=(
            f"**Project:** {plan['project_id']}\n\n"
            f"**Hypothesis:** {plan['hypothesis']}\n\n"
            f"**Measurement:** {plan['metric']['unit']}; baseline unknown.\n\n"
            f"**Readiness:** {plan['readiness_gate']}, health freshness: {plan['health_freshness']}.\n\n"
            f"**Next action:** {plan['next_action']}\n\n"
            "**Status:** draft only. No customers, tests, spending, outreach or publication."
        ),
        source="maya-growth-experiment",
        severity="info", action_required=False,
        metadata={
            "plan_fingerprint": fingerprint,
            "source_fingerprint": plan["source_fingerprint"],
            "project_id": plan["project_id"],
            "plan": plan,
            "execution_status": "not_executed",
        },
    )
    return {"created": True, "event_id": event.id, "plan": plan}
