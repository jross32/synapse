"""Deterministic, read-only booking and follow-up suggestions; never sends messages."""
from __future__ import annotations


def plan_actions(workspace: dict) -> list[dict]:
    data = workspace.get("data", {})
    leads = {str(x.get("id")): x for x in data.get("leads", [])}
    actions: list[dict] = []
    for quote in data.get("quotes", []):
        if quote.get("status") == "sent":
            lead = leads.get(str(quote.get("lead_id")), {})
            actions.append({
                "id": f"quote:{quote['id']}", "kind": "quote_follow_up",
                "title": f"Review quote with {lead.get('company', 'customer')}",
                "draft": "Hello, following up on your quote. Would you like to review it or request a change?",
                "approval_required": True, "send_enabled": False,
            })
    for job in data.get("jobs", []):
        status = job.get("status")
        if status not in ("pending", "ready", "unscheduled", "scheduled"):
            continue
        scheduled_for = job.get("scheduled_for")
        if status == "scheduled" and scheduled_for:
            actions.append({
                "id": f"booking:{job['id']}", "kind": "booking_confirmation",
                "title": f"Review booking for {job.get('client', 'customer')}",
                "draft": f"Hello, your appointment is proposed for {scheduled_for}. Please confirm the details.",
                "approval_required": True, "send_enabled": False,
            })
        else:
            actions.append({
                "id": f"booking:{job['id']}", "kind": "booking_request",
                "title": f"Schedule {job.get('client', 'customer')}",
                "draft": "Hello, we are ready to arrange your appointment. What dates and times work for you?",
                "approval_required": True, "send_enabled": False,
            })
    for invoice in data.get("invoices", []):
        if invoice.get("status") == "sent":
            actions.append({
                "id": f"invoice:{invoice['id']}", "kind": "invoice_follow_up",
                "title": f"Review invoice for {invoice.get('client', 'customer')}",
                "draft": "Hello, your invoice is available for review. Please contact us with any questions.",
                "approval_required": True, "send_enabled": False,
            })
    return actions
