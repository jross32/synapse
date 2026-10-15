from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime, timezone
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from stripe_payments import checkout_session, verified_webhook, StripeConfigurationError
from offer_catalog import OFFERS

from local_auth import (
    CSRF_HEADER_NAME,
    LocalSession,
    LocalSessionStore,
    build_session_cookie,
    clear_session_cookie,
    csrf_matches,
    read_session_token,
)
BASE_DIR = Path(__file__).resolve().parent
CONFIG = json.loads((BASE_DIR / "fast_money.config.json").read_text(encoding="utf-8"))
SEED_DATA = json.loads((BASE_DIR / "seed-data.json").read_text(encoding="utf-8"))
STATE_PATH = BASE_DIR / "workspace-state.json"
PORT = int(CONFIG.get("expected_port") or 8740)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class WorkflowStore:
    def __init__(self, path: Path, seed_data: dict[str, object]) -> None:
        self.path = path
        self.seed_data = seed_data
        self._lock = threading.RLock()

    def _new_state(self) -> dict[str, object]:
        return {
            "schema_version": 2,
            "workspace_id": "local-default",
            "updated_at": None,
            "data": copy.deepcopy(self.seed_data),
            "audit_log": [],
        }

    def _load_unlocked(self) -> dict[str, object]:
        if not self.path.exists():
            return self._new_state()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise ValueError("Workspace state is invalid.")
        payload["schema_version"] = max(int(payload.get("schema_version") or 1), 2)
        payload.setdefault("workspace_id", "local-default")
        payload.setdefault("updated_at", None)
        payload.setdefault("audit_log", [])
        return payload

    def load(self) -> dict[str, object]:
        with self._lock:
            return copy.deepcopy(self._load_unlocked())

    def _save_unlocked(self, state: dict[str, object]) -> None:
        state["schema_version"] = 2
        state["updated_at"] = utc_now()
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self.path)

    @staticmethod
    def _find(items: list[dict[str, object]], item_id: str) -> dict[str, object] | None:
        return next((item for item in items if item.get("id") == item_id), None)

    @staticmethod
    def _audit(
        state: dict[str, object],
        *,
        event_type: str,
        message: str,
        occurred_at: str,
        **links: object,
    ) -> None:
        event = {
            "id": f"audit-{uuid4().hex[:12]}",
            "type": event_type,
            "occurred_at": occurred_at,
            "message": message,
        }
        event.update({key: value for key, value in links.items() if value is not None})
        state.setdefault("audit_log", []).append(event)

    def approve_quote(self, quote_id: str) -> tuple[dict[str, object], dict[str, object]]:
        with self._lock:
            state = self._load_unlocked()
            data = state["data"]
            quotes = data.setdefault("quotes", [])
            quote = self._find(quotes, quote_id)
            if quote is None:
                raise KeyError("Quote not found.")

            leads = data.setdefault("leads", [])
            lead = self._find(leads, str(quote.get("lead_id") or ""))
            jobs = data.setdefault("jobs", [])
            job = next((item for item in jobs if item.get("quote_id") == quote_id), None)
            already_approved = quote.get("status") == "approved"

            if not already_approved:
                approved_at = utc_now()
                quote["status"] = "approved"
                quote["approved_at"] = approved_at
                if lead:
                    lead["stage"] = "approved"

                if job is None:
                    job = {
                        "id": f"job-{quote_id.replace('quote-', '')}",
                        "client": lead.get("company", "Client") if lead else "Client",
                        "status": "ready-to-schedule",
                        "owner": "Unassigned",
                        "next_step": "Schedule kickoff and assign owner",
                        "lead_id": quote.get("lead_id"),
                        "quote_id": quote_id,
                    }
                    jobs.append(job)

                self._audit(
                    state,
                    event_type="quote.approved",
                    occurred_at=approved_at,
                    quote_id=quote_id,
                    lead_id=quote.get("lead_id"),
                    job_id=job.get("id") if job else None,
                    message=f"{quote.get('package', 'Quote')} approved; kickoff is ready to schedule.",
                )
                self._save_unlocked(state)

            result = {
                "already_approved": already_approved,
                "quote_id": quote_id,
                "job_id": job.get("id") if job else None,
            }
            return copy.deepcopy(state), result

    def schedule_job(
        self,
        job_id: str,
        *,
        owner: str,
        scheduled_for: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        owner = owner.strip()
        scheduled_for = scheduled_for.strip()
        if not owner or len(owner) > 80:
            raise ValueError("Owner is required and must be 80 characters or fewer.")
        if not scheduled_for or len(scheduled_for) > 80:
            raise ValueError("A kickoff date and time is required.")
        try:
            datetime.fromisoformat(scheduled_for.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Kickoff date and time is invalid.") from error

        with self._lock:
            state = self._load_unlocked()
            data = state["data"]
            jobs = data.setdefault("jobs", [])
            job = self._find(jobs, job_id)
            if job is None:
                raise KeyError("Job not found.")
            if job.get("status") == "completed":
                raise ValueError("Completed jobs cannot be rescheduled.")

            same_schedule = (
                job.get("status") == "scheduled"
                and job.get("owner") == owner
                and job.get("scheduled_for") == scheduled_for
            )
            was_scheduled = job.get("status") == "scheduled"
            if not same_schedule:
                changed_at = utc_now()
                job["status"] = "scheduled"
                job["owner"] = owner
                job["scheduled_for"] = scheduled_for
                job["next_step"] = f"Kickoff scheduled for {scheduled_for}"
                self._audit(
                    state,
                    event_type="job.rescheduled" if was_scheduled else "job.scheduled",
                    occurred_at=changed_at,
                    job_id=job_id,
                    quote_id=job.get("quote_id"),
                    lead_id=job.get("lead_id"),
                    message=f"{job.get('client', 'Client')} kickoff scheduled for {scheduled_for} with {owner}.",
                )
                self._save_unlocked(state)

            return copy.deepcopy(state), {
                "already_scheduled": same_schedule,
                "rescheduled": was_scheduled and not same_schedule,
                "job_id": job_id,
            }

    def complete_job(self, job_id: str) -> tuple[dict[str, object], dict[str, object]]:
        with self._lock:
            state = self._load_unlocked()
            data = state["data"]
            jobs = data.setdefault("jobs", [])
            job = self._find(jobs, job_id)
            if job is None:
                raise KeyError("Job not found.")

            invoices = data.setdefault("invoices", [])
            existing_invoice = next(
                (
                    item
                    for item in invoices
                    if item.get("job_id") == job_id
                    or (
                        job.get("quote_id")
                        and item.get("quote_id") == job.get("quote_id")
                    )
                ),
                None,
            )
            already_completed = job.get("status") == "completed"
            if already_completed:
                return copy.deepcopy(state), {
                    "already_completed": True,
                    "job_id": job_id,
                    "invoice_id": existing_invoice.get("id") if existing_invoice else None,
                }
            if job.get("status") != "scheduled":
                raise ValueError("Schedule the job before marking it complete.")

            completed_at = utc_now()
            job["status"] = "completed"
            job["completed_at"] = completed_at
            job["next_step"] = "Send invoice"

            quotes = data.setdefault("quotes", [])
            quote = self._find(quotes, str(job.get("quote_id") or ""))
            leads = data.setdefault("leads", [])
            lead = self._find(leads, str(job.get("lead_id") or ""))
            if lead is None:
                lead = next(
                    (item for item in leads if item.get("company") == job.get("client")),
                    None,
                )
                if lead:
                    job["lead_id"] = lead.get("id")

            if existing_invoice is None:
                invoice_id = f"inv-{job_id.replace('job-', '')}"
                amount = int(
                    (quote or {}).get("amount_usd")
                    or (lead or {}).get("value_usd")
                    or 0
                )
                existing_invoice = {
                    "id": invoice_id,
                    "client": job.get("client", "Client"),
                    "status": "draft",
                    "amount_usd": amount,
                    "renewal_window_days": 30,
                    "renewal_status": "not-ready",
                    "next_step": "Send invoice",
                    "job_id": job_id,
                    "lead_id": job.get("lead_id"),
                    "quote_id": job.get("quote_id"),
                }
                invoices.append(existing_invoice)

            if lead:
                lead["stage"] = "delivered"

            self._audit(
                state,
                event_type="job.completed",
                occurred_at=completed_at,
                job_id=job_id,
                quote_id=job.get("quote_id"),
                lead_id=job.get("lead_id"),
                invoice_id=existing_invoice.get("id"),
                message=f"{job.get('client', 'Client')} delivery completed; invoice is ready to send.",
            )
            self._save_unlocked(state)

            return copy.deepcopy(state), {
                "already_completed": False,
                "job_id": job_id,
                "invoice_id": existing_invoice.get("id"),
            }

    def send_invoice(self, invoice_id: str) -> tuple[dict[str, object], dict[str, object]]:
        with self._lock:
            state = self._load_unlocked()
            data = state["data"]
            invoices = data.setdefault("invoices", [])
            invoice = self._find(invoices, invoice_id)
            if invoice is None:
                raise KeyError("Invoice not found.")

            status = invoice.get("status")
            if status == "paid":
                return copy.deepcopy(state), {
                    "already_sent": True,
                    "invoice_id": invoice_id,
                    "status": "paid",
                }
            if status == "sent":
                return copy.deepcopy(state), {
                    "already_sent": True,
                    "invoice_id": invoice_id,
                    "status": "sent",
                }
            if status != "draft":
                raise ValueError("Only draft invoices can be sent.")

            sent_at = utc_now()
            invoice["status"] = "sent"
            invoice["sent_at"] = sent_at
            invoice["next_step"] = "Await payment"
            self._audit(
                state,
                event_type="invoice.sent",
                occurred_at=sent_at,
                invoice_id=invoice_id,
                job_id=invoice.get("job_id"),
                quote_id=invoice.get("quote_id"),
                lead_id=invoice.get("lead_id"),
                message=f"Invoice {invoice_id} sent to {invoice.get('client', 'client')}.",
            )
            self._save_unlocked(state)
            return copy.deepcopy(state), {
                "already_sent": False,
                "invoice_id": invoice_id,
                "status": "sent",
            }

    def bind_checkout(self, invoice_id, checkout):
        sid = str(checkout.get("id") or "")
        if not sid.startswith("cs_test_") or not str(checkout.get("url") or "").startswith("https://"):
            raise ValueError("Invalid sandbox checkout")
        with self._lock:
            state = self._load_unlocked()
            invoice = self._find(state["data"]["invoices"], invoice_id)
            if invoice is None or invoice.get("status") != "sent":
                raise ValueError("Invoice not eligible")
            ids = invoice.setdefault("checkout_session_ids", [])
            if sid not in ids:
                ids.append(sid)
                self._save_unlocked(state)

    def confirm_stripe_payment(self, event: dict[str, object]) -> dict[str, object]:
        if event.get("livemode") is not False:
            raise ValueError("Only Stripe sandbox events are accepted.")
        if event.get("type") not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            return {"ignored": True}
        session = event.get("data", {}).get("object", {})
        if not isinstance(session, dict) or session.get("payment_status") != "paid":
            return {"ignored": True}
        invoice_id = str(session.get("client_reference_id") or "")
        metadata = session.get("metadata") or {}
        if not isinstance(metadata, dict) or metadata.get("invoice_id") != invoice_id:
            raise ValueError("Stripe invoice metadata mismatch.")
        if session.get("currency") != "usd":
            raise ValueError("Unexpected Stripe currency.")
        if not str(session.get("id") or "").startswith("cs_"):
            raise ValueError("Invalid Stripe checkout session.")
        with self._lock:
            state = self._load_unlocked()
            invoice = self._find(state["data"].setdefault("invoices", []), invoice_id)
            if invoice is None:
                raise KeyError("Invoice not found.")
            if invoice.get("status") not in ("sent", "paid"):
                raise ValueError("Invoice must be sent before payment confirmation.")
            if session["id"] not in invoice.get("checkout_session_ids", []):
                raise ValueError("Unknown checkout session")
            expected = int(invoice.get("amount_usd") or 0) * 100
            if expected <= 0 or session.get("amount_total") != expected:
                raise ValueError("Stripe payment amount does not match invoice.")
            event_id = str(event.get("id") or "")
            seen = state.setdefault("stripe_event_ids", [])
            if event_id in seen:
                return {"duplicate": True, "invoice_id": invoice_id}
            if invoice.get("status") == "paid":
                if invoice.get("stripe_session_id") != session["id"] or not invoice.get("payment_verified"):
                    raise ValueError("Invoice paid by another method or session.")
                seen.append(event_id)
                self._save_unlocked(state)
                return {"duplicate": True, "invoice_id": invoice_id}
            invoice["status"] = "paid"
            invoice["payment_verified"] = True
            invoice["stripe_session_id"] = session["id"]
            invoice["stripe_payment_intent"] = session.get("payment_intent")
            invoice["paid_at"] = utc_now()
            invoice["renewal_status"] = "ready"
            invoice["next_step"] = "Payment verified; arrange fulfillment"
            lead = self._find(state["data"].setdefault("leads", []), str(invoice.get("lead_id") or ""))
            if lead:
                lead["stage"] = "active-client"
            seen.append(event_id)
            self._audit(state,event_type="invoice.stripe_verified",occurred_at=utc_now(),
                        invoice_id=invoice_id,lead_id=invoice.get("lead_id"),
                        message="Stripe verified payment received.")
            self._save_unlocked(state)
            return {"verified": True, "invoice_id": invoice_id}



WORKFLOW_STORE = WorkflowStore(STATE_PATH, SEED_DATA)
SESSION_STORE = LocalSessionStore()


def workspace_for_session(session: LocalSession) -> dict[str, object]:
    state = WORKFLOW_STORE.load()
    if session.role == "operator":
        return state

    lead_id = session.lead_id
    data = state.get("data", {})
    leads = [item for item in data.get("leads", []) if item.get("id") == lead_id]
    quotes = [item for item in data.get("quotes", []) if item.get("lead_id") == lead_id]
    quote_ids = {item.get("id") for item in quotes}
    jobs = [
        item
        for item in data.get("jobs", [])
        if item.get("lead_id") == lead_id or item.get("quote_id") in quote_ids
    ]
    job_ids = {item.get("id") for item in jobs}
    invoices = [
        item
        for item in data.get("invoices", [])
        if (
            item.get("lead_id") == lead_id
            or item.get("quote_id") in quote_ids
            or item.get("job_id") in job_ids
        )
    ]

    scoped = copy.deepcopy(state)
    scoped["data"] = {
        "leads": leads,
        "quotes": quotes,
        "jobs": jobs,
        "invoices": invoices,
        "catalog": [],
    }
    scoped["audit_log"] = []
    return scoped


def nav_items() -> list[tuple[str, str]]:
    items = [
        ("/", "Overview"),
        ("/pricing", "Pricing"),
        ("/signin", "Sign in"),
    ]
    if CONFIG.get("include_customer_portal", True):
        items.append(("/portal", "Customer portal"))
    if CONFIG.get("include_employee_console", True):
        items.append(("/ops", "Operator console"))
    items.append(("/catalog", "Catalog"))
    return items


def page_shell(title: str, body: str, *, page_id: str) -> str:
    links = "".join(
        f'<a href="{href}" class="nav-link">{"%s" % escape(label)}</a>'
        for href, label in nav_items()
    )
    app_name = escape(str(CONFIG.get("app_name") or "Fast Money"))
    config_json = json.dumps(CONFIG)
    data_json = json.dumps(SEED_DATA)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)} - {app_name}</title>
    <link rel="stylesheet" href="/static/styles.css">
  </head>
  <body data-page="{escape(page_id)}">
    <div class="backdrop"></div>
    <header class="topbar">
      <div>
        <p class="eyebrow">Synapse Fast Money</p>
        <h1>{app_name}</h1>
      </div>
      <nav class="nav">{links}</nav>
    </header>
    <main class="frame">
      {body}
    </main>
    <script>
      window.FAST_MONEY_CONFIG = {config_json};
      window.FAST_MONEY_DATA = {data_json};
    </script>
    <script src="/static/auth.js"></script>
    <script src="/static/app.js"></script>
  </body>
