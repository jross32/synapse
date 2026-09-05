"""REST for human review plus the durable improvement-proposal backlog.

Work-item review keeps the approve/revise/reject workflow from ADR-0016. Proposals use two
independent axes: human decision (pending/accepted/declined) and implementation lifecycle
(proposed/in_progress/done), with queryable categorization and inspectable auto-detection evidence.
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any

from fastapi import APIRouter, Query

from . import coder_workspace
from . import project_records
from . import projects as projects_module
from . import proposals as proposals_module
from . import review
from . import review_engine
from .api_versions import event_name
from .audit import AuditRecord, audit
from .errors import invalid
from .models import AuditSource
from .project_records import ProjectBacklogItemCreate
from .proposals import (
    ProposalCreate,
    ProposalDecision,
    ProposalLifecycleRequest,
    ProposalResolveRequest,
    ProposalSort,
    ProposalStatus,
    SortDirection,
)
from .review import ReviewActionRequest, ReviewInbox
from .storage import Storage
from .ws import EventBus


def _review_pass_summary(plan: review_engine.ReviewPlan, pass_plan: review_engine.ReviewPassPlan) -> str:
    changed = "\n".join(f"- {path}" for path in plan.change.changed_files[:100]) or "- No named files supplied."
    findings = (
        "\n".join(
            f"- [{item.severity}] {item.title}: {item.detail}"
            for item in plan.deterministic_findings
        )
        or "- No deterministic findings."
    )
    focus = "\n".join(f"- {item}" for item in pass_plan.focus_points) or "- Review material correctness."
    diff = review_engine.bounded_diff_for_prompt(plan).strip() or "[no textual diff available]"
    return (
        "Synapse Smart Review Engine generated this targeted, read-only review pass.\n\n"
        f"Project: {plan.project_name} ({plan.project_id})\n"
        f"Risk: {plan.risk.value}\n"
        f"Review mode: {plan.mode.value}\n"
        f"Review token budget: {plan.policy.token_budget}\n"
        f"Estimated context tokens: {plan.estimated_context_tokens}\n"
        f"Why this pass exists: {pass_plan.reason}\n\n"
        "Changed files:\n"
        f"{changed}\n\n"
        "Deterministic pre-checks:\n"
        f"{findings}\n\n"
        "Focus points:\n"
        f"{focus}\n\n"
        "Rules:\n"
        "- Review the supplied change, not the whole repository.\n"
        "- Prefer concrete bugs, regressions, missing proof, or violated contracts over generic advice.\n"
        "- Do not edit files or broaden scope during this pass.\n"
        "- If no material issue exists, say so instead of inventing work.\n"
        "- Recommend another AI pass only when its likely value justifies more tokens.\n\n"
        "Bounded diff/context:\n"
        "```diff\n"
        f"{diff}\n"
        "```"
    )


def build_review_router(storage: Storage, bus: EventBus) -> APIRouter:
    router = APIRouter(prefix="/review", tags=["review"])

    @router.get("/inbox", response_model=ReviewInbox)
    async def inbox() -> ReviewInbox:
        return review.build_inbox(storage.conn)

    @router.post("/engine/plan/{project_id}", response_model=review_engine.ReviewPlan)
    async def plan_project_review(
        project_id: str,
        payload: review_engine.ReviewEngineRequest | None = None,
    ) -> review_engine.ReviewPlan:
        """Plan the cheapest useful review for a project change without spending AI tokens."""

        project = projects_module.get(storage.conn, project_id)
        request = payload or review_engine.ReviewEngineRequest()
        return await asyncio.to_thread(review_engine.plan_project_review, project, request)

    @router.post("/engine/queue/{project_id}", response_model=None, status_code=201)
    async def queue_project_review(
        project_id: str,
        payload: review_engine.ReviewEngineRequest | None = None,
    ) -> dict[str, Any]:
        """Create targeted coder review passes after deterministic/token-budget planning.

        This intentionally reuses the existing coder review-pass runtime instead of launching
        a second model-execution path. AI coders can call this route, then launch the returned
        pass URLs through the normal coder endpoint, which preserves runtime accounting,
        sandboxing, review verdicts, and quality gates.
        """

        project = projects_module.get(storage.conn, project_id)
        request = payload or review_engine.ReviewEngineRequest()
        plan = await asyncio.to_thread(review_engine.plan_project_review, project, request)
        queued: list[dict[str, Any]] = []
        thread = None

        if plan.ai_review_required and plan.review_passes:
            with storage.transaction() as conn:
                existing_threads = coder_workspace.list_threads(conn, project_id)
                thread = existing_threads[0] if existing_threads else coder_workspace.create_thread(
                    conn,
                    project_id,
                    coder_workspace.CoderThreadCreate(
                        title=f"Smart review · {project.name}",
                        active_runtime_id=request.primary_runtime or "codex",
                        thread_kind="review",
                        metadata={"created_by": "review-engine", "review_engine_version": "v1"},
                    ),
                )
                for pass_plan in plan.review_passes:
                    review_pass = coder_workspace.create_review_pass(
                        conn,
                        thread.id,
                        coder_workspace.CoderReviewPassCreate(
                            requested_runtime_id=pass_plan.requested_runtime_id,
                            title=pass_plan.title,
                            summary_md=_review_pass_summary(plan, pass_plan),
                            metadata={
                                "review_kind": pass_plan.review_kind,
                                "reason": pass_plan.reason,
                                "focus_points": pass_plan.focus_points,
                                "review_engine": "smart-v1",
                                "risk": plan.risk.value,
                                "review_mode": plan.mode.value,
                                "token_budget": plan.policy.token_budget,
                                "estimated_context_tokens": plan.estimated_context_tokens,
                                "source": request.source,
                            },
                        ),
                    )
                    queued.append(
                        {
                            "review_pass": review_pass.model_dump(mode="json"),
                            "launch_url": (
                                f"/api/v1/coder-threads/{thread.id}/review-passes/"
                                f"{review_pass.id}/launch"
                            ),
                        }
                    )
                    audit(
                        conn,
                        AuditRecord(
                            entity_type="coder_review_pass",
                            entity_id=review_pass.id,
                            action="review_engine.queued",
                            source=AuditSource.AUTO,
                            result="success",
                            details={
                                "project_id": project_id,
                                "risk": plan.risk.value,
                                "mode": plan.mode.value,
                                "review_kind": pass_plan.review_kind,
                                "requested_runtime_id": pass_plan.requested_runtime_id,
                            },
                        ),
                    )

        await bus.publish(
            event_name("review", "engine_planned"),
            {
                "project_id": project_id,
                "risk": plan.risk.value,
                "mode": plan.mode.value,
                "ai_review_required": plan.ai_review_required,
                "queued": len(queued),
            },
        )
        return {
            "plan": plan.model_dump(mode="json"),
            "thread": thread.model_dump(mode="json") if thread else None,
            "queued": queued,
            "next_action": (
                "Launch each returned launch_url through Synapse. The existing coder review runtime "
                "will execute it read-only and retain normal usage/accounting semantics."
                if queued
                else "No AI review pass was worth queueing for this change."
            ),
        }

    async def _act(work_item_id: str, action: str, note: str | None) -> dict[str, Any]:
        with storage.transaction() as conn:
            if action == "approve":
                item = review.approve(conn, work_item_id)
            elif action == "revise":
                item = review.revise(conn, work_item_id, note)
            else:
                item = review.reject(conn, work_item_id, note)
            audit(
                conn,
                AuditRecord(
                    entity_type="agent_work_item",
                    entity_id=work_item_id,
                    action=f"review_{action}",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"status": item.status.value},
                ),
            )
        await bus.publish(
            event_name("review", "resolved"),
            {"id": work_item_id, "action": action, "status": item.status.value},
        )
        return item.model_dump(mode="json")

    @router.post("/items/{work_item_id}/approve", response_model=None)
    async def approve(work_item_id: str) -> dict[str, Any]:
        return await _act(work_item_id, "approve", None)

    @router.post("/items/{work_item_id}/revise", response_model=None)
    async def revise(work_item_id: str, payload: ReviewActionRequest) -> dict[str, Any]:
        return await _act(work_item_id, "revise", payload.note)

    @router.post("/items/{work_item_id}/reject", response_model=None)
    async def reject(work_item_id: str, payload: ReviewActionRequest) -> dict[str, Any]:
        return await _act(work_item_id, "reject", payload.note)

    @router.post("/proposals", response_model=proposals_module.Proposal)
    async def file_proposal(payload: ProposalCreate) -> proposals_module.Proposal:
        """File durable backlog work. ``kind`` is first-class; metadata.kind remains accepted."""
        with storage.transaction() as conn:
            proposal = proposals_module.create_proposal(conn, payload)
            audit(
                conn,
                AuditRecord(
                    entity_type="proposal",
                    entity_id=proposal.id,
                    action="proposal.filed",
                    source=AuditSource.AUTO,
                    result="success",
                    details={
                        "title": proposal.title,
                        "project_id": proposal.project_id,
                        "kind": proposal.kind,
                    },
                ),
            )
        await bus.publish(event_name("review", "proposal_filed"), {"id": proposal.id})
        return proposal

    async def _decide_proposal(
        proposal_id: str, decision: ProposalDecision, note: str
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            proposal = proposals_module.resolve_proposal(conn, proposal_id, decision, note)
            audit(
                conn,
                AuditRecord(
                    entity_type="proposal",
                    entity_id=proposal_id,
                    action=f"proposal.decision.{decision.value}",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"status": proposal.status.value},
                ),
            )
        await bus.publish(
            event_name("review", "proposal_updated"),
            {"id": proposal_id, "decision": decision.value, "status": proposal.status.value},
        )
        return proposal.model_dump(mode="json")

    # Compatibility URLs retained: approve/reject now change DECISION only. They no longer pretend
    # an accepted idea has been implemented.
    @router.post("/proposals/{proposal_id}/approve", response_model=None)
    async def approve_proposal(
        proposal_id: str, payload: ProposalResolveRequest | None = None
    ) -> dict[str, Any]:
        return await _decide_proposal(
            proposal_id, ProposalDecision.ACCEPTED, payload.note if payload else ""
        )

    @router.post("/proposals/{proposal_id}/reject", response_model=None)
    async def reject_proposal(
        proposal_id: str, payload: ProposalResolveRequest | None = None
    ) -> dict[str, Any]:
        return await _decide_proposal(
            proposal_id, ProposalDecision.DECLINED, payload.note if payload else ""
        )

    @router.patch("/proposals/{proposal_id}/lifecycle", response_model=proposals_module.Proposal)
    async def update_proposal_lifecycle(
        proposal_id: str, payload: ProposalLifecycleRequest
    ) -> proposals_module.Proposal:
        """Explicit lifecycle override/reopen. Automatic reconciliation uses the same transition log."""
        with storage.transaction() as conn:
            proposal = proposals_module.transition_proposal(
                conn,
                proposal_id,
                payload.status,
                source="manual",
                detail=payload.note or f"Lifecycle set manually to {payload.status.value}",
            )
            audit(
                conn,
                AuditRecord(
                    entity_type="proposal",
                    entity_id=proposal_id,
                    action=f"proposal.lifecycle.{payload.status.value}",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"note": payload.note.strip()},
                ),
            )
        await bus.publish(
            event_name("review", "proposal_updated"),
            {"id": proposal_id, "status": proposal.status.value},
        )
        return proposal

    @router.post("/proposals/{proposal_id}/promote", response_model=None)
    async def promote_proposal(proposal_id: str) -> dict[str, Any]:
        """Accept + create a project backlog item + mark implementation in progress."""
        with storage.transaction() as conn:
            proposal = proposals_module.get_proposal(conn, proposal_id)
            if not proposal.project_id:
                raise invalid(
                    "proposal", "Only a project-scoped proposal can be promoted to a backlog item."
                )
            if proposal.resolution_note.startswith("Promoted to backlog item ") or any(
                e.source == "backlog" for e in proposal.lifecycle_evidence
            ):
                raise invalid("proposal", "This proposal has already been promoted to the backlog.")
            item = project_records.create_backlog_item(
                conn,
                proposal.project_id,
                ProjectBacklogItemCreate(
                    title=proposal.title,
                    body_md=(
                        proposal.rationale_md.strip()
                        + f"\n\n_Promoted from proposal {proposal.id}; keep this id in linked work so lifecycle detection can follow it._"
                    ).strip(),
                    source=AuditSource.DESKTOP,
                ),
            )
            decided = proposals_module.set_proposal_decision(
                conn,
                proposal_id,
                ProposalDecision.ACCEPTED,
                f"Promoted to backlog item {item.id}",
            )
            promoted = decided
            if decided.status != ProposalStatus.DONE:
                promoted = proposals_module.transition_proposal(
                    conn,
                    proposal_id,
                    ProposalStatus.IN_PROGRESS,
                    source="backlog",
                    detail=f"Promoted to project backlog item {item.id}",
                    ref_id=item.id,
                    evidence_status="open",
                )
            audit(
                conn,
                AuditRecord(
                    entity_type="proposal",
                    entity_id=proposal_id,
                    action="proposal.promoted",
                    source=AuditSource.DESKTOP,
                    result="success",
                    details={"backlog_item_id": item.id, "project_id": proposal.project_id},
                ),
            )
        await bus.publish(
            event_name("review", "proposal_updated"),
            {
                "id": proposal_id,
                "action": "promoted",
                "backlog_item_id": item.id,
                "status": promoted.status.value,
            },
        )
        return {
            "proposal": promoted.model_dump(mode="json"),
            "backlog_item": item.model_dump(mode="json"),
        }

    @router.get("/proposals/schema", response_model=None)
    async def proposal_schema() -> dict[str, Any]:
        """Compact machine-readable contract so a new AI can use the backlog without a playbook."""
        return {
            "purpose": (
                "Durable improvement backlog. decision records whether the idea is wanted; status records "
                "whether implementation work has happened. Do not use decision=accepted to mean done."
            ),
            "lifecycle": {
                "field": "status",
                "values": [item.value for item in ProposalStatus],
                "normal_flow": ["proposed", "in_progress", "done"],
                "auto_detection": (
                    "Reconcile can infer in_progress only from an active work item/session explicitly "
                    "referencing the proposal id, and done only from a commit line explicitly claiming "
                    "to fix/close/resolve/address/implement that id. Evidence is persisted."
                ),
            },
            "decision": {
                "field": "decision",
                "values": [item.value for item in ProposalDecision],
                "meaning": "pending=user has not decided; accepted=worth doing; declined=do not pursue",
            },
            "kinds": list(proposals_module.KNOWN_KINDS),
            "linking_convention": (
                "When beginning work on an existing proposal, include its exact proposal id in the work "
                "item/session task and in the completion commit message."
            ),
            "queries": {
                "list": "GET /api/v1/review/proposals?status=&decision=&kind=&project_id=&sort_by=&sort_dir=",
                "one": "GET /api/v1/review/proposals/{id}",
                "set_lifecycle": "PATCH /api/v1/review/proposals/{id}/lifecycle",
                "accept": "POST /api/v1/review/proposals/{id}/approve",
                "decline": "POST /api/v1/review/proposals/{id}/reject",
                "reconcile": "POST /api/v1/review/proposals/reconcile",
                "review_plan": "POST /api/v1/review/engine/plan/{project_id}",
                "queue_smart_review": "POST /api/v1/review/engine/queue/{project_id}",
            },
        }

    @router.get("/proposals", response_model=list[proposals_module.Proposal])
    async def list_review_proposals(
        status: ProposalStatus | None = Query(default=None),
        decision: ProposalDecision | None = Query(default=None),
        kind: str | None = Query(default=None),
        project_id: str | None = Query(default=None),
        sort_by: ProposalSort = Query(default=ProposalSort.UPDATED_AT),
        sort_dir: SortDirection = Query(default=SortDirection.DESC),
    ) -> list[proposals_module.Proposal]:
        return proposals_module.list_proposals(
            storage.conn,
            status,
            decision=decision,
            kind=kind,
            project_id=project_id,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

    @router.get("/proposals/{proposal_id}", response_model=proposals_module.Proposal)
    async def get_review_proposal(proposal_id: str) -> proposals_module.Proposal:
        return proposals_module.get_proposal(storage.conn, proposal_id)

    @router.post("/proposals/reconcile", response_model=None)
    async def reconcile_proposals_route() -> dict[str, Any]:
        """Refresh lifecycle from recent commits plus explicitly-linked active Synapse work."""
        from .runtime_paths import repo_root

        def read_recent_commits() -> list[str]:
            try:
                result = subprocess.run(
                    ["git", "log", "-n", "500", "--format=%h %s%n%b%x1e"],
                    cwd=str(repo_root()),
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            except Exception:  # noqa: BLE001 - reconciliation is best-effort
                return []
            if not result.stdout:
                return []
            return [chunk.strip() for chunk in result.stdout.split("\x1e") if chunk.strip()]

        commit_texts = await asyncio.to_thread(read_recent_commits)
        with storage.transaction() as conn:
            changed = proposals_module.reconcile_proposals(conn, commit_texts)
            for proposal in changed:
                audit(
                    conn,
                    AuditRecord(
                        entity_type="proposal",
                        entity_id=proposal.id,
                        action=f"proposal.reconciled.{proposal.status.value}",
                        source=AuditSource.AUTO,
                        result="success",
                        details={"lifecycle_source": proposal.lifecycle_source},
                    ),
                )
        for proposal in changed:
            await bus.publish(
                event_name("review", "proposal_updated"),
                {"id": proposal.id, "status": proposal.status.value},
            )
        payload = [p.model_dump(mode="json") for p in changed]
        # ``flagged`` remains as a response alias for clients written against the old route.
        return {"changed": payload, "flagged": payload, "count": len(changed)}

    return router