</html>"""


def money(value: int) -> str:
    return "$" + f"{value:,.0f}"


def landing_page() -> str:
    total_pipeline = sum(item["value_usd"] for item in SEED_DATA["leads"])
    return f"""
    <section class="hero">
      <div>
        <p class="eyebrow">Private/local-first client ops SaaS</p>
        <h2>Quotes, approvals, jobs, invoices, and renewals in one workspace.</h2>
        <p class="lede">
          Turn service-business pipeline into predictable recurring revenue with a customer portal,
          operator console, and pricing hooks that can grow with AI-heavy workflows.
        </p>
        <div class="cta-row">
          <a class="button primary" href="/pricing">See pricing</a>
          <a class="button ghost" href="/portal">View portal</a>
        </div>
      </div>
      <aside class="hero-card">
        <p class="card-label">Pipeline under management</p>
        <p class="hero-value">{money(total_pipeline)}</p>
        <p class="muted">2 live leads, 1 scheduled job, 1 draft invoice</p>
      </aside>
    </section>
    <section class="grid two-up">
      <article class="panel">
        <p class="card-label">Core workflow</p>
        <h3>Lead -> quote -> approval -> job -> invoice -> renewal</h3>
        <p class="muted">
          The starter keeps the entire money path visible so a future AI pass can deepen each stage
          without rebuilding the product story from scratch.
        </p>
      </article>
      <article class="panel">
        <p class="card-label">Billing-ready seam</p>
        <h3>Hybrid pricing by default</h3>
        <p class="muted">
          Base subscription for the workspace, then usage/overage for AI-heavy actions such as quote
          drafting, lead enrichment, and renewal nudges.
        </p>
      </article>
    </section>
    <section class="grid three-up">
      <article class="panel">
        <p class="card-label">Customer portal</p>
        <h3>Fewer Ã¢â‚¬Å“where are we?Ã¢â‚¬Â emails</h3>
        <p class="muted">Clients can see quotes, approvals, jobs, invoices, and renewal timing in one place.</p>
      </article>
      <article class="panel">
        <p class="card-label">Operator console</p>
        <h3>Pipeline with actions</h3>
        <p class="muted">Work leads, monitor job load, and keep invoicing and renewals from slipping.</p>
      </article>
      <article class="panel">
        <p class="card-label">Catalog control</p>
        <h3>Editable packages and services</h3>
        <p class="muted">The catalog editor shell is ready when this business needs packaged offers.</p>
      </article>
    </section>
    """


def pricing_page() -> str:
    return """
    <section class="hero compact">
      <div>
        <p class="eyebrow">Pricing</p>
        <h2>Designed for recurring revenue, not one-off setup fees.</h2>
        <p class="lede">
          Start with a clean monthly subscription, then let AI-heavy or high-volume work float on top.
        </p>
      </div>
    </section>
    <section class="grid three-up">
      <article class="panel price-card">
        <p class="card-label">Starter</p>
        <h3>$149/mo</h3>
        <p class="muted">1 team, portal access, quote tracking, invoice reminders.</p>
      </article>
      <article class="panel price-card featured">
        <p class="card-label">Growth</p>
        <h3>$349/mo</h3>
        <p class="muted">Ops console, catalog controls, team workflows, AI drafting credits.</p>
      </article>
      <article class="panel price-card">
        <p class="card-label">Scale</p>
        <h3>Custom</h3>
        <p class="muted">Higher usage ceilings, white-label portal polish, and deeper billing adapters.</p>
      </article>
    </section>
    <section class="panel">
      <p class="card-label">Usage seam</p>
      <h3>Charge for the expensive part honestly.</h3>
      <p class="muted">
        AI-heavy actions such as lead enrichment, quote generation, and renewal-risk scans should map to
        metered usage instead of being hidden inside flat seat pricing.
      </p>
    </section>
    """


def signin_page() -> str:
    return """
    <section class="hero compact">
      <div>
        <p class="eyebrow">Local sessions</p>
        <h2>Choose a customer or operator session.</h2>
        <p class="lede">
          The reference app now keeps opaque server-side sessions and enforces role boundaries
          around workflow data and mutations while remaining private to localhost.
        </p>
      </div>
    </section>
    <section class="panel auth-card">
      <p class="card-label">Local demo identity</p>
      <h3>Start an isolated role session</h3>
      <p class="muted">
        Customer is scoped to Erin Stone at Northline HVAC. Operator can manage jobs, invoices,
        and the full workspace.
      </p>
      <div class="local-role-grid">
        <button class="button primary" type="button" data-local-role="customer">
          Continue as customer
        </button>
        <button class="button ghost" type="button" data-local-role="operator">
          Continue as operator
        </button>
      </div>
      <p id="signin-status" class="status-message" role="status" aria-live="polite"></p>
      <p class="muted security-note">
        This is local role separation, not production identity verification. Role choice is open
        because the server binds only to 127.0.0.1; replace it with a real identity provider before
        hosting or exposing the app to other devices.
      </p>
    </section>
    """

def portal_page() -> str:
    return """
    <section class="session-strip" aria-label="Current local session">
      <span>Signed in as <strong data-session-label>Loading session...</strong></span>
      <button class="button ghost small" type="button" data-signout>Sign out</button>
    </section>    <section class="hero compact">
      <div>
        <p class="eyebrow">Customer portal</p>
        <h2>Your customers can see status without asking for an update.</h2>
      </div>
    </section>
    <section class="grid two-up">
      <article class="panel">
        <p class="card-label">My quotes</p>
        <div id="portal-quotes" class="stack"></div>
      </article>
      <article class="panel">
        <p class="card-label">Jobs & invoicing</p>
        <div id="portal-jobs" class="stack"></div>
      </article>
    </section>
    """


def ops_page() -> str:
    return """
    <section class="session-strip" aria-label="Current local session">
      <span>Signed in as <strong data-session-label>Loading session...</strong></span>
      <button class="button ghost small" type="button" data-signout>Sign out</button>
    </section>    <section class="hero compact">
      <div>
        <p class="eyebrow">Operator console</p>
        <h2>Run the revenue engine from one board.</h2>
        <p id="ops-status" class="status-message" role="status" aria-live="polite"></p>
      </div>
    </section>
    <section class="panel">
      <p class="card-label">Sales dashboard â€” evidence and conversion</p>
      <div id="client-hunter-board" aria-live="polite">Loading Client Hunter readiness...</div>
      <div id="sales-pipeline-board" aria-live="polite">Loading company pipeline...</div>
    </section>
    <script src="/static/sales_dashboard.js" defer></script>
    <section class="grid two-up">
      <article class="panel">
        <p class="card-label">Lead pipeline</p>
        <div id="ops-leads" class="stack"></div>
      </article>
      <article class="panel">
        <p class="card-label">Job delivery</p>
        <div id="ops-jobs" class="stack"></div>
      </article>
    </section>
    <section class="panel">
      <p class="card-label">Invoices & renewals</p>
      <div id="ops-invoices" class="stack"></div>
    </section>
    <section class="panel">
      <p class="card-label">Workflow audit trail</p>
      <div id="ops-audit" class="stack"></div>
    </section>
    """


def catalog_page() -> str:
    if not CONFIG.get("include_catalog_editor", False):
        return """
        <section class="hero compact">
          <div>
            <p class="eyebrow">Catalog editor</p>
            <h2>Catalog editing is disabled in this brief.</h2>
            <p class="lede">
              The route is here so the product can grow into editable packages and services when needed.
            </p>
          </div>
        </section>
        """
    return """
    <section class="hero compact">
      <div>
        <p class="eyebrow">Catalog editor</p>
        <h2>Package and price the offers your team sells.</h2>
      </div>
    </section>
    <section class="panel">
      <div id="catalog-items" class="grid three-up"></div>
    </section>
    """


PAGES = {
    "/": ("Overview", "overview", landing_page),
    "/pricing": ("Pricing", "pricing", pricing_page),
    "/signin": ("Sign in", "signin", signin_page),
    "/portal": ("Customer portal", "portal", portal_page),
    "/ops": ("Operator console", "ops", ops_page),
    "/catalog": ("Catalog", "catalog", catalog_page),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path or "/"

        if path == "/health":
            self._json({"ok": True, "app": CONFIG.get("app_name"), "port": PORT})
            return

        if path == "/api/sales/offers":
            session = self._require_session("operator")
            if session is None:
                return
            self._json({"ok": True, "offers": [offer.public_summary() for offer in OFFERS.values()]},
                       cache_control="no-store")
            return

        if path == "/api/client-hunter/latest-run":
            session = self._require_session("operator")
            if session is None:
                return
            report = BASE_DIR / "files" / "client-hunter-latest-run.json"
            if not report.is_file():
                self._json({"ok": False, "error": "No Client Hunter dry run recorded"},
                           status=HTTPStatus.NOT_FOUND, cache_control="no-store")
                return
            try:
                self._json({"ok": True, "report": json.loads(report.read_text(encoding="utf-8-sig"))},
                           cache_control="no-store")
            except (OSError, ValueError, json.JSONDecodeError):
                self._json({"ok": False, "error": "Client Hunter run report unreadable"},
                           status=HTTPStatus.INTERNAL_SERVER_ERROR, cache_control="no-store")
            return
        if path == "/api/client-hunter/readiness":
            session = self._require_session("operator")
            if session is None:
                return
            try:
                from files.client_hunter_readiness import readiness
                self._json({"ok": True, **readiness()}, cache_control="no-store")
            except (OSError, ValueError, json.JSONDecodeError) as error:
                self._json({"ok": False, "error": "Client Hunter readiness unavailable"},
                           status=HTTPStatus.INTERNAL_SERVER_ERROR, cache_control="no-store")
            return
        if path == "/api/stripe/status":
            session = self._require_session("operator")
            if session is None:
                return
            self._json({"ok": True, "test_key_configured": os.environ.get("STRIPE_SECRET_KEY", "").startswith("sk_test_"),
                        "webhook_configured": os.environ.get("STRIPE_WEBHOOK_SECRET", "").startswith("whsec_"),
                        "mode": "test-only"}, cache_control="no-store")
            return

        if path == "/api/session":
            session = self._current_session()
            self._json(
                {
                    "ok": True,
                    "authenticated": session is not None,
                    "session": session.public(include_csrf=True) if session else None,
                },
                cache_control="no-store",
            )
            return

        if path == "/api/demo-data":
            session = self._require_session("operator")
            if session is None:
                return
            self._json(SEED_DATA, cache_control="no-store")
            return

        if path == "/api/workspace-state":
            session = self._require_session()
            if session is None:
                return
            try:
                self._json(workspace_for_session(session), cache_control="no-store")
            except (OSError, ValueError, json.JSONDecodeError) as error:
                self._json(
                    {"ok": False, "error": str(error)},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return

        if path == "/static/styles.css":
            self._file(BASE_DIR / "static" / "styles.css", "text/css; charset=utf-8")
            return
        if path == "/static/auth.js":
            self._file(
                BASE_DIR / "static" / "auth.js",
                "application/javascript; charset=utf-8",
            )
            return
        if path == "/static/sales_dashboard.js":
            session = self._require_session("operator")
            if session is None:
                return
            self._file(BASE_DIR / "static" / "sales_dashboard.js", "application/javascript; charset=utf-8")
            return
        if path == "/static/app.js":
            self._file(
                BASE_DIR / "static" / "app.js",
                "application/javascript; charset=utf-8",
            )
            return

        if path in PAGES:
            required_role = {
                "/portal": "customer",
                "/ops": "operator",
                "/catalog": "operator",
            }.get(path)
            if required_role:
                session = self._current_session()
                if session is None or session.role != required_role:
                    self._redirect("/signin")
                    return
            title, page_id, renderer = PAGES[path]
            self._html(page_shell(title, renderer(), page_id=page_id))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Page not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path or "/"
        parts = [part for part in path.split("/") if part]

        try:
            if path == "/api/stripe/webhook":
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 262144:
                    raise ValueError("Invalid webhook body size.")
                raw = self.rfile.read(length)
                event = verified_webhook(raw, self.headers.get("Stripe-Signature", ""))
                result = WORKFLOW_STORE.confirm_stripe_payment(event)
                self._json({"ok": True, "result": result}, cache_control="no-store")
                return

            if len(parts) == 4 and parts[:2] == ["api", "invoices"] and parts[3] == "checkout":
                session = self._require_session("operator", require_csrf=True)
                if session is None:
                    return
                current = WORKFLOW_STORE.load()
                invoice = WorkflowStore._find(current["data"].get("invoices", []), parts[2])
                if invoice is None:
                    raise KeyError("Invoice not found.")
                if invoice.get("status") != "sent":
                    raise ValueError("Only sent invoices can be checked out.")
                amount = int(invoice.get("amount_usd") or 0) * 100
                base = os.environ.get("STRIPE_CHECKOUT_RETURN_ORIGIN", "")
                if not base.startswith("https://"):
                    raise StripeConfigurationError("Configure HTTPS checkout return origin.")
                checkout = checkout_session(invoice_id=parts[2], amount_cents=amount,
                    success_url=base.rstrip("/") + "/portal?checkout=success",
                    cancel_url=base.rstrip("/") + "/portal?checkout=cancel")
                WORKFLOW_STORE.bind_checkout(parts[2], checkout)
                self._json({"ok": True, "checkout_url": checkout.get("url"), "checkout_session_id": checkout.get("id")},
                           cache_control="no-store")
                return

            if path == "/api/client-hunter/run":
                session = self._require_session("operator", require_csrf=True)
                if session is None:
                    return
                from files.client_hunter_execution import execute_once
                result = execute_once()
                self._json(result, status=HTTPStatus.CONFLICT if result.get("busy") else HTTPStatus.OK,
                           cache_control="no-store")
                return
            if path == "/api/session/login":
                body = self._json_body()
                role = str(body.get("role") or "").strip()
                previous_token = read_session_token(self.headers.get("Cookie"))
                SESSION_STORE.delete(previous_token)
                session = SESSION_STORE.create(role)
                self._json(
                    {"ok": True, "session": session.public(include_csrf=True)},
                    cache_control="no-store",
                    headers={"Set-Cookie": build_session_cookie(session.token)},
                )
                return

            if path == "/api/session/logout":
                session = self._require_session(require_csrf=True)
                if session is None:
                    return
                token = read_session_token(self.headers.get("Cookie"))
                SESSION_STORE.delete(token)
                self._json(
                    {"ok": True},
                    cache_control="no-store",
                    headers={"Set-Cookie": clear_session_cookie()},
                )
                return

            if (
                len(parts) == 4
                and parts[:2] == ["api", "quotes"]
                and parts[3] == "approve"
            ):
                session = self._require_session("customer", require_csrf=True)
                if session is None:
                    return
                current = WORKFLOW_STORE.load()
                quote = WorkflowStore._find(
                    current.get("data", {}).get("quotes", []),
                    parts[2],
                )
                if quote is None:
                    raise KeyError("Quote not found.")
                if quote.get("lead_id") != session.lead_id:
                    self._json(
                        {
                            "ok": False,
                            "error": "That quote is outside this customer session.",
                        },
                        status=HTTPStatus.FORBIDDEN,
                    )
                    return
                state, result = WORKFLOW_STORE.approve_quote(parts[2])
                self._workflow_json(state, result, session)
                return

            if (
                len(parts) == 4
                and parts[:2] == ["api", "jobs"]
                and parts[3] == "schedule"
            ):
                session = self._require_session("operator", require_csrf=True)
                if session is None:
                    return
                body = self._json_body()
                state, result = WORKFLOW_STORE.schedule_job(
                    parts[2],
                    owner=str(body.get("owner") or ""),
                    scheduled_for=str(body.get("scheduled_for") or ""),
                )
                self._workflow_json(state, result, session)
                return

            if (
                len(parts) == 4
                and parts[:2] == ["api", "jobs"]
                and parts[3] == "complete"
            ):
                session = self._require_session("operator", require_csrf=True)
                if session is None:
                    return
                state, result = WORKFLOW_STORE.complete_job(parts[2])
                self._workflow_json(state, result, session)
                return

            if (
                len(parts) == 4
                and parts[:2] == ["api", "invoices"]
                and parts[3] == "send"
            ):
                session = self._require_session("operator", require_csrf=True)
                if session is None:
                    return
                state, result = WORKFLOW_STORE.send_invoice(parts[2])
                self._workflow_json(state, result, session)
                return

            if (
                len(parts) == 4
                and parts[:2] == ["api", "invoices"]
                and parts[3] == "mark-paid"
            ):
                session = self._require_session("operator", require_csrf=True)
                if session is None:
                    return
                self._json(
                    {"ok": False, "error": "Manual payment confirmation is disabled. A verified payment-provider webhook is required."},
                    status=HTTPStatus.CONFLICT,
                    cache_control="no-store",
                )
                return
        except StripeConfigurationError:
            self._json({"ok": False, "error": "Stripe sandbox configuration incomplete."},
                       status=HTTPStatus.SERVICE_UNAVAILABLE, cache_control="no-store")
            return
        except KeyError as error:
            self._json(
                {"ok": False, "error": error.args[0]},
                status=HTTPStatus.NOT_FOUND,
            )
            return
        except ValueError as error:
            self._json(
                {"ok": False, "error": str(error)},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        except (OSError, json.JSONDecodeError) as error:
            self._json(
                {"ok": False, "error": str(error)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self._json(
            {"ok": False, "error": "Route not found."},
            status=HTTPStatus.NOT_FOUND,
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _current_session(self) -> LocalSession | None:
        token = read_session_token(self.headers.get("Cookie"))
        return SESSION_STORE.get(token)

    def _require_session(
        self,
        role: str | None = None,
        *,
        require_csrf: bool = False,
    ) -> LocalSession | None:
        session = self._current_session()
        if session is None:
            self._json(
                {"ok": False, "error": "Sign in to continue."},
                status=HTTPStatus.UNAUTHORIZED,
                cache_control="no-store",
            )
            return None
        if role and session.role != role:
            label = "Operator" if role == "operator" else "Customer"
            self._json(
                {"ok": False, "error": f"{label} access is required."},
                status=HTTPStatus.FORBIDDEN,
                cache_control="no-store",
            )
            return None
        if require_csrf and not csrf_matches(
            session,
            self.headers.get(CSRF_HEADER_NAME),
        ):
            self._json(
                {
                    "ok": False,
                    "error": "Request verification failed. Refresh and try again.",
                },
                status=HTTPStatus.FORBIDDEN,
                cache_control="no-store",
            )
            return None
        return session

    def _json_body(self) -> dict[str, object]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValueError("Invalid request length.") from error
        if length <= 0:
            return {}
        if length > 16_384:
            raise ValueError("Request body is too large.")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Request body must be valid JSON.") from error
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def _workflow_json(
        self,
        state: dict[str, object],
        result: dict[str, object],
        session: LocalSession,
    ) -> None:
        payload_state = (
            state if session.role == "operator" else workspace_for_session(session)
        )
        self._json(
            {"ok": True, "result": result, "workspace": payload_state},
            cache_control="no-store",
        )

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _html(self, payload: str) -> None:
        data = payload.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(
        self,
        payload: object,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        cache_control: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Fast Money reference app running on http://127.0.0.1:{PORT}")
    server.serve_forever()
