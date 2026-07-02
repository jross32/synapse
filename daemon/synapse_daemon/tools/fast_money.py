"""Fast Money -- a built-in Synapse launcher for monetizable app creation.

The tool does three things in one action:

1. Ensures the reusable Fast Money AI bundle is installed.
2. Ensures a runnable local reference app project exists on disk.
3. Opens an AI PTY session in that project with a tailored prompt.

This keeps the operational surface simple for the user while staying inside
Synapse's existing tool + bundle + PTY architecture.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .. import ai_bundles
from .. import projects as projects_module
from ..api_versions import event_name
from ..health import HealthProbe
from ..models import EntityStatus, ErrorRef, ToolState
from ..projects import Project, ProjectKind, ProjectUpdate
from ..runtime_resolution import resolve_command
from ..storage import Storage
from ..ws import EventBus
from . import ToolHandler

_DEFAULT_APP_NAME = "Fast Money Client Ops"
_DEFAULT_PROJECT_ID = "fast-money-client-ops"
_DEFAULT_PORT = 8740
_BUNDLE_ID = "fast-money"
_RUNTIME_ORDER = ("codex", "claude", "copilot")
_ID_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str, *, fallback: str) -> str:
    lowered = (value or "").strip().lower()
    cleaned = _ID_RE.sub("-", lowered).strip("-")
    if not cleaned:
        return fallback
    if not cleaned[0].isalpha():
        cleaned = f"a-{cleaned}"
    return cleaned


def _bool_field(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
    return default


def _text_field(value: Any, *, default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


class FastMoneyTool(ToolHandler):
    tool_id = "fast-money"

    def __init__(self, bus: EventBus, storage: Storage | None = None) -> None:
        self._bus = bus
        self._storage = storage
        self._state = ToolState(tool_id=self.tool_id, status=EntityStatus.IDLE)

    def state(self) -> ToolState:
        return self._state

    async def run_action(
        self, action_id: str, fields: dict[str, Any], item_id: str | None = None
    ) -> ToolState:
        if action_id != "launch":
            self._state = ToolState(
                tool_id=self.tool_id,
                status=EntityStatus.ERROR,
                fields=fields or {},
                last_error=ErrorRef(
                    code="fast-money.unknown_action",
                    message=f"Fast Money has no action '{action_id}'.",
                ),
            )
            return self._state
        return await self._launch(fields or {})

    async def _launch(self, fields: dict[str, Any]) -> ToolState:
        if self._storage is None:
            self._state = ToolState(
                tool_id=self.tool_id,
                status=EntityStatus.ERROR,
                fields=fields,
                last_error=ErrorRef(
                    code="fast-money.unavailable",
                    message="Fast Money needs daemon storage to create the project scaffold.",
                ),
            )
            return self._state

        manager = getattr(self._bus, "_pty_manager", None)
        if manager is None:
            self._state = ToolState(
                tool_id=self.tool_id,
                status=EntityStatus.ERROR,
                fields=fields,
                last_error=ErrorRef(
                    code="fast-money.unavailable",
                    message="Fast Money needs a PTY session manager wired into the daemon.",
                ),
            )
            return self._state

        normalized = self._normalize_fields(fields)
        runtime_choice = self._choose_runtime(normalized["preferred_runtime"])
        if runtime_choice is None:
            wanted = normalized["preferred_runtime"]
            message = (
                "No supported AI runtime is available. Install one of codex, claude, or copilot,"
                " or choose a command that Synapse can resolve."
                if wanted == "auto"
                else f"Preferred runtime '{wanted}' is not available. Install it or choose auto."
            )
            self._state = ToolState(
                tool_id=self.tool_id,
                status=EntityStatus.ERROR,
                fields=normalized,
                last_error=ErrorRef(
                    code="fast-money.runtime_unavailable",
                    message=message,
                ),
            )
            return self._state

        self._ensure_bundle_installed()
        project_path = self._resolve_project_path(normalized["output_path"])
        project, created = self._ensure_project(project_path, normalized)
        written = self._ensure_reference_scaffold(
            project_path=project_path,
            project=project,
            normalized=normalized,
        )

        prompt = self._build_prompt(project, normalized)
        brief = self._build_brief(project, normalized)
        prompt_path = project_path / "PROMPT.md"
        brief_path = project_path / "FAST_MONEY_BRIEF.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        brief_path.write_text(brief, encoding="utf-8")

        env = {
            "SYNAPSE_FAST_MONEY_APP_NAME": normalized["app_name"],
            "SYNAPSE_FAST_MONEY_BRIEF_FILE": str(brief_path),
            "SYNAPSE_FAST_MONEY_PROMPT_FILE": str(prompt_path),
            "SYNAPSE_FAST_MONEY_BUNDLE_ID": _BUNDLE_ID,
            "SYNAPSE_FAST_MONEY_PRICING_MODEL": normalized["pricing_model"],
        }
        session = await manager.spawn(
            argv=[runtime_choice],
            cwd=str(project_path),
            env=env,
            project_id=project.id,
        )
        summary = session.summary()
        result = {
            "session_id": summary.session_id,
            "project_id": project.id,
            "project_path": str(project_path),
            "bundle_id": _BUNDLE_ID,
            "chosen_runtime": runtime_choice,
            "prompt_file": str(prompt_path),
            "brief_file": str(brief_path),
            "reference_app_port": project.expected_port,
            "reference_app_created": created,
            "scaffolded_files": sorted(str(path.relative_to(project_path)) for path in written),
        }
        await self._bus.publish(
            event_name("tool", "fast_money_launched"),
            {
                "tool_id": self.tool_id,
                "project_id": project.id,
                "session_id": summary.session_id,
                "runtime": runtime_choice,
            },
        )
        self._state = ToolState(
            tool_id=self.tool_id,
            status=EntityStatus.LAUNCHED,
            fields=normalized,
            result=result,
            message=f"Opened Fast Money in {runtime_choice} for project '{project.name}'.",
        )
        return self._state

    def _normalize_fields(self, fields: dict[str, Any]) -> dict[str, Any]:
        return {
            "app_name": _text_field(fields.get("app_name"), default=_DEFAULT_APP_NAME),
            "brief": _text_field(
                fields.get("brief"),
                default=(
                    "Build a private/local-first client-ops SaaS for service businesses "
                    "that turns leads into quotes, approvals, jobs, invoices, and renewals."
                ),
            ),
            "output_path": str(fields.get("output_path") or "").strip(),
            "pricing_model": _text_field(fields.get("pricing_model"), default="hybrid"),
            "include_customer_portal": _bool_field(
                fields.get("include_customer_portal"), default=True
            ),
            "include_employee_console": _bool_field(
                fields.get("include_employee_console"), default=True
            ),
            "include_catalog_editor": _bool_field(
                fields.get("include_catalog_editor"), default=False
            ),
            "preferred_runtime": _text_field(
                fields.get("preferred_runtime"), default="auto"
            ).lower(),
        }

    def _choose_runtime(self, preferred_runtime: str) -> str | None:
        preferred = (preferred_runtime or "auto").strip().lower()
        if preferred in {"", "auto"}:
            for candidate in _RUNTIME_ORDER:
                if resolve_command(candidate):
                    return candidate
            return None
        return preferred if resolve_command(preferred) else None

    def _resolve_project_path(self, output_path: str) -> Path:
        if output_path.strip():
            candidate = Path(output_path).expanduser()
            if not candidate.is_absolute():
                candidate = self._storage.data_dir / "projects" / candidate
            return candidate.resolve()
        return (self._storage.data_dir / "projects" / _DEFAULT_PROJECT_ID).resolve()

    def _ensure_bundle_installed(self) -> None:
        with self._storage.transaction() as conn:
            installed = set(ai_bundles.list_installed_bundle_ids(conn))
            if _BUNDLE_ID in installed:
                return
            ai_bundles.install_bundle(
                conn,
                self._storage.data_dir,
                ai_bundles.bundle_by_id(_BUNDLE_ID),
            )

    def _ensure_project(
        self,
        project_path: Path,
        normalized: dict[str, Any],
    ) -> tuple[Project, bool]:
        project_path.mkdir(parents=True, exist_ok=True)
        existing = self._find_project_by_path(project_path)
        if existing is not None:
            return existing, False

        base_id = _slugify(project_path.name or normalized["app_name"], fallback=_DEFAULT_PROJECT_ID)
        project_id = self._next_project_id(base_id)
        project = Project(
            id=project_id,
            name=normalized["app_name"],
            path=str(project_path),
            launch_cmd="python server.py",
            kind=ProjectKind.APP,
            description=(
                "Fast Money reference app: a private/local-first client-ops SaaS starter "
                "for leads, quotes, jobs, invoices, and renewals."
            ),
            category="fast-money",
            expected_port=_DEFAULT_PORT,
            health=HealthProbe(
                kind="http",
                target=f"http://127.0.0.1:{_DEFAULT_PORT}/health",
                expect_status=200,
            ),
            tags=["ai-generated", "fast-money", "client-ops", "saas"],
        )
        with self._storage.transaction() as conn:
            created = projects_module.create(conn, project)
        return created, True

    def _find_project_by_path(self, project_path: Path) -> Project | None:
        target = str(project_path.resolve())
        for project in projects_module.list_projects(self._storage.conn):
            try:
                if str(Path(project.path).expanduser().resolve()) == target:
                    return project
            except OSError:
                if project.path == target:
                    return project
        return None

    def _next_project_id(self, base_id: str) -> str:
        candidate = base_id
        suffix = 2
        while projects_module.get_or_none(self._storage.conn, candidate) is not None:
            candidate = f"{base_id}-{suffix}"
            suffix += 1
        return candidate

    def _ensure_reference_scaffold(
        self,
        *,
        project_path: Path,
        project: Project,
        normalized: dict[str, Any],
    ) -> list[Path]:
        written: list[Path] = []
        static_dir = project_path / "static"
        static_dir.mkdir(parents=True, exist_ok=True)

        config_path = project_path / "fast_money.config.json"
        config_payload = {
            "app_name": normalized["app_name"],
            "pricing_model": normalized["pricing_model"],
            "include_customer_portal": normalized["include_customer_portal"],
            "include_employee_console": normalized["include_employee_console"],
            "include_catalog_editor": normalized["include_catalog_editor"],
            "expected_port": project.expected_port or _DEFAULT_PORT,
            "billing": {
                "provider": "stripe-placeholder",
                "secret_key_env": "STRIPE_SECRET_KEY",
                "publishable_key_env": "STRIPE_PUBLISHABLE_KEY",
                "webhook_secret_env": "STRIPE_WEBHOOK_SECRET",
                "notes": "Wire live billing after local validation; keep secrets out of source control.",
            },
            "auth": {
                "provider": "local-placeholder",
                "session_cookie_name": "fast_money_session",
                "notes": "Replace this placeholder with the hosted auth provider you choose.",
            },
            "ai_features": [
                "Lead enrichment notes",
                "Quote draft acceleration",
                "Renewal risk nudges",
            ],
        }
        config_path.write_text(json.dumps(config_payload, indent=2) + "\n", encoding="utf-8")
        written.append(config_path)

        seed_path = project_path / "seed-data.json"
        if not seed_path.exists():
            seed_path.write_text(_seed_data_json(), encoding="utf-8")
            written.append(seed_path)

        server_path = project_path / "server.py"
        if not server_path.exists():
            server_path.write_text(_server_py(), encoding="utf-8")
            written.append(server_path)

        styles_path = static_dir / "styles.css"
        if not styles_path.exists():
            styles_path.write_text(_styles_css(), encoding="utf-8")
            written.append(styles_path)

        app_js_path = static_dir / "app.js"
        if not app_js_path.exists():
            app_js_path.write_text(_app_js(), encoding="utf-8")
            written.append(app_js_path)

        readme_path = project_path / "README.md"
        if not readme_path.exists():
            readme_path.write_text(_project_readme(normalized["app_name"]), encoding="utf-8")
            written.append(readme_path)

        architecture_path = project_path / "ARCHITECTURE.md"
        if not architecture_path.exists():
            architecture_path.write_text(_architecture_note(), encoding="utf-8")
            written.append(architecture_path)

        monetization_path = project_path / "MONETIZATION.md"
        if not monetization_path.exists():
            monetization_path.write_text(_monetization_note(), encoding="utf-8")
            written.append(monetization_path)

        context_path = project_path / ".synapse-ai-context.md"
        if not context_path.exists():
            context_path.write_text(_ai_context_note(normalized["app_name"]), encoding="utf-8")
            written.append(context_path)

        existing = self._find_project_by_path(project_path)
        if (
            existing is not None
            and existing.expected_port is None
            and existing.launch_cmd == project.launch_cmd
        ):
            with self._storage.transaction() as conn:
                projects_module.update(
                    conn,
                    existing.id,
                    ProjectUpdate(
                        expected_port=_DEFAULT_PORT,
                        health=HealthProbe(
                            kind="http",
                            target=f"http://127.0.0.1:{_DEFAULT_PORT}/health",
                            expect_status=200,
                        ),
                    ),
                )
        return written

    def _build_brief(self, project: Project, normalized: dict[str, Any]) -> str:
        portal = "yes" if normalized["include_customer_portal"] else "no"
        ops = "yes" if normalized["include_employee_console"] else "no"
        catalog = "yes" if normalized["include_catalog_editor"] else "no"
        return "\n".join(
            [
                f"# {normalized['app_name']}",
                "",
                "## Product brief",
                normalized["brief"],
                "",
                "## Defaults",
                f"- Pricing model: {normalized['pricing_model']}",
                f"- Customer portal: {portal}",
                f"- Employee console: {ops}",
                f"- Catalog editor: {catalog}",
                f"- Project id: {project.id}",
                f"- Project path: {project.path}",
                f"- Launch command: {project.launch_cmd}",
                f"- Expected port: {project.expected_port or _DEFAULT_PORT}",
                "",
                "## Required flow",
                "- Lead -> quote -> approval -> engagement/job -> invoice -> renewal handoff",
                "",
                "## Non-negotiables",
                "- Keep the app private/local-first by default.",
                "- Keep billing/auth integrations as adapter seams with config placeholders, not hardcoded secrets.",
                "- Preserve README.md, ARCHITECTURE.md, MONETIZATION.md, seed-data.json, and FAST_MONEY_BRIEF.md as project memory.",
                "",
            ]
        )

    def _build_prompt(self, project: Project, normalized: dict[str, Any]) -> str:
        portal = "enabled" if normalized["include_customer_portal"] else "disabled"
        ops = "enabled" if normalized["include_employee_console"] else "disabled"
        catalog = "enabled" if normalized["include_catalog_editor"] else "disabled"
        return "\n".join(
            [
                f"You are upgrading `{normalized['app_name']}` inside the project `{project.id}`.",
                "",
                "Start by reading:",
                "- Synapse AI context if this session can reach `/api/v1/ai/context`",
                "- `FAST_MONEY_BRIEF.md`",
                "- `README.md`",
                "- `ARCHITECTURE.md`",
                "- `MONETIZATION.md`",
                "- `fast_money.config.json`",
                "- `seed-data.json`",
                "",
                "What already exists:",
                "- Synapse already created or reused this target project for you; build in place instead of starting over.",
                "- A runnable private/local-first reference app shell launched with `python server.py`.",
                "- Route shells for landing page, pricing, sign-in, customer portal, operator console, and optional catalog editor.",
                "- Billing/auth adapter placeholders and demo data.",
                "",
                "Your job:",
                "- Deepen the starter into a sellable vertical B2B client-ops SaaS for service businesses.",
                "- Preserve or improve the current launch path instead of replacing it with something heavier unless there is a strong reason.",
                f"- Pricing model: `{normalized['pricing_model']}`.",
                f"- Customer portal is `{portal}`.",
                f"- Employee console is `{ops}`.",
                f"- Catalog editor is `{catalog}`.",
                "",
                "Must-have product surfaces:",
                "- Landing page",
                "- Pricing page",
                "- Auth shell",
                "- Customer portal",
                "- Operator/admin console",
                "- One core flow: lead -> quote -> approval -> engagement/job -> invoice/renewal handoff",
                "",
                "Business constraints:",
                "- Keep the app private/local-first unless explicitly asked to publish it.",
                "- Keep billing and auth as adapter seams with config placeholders instead of live provider secrets.",
                "- Keep secrets out of source control.",
                "- Favor recurring revenue via a base subscription plus AI-heavy usage/overage where appropriate.",
                "",
                "Documentation expectations:",
                "- Update README.md with how to run and what the product sells.",
                "- Update ARCHITECTURE.md if you change the structure.",
                "- Update MONETIZATION.md if pricing or packaging changes.",
                "",
                "When you finish, leave the project in a runnable state and summarize what changed.",
                "",
            ]
        )


def _project_readme(app_name: str) -> str:
    return f"""# {app_name}

Fast Money created this local-first client-ops SaaS starter as a proof app
that Synapse can generate and then hand to an AI runtime for refinement.

## What it includes

- Landing page
- Pricing page
- Sign-in shell
- Customer portal shell
- Operator console shell
- Optional catalog editor shell
- Demo data and billing/auth placeholders

## Run locally

```powershell
python server.py
```

Then open `http://127.0.0.1:8740/`.

## Files to know

- `FAST_MONEY_BRIEF.md` -- the latest product brief passed by the launcher
- `PROMPT.md` -- the current AI build/refinement prompt
- `ARCHITECTURE.md` -- structure and boundaries
- `MONETIZATION.md` -- pricing and packaging notes
- `seed-data.json` -- demo records used by the portal and ops screens
"""


def _architecture_note() -> str:
    return """# Architecture

## Runtime

- `server.py` uses Python's standard-library HTTP server so the starter is
  runnable anywhere Synapse itself can run Python.
- `fast_money.config.json` controls app name, enabled surfaces, billing
  placeholders, and the expected port.
- `seed-data.json` feeds the portal and operations console with deterministic
  sample records.

## Surfaces

- `/` landing page
- `/pricing` pricing and packaging
- `/signin` auth shell
- `/portal` customer portal
- `/ops` operator console
- `/catalog` optional catalog editor shell
- `/health` launcher-friendly health endpoint

## Next upgrades

- Swap the placeholder auth seam for real sessions.
- Replace the demo data seam with persistent storage.
- Add real billing and subscription state behind the pricing page.
"""


def _monetization_note() -> str:
    return """# Monetization

## Default model

Use hybrid pricing:

- Base subscription for the workspace, staff seats, and portal access.
- AI-heavy or volume-heavy actions charged as usage/overage.

## Why this is the default

- The recurring subscription keeps the business legible to buyers.
- The usage layer covers variable AI cost instead of hiding it in flat seats.
- Client-ops workflows create operational stickiness once quotes, jobs, and
  invoices are flowing through the system.

## Revenue hooks to refine

- Quote drafting and lead enrichment credits
- Renewal-risk nudges for retained clients
- Catalog/package upsell recommendations
"""


def _ai_context_note(app_name: str) -> str:
    return f"""# AI context

- Project: {app_name}
- Created by: Synapse Fast Money
- Intent: turn the local starter into a sellable client-ops SaaS
- Remember to preserve the private/local-first default unless the human asks to publish it
"""


def _seed_data_json() -> str:
    payload = {
        "leads": [
            {
                "id": "lead-1001",
                "company": "Northline HVAC",
                "contact": "Erin Stone",
                "stage": "quote-draft",
                "value_usd": 4800,
            },
            {
                "id": "lead-1002",
                "company": "Bright Dental Group",
                "contact": "Mina Patel",
                "stage": "approval-pending",
                "value_usd": 9200,
            },
        ],
        "quotes": [
            {
                "id": "quote-2001",
                "lead_id": "lead-1001",
                "package": "Maintenance Retainer",
                "status": "sent",
                "amount_usd": 4800,
            }
        ],
        "jobs": [
            {
                "id": "job-3001",
                "client": "Bright Dental Group",
                "status": "scheduled",
                "owner": "Jordan",
                "next_step": "Kickoff call Monday 10:00",
            }
        ],
        "invoices": [
            {
                "id": "inv-4001",
                "client": "Northline HVAC",
                "status": "draft",
                "amount_usd": 1200,
                "renewal_window_days": 45,
            }
        ],
        "catalog": [
            {
                "id": "svc-5001",
                "name": "Lead-to-Launch Sprint",
                "price_from_usd": 2500,
                "category": "Implementation",
            },
            {
                "id": "svc-5002",
                "name": "Monthly Revenue Ops Retainer",
                "price_from_usd": 1200,
                "category": "Recurring",
            },
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def _server_py() -> str:
    return r'''from __future__ import annotations

import json
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
CONFIG = json.loads((BASE_DIR / "fast_money.config.json").read_text(encoding="utf-8"))
SEED_DATA = json.loads((BASE_DIR / "seed-data.json").read_text(encoding="utf-8"))
PORT = int(CONFIG.get("expected_port") or 8740)


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
    <script src="/static/app.js"></script>
  </body>
</html>"""


def money(value: int) -> str:
    return f"${value:,.0f}"


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
        <h3>Fewer “where are we?” emails</h3>
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
        <p class="eyebrow">Auth shell</p>
        <h2>Local-first sign in, ready for a hosted provider later.</h2>
        <p class="lede">
          This shell is intentionally simple: enough to prove the route, layout, and handoff without
          hardcoding secrets or committing live auth config.
        </p>
      </div>
    </section>
    <section class="panel auth-card">
      <label>Email</label>
      <input placeholder="you@company.com" />
      <label>Password</label>
      <input type="password" placeholder="••••••••" />
      <div class="cta-row">
        <button class="button primary" type="button">Sign in</button>
        <button class="button ghost" type="button">Request invite</button>
      </div>
      <p class="muted">Wire this shell to the chosen auth provider after local validation.</p>
    </section>
    """


def portal_page() -> str:
    return """
    <section class="hero compact">
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
    <section class="hero compact">
      <div>
        <p class="eyebrow">Operator console</p>
        <h2>Run the revenue engine from one board.</h2>
      </div>
      <aside class="hero-card">
        <p class="card-label">Today</p>
        <p class="hero-value">3 action items</p>
        <p class="muted">1 approval, 1 kickoff, 1 invoice follow-up</p>
      </aside>
    </section>
    <section class="grid two-up">
      <article class="panel">
        <p class="card-label">Lead pipeline</p>
        <div id="ops-leads" class="stack"></div>
      </article>
      <article class="panel">
        <p class="card-label">Invoices & renewals</p>
        <div id="ops-invoices" class="stack"></div>
      </article>
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
        if path == "/api/demo-data":
            self._json(SEED_DATA)
            return
        if path == "/static/styles.css":
            self._file(BASE_DIR / "static" / "styles.css", "text/css; charset=utf-8")
            return
        if path == "/static/app.js":
            self._file(BASE_DIR / "static" / "app.js", "application/javascript; charset=utf-8")
            return
        if path in PAGES:
            title, page_id, renderer = PAGES[path]
            self._html(page_shell(title, renderer(), page_id=page_id))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Page not found")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _html(self, payload: str) -> None:
        data = payload.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: object) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
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
'''


def _styles_css() -> str:
    return """\
:root {
  --bg: #f6f0e3;
  --bg-soft: rgba(255, 255, 255, 0.72);
  --panel: rgba(255, 255, 255, 0.84);
  --line: rgba(36, 44, 28, 0.1);
  --text: #1d2715;
  --muted: #5f6f53;
  --accent: #2f6b2f;
  --accent-strong: #174117;
  --warm: #d58b32;
  --shadow: 0 18px 50px rgba(37, 44, 25, 0.12);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  font-family: "Segoe UI", "Trebuchet MS", sans-serif;
  color: var(--text);
  background:
    radial-gradient(circle at top left, rgba(213, 139, 50, 0.16), transparent 28rem),
    linear-gradient(180deg, #faf6ec 0%, var(--bg) 48%, #f3ead8 100%);
}

.backdrop {
  position: fixed;
  inset: 0;
  background:
    radial-gradient(circle at 18% 18%, rgba(47, 107, 47, 0.11), transparent 18rem),
    radial-gradient(circle at 82% 10%, rgba(213, 139, 50, 0.12), transparent 20rem);
  pointer-events: none;
}

.topbar,
.frame {
  position: relative;
  z-index: 1;
}

.topbar {
  display: flex;
  justify-content: space-between;
  gap: 2rem;
  padding: 2rem 2rem 1rem;
  align-items: flex-end;
}

.topbar h1,
.hero h2,
.panel h3 {
  margin: 0;
  font-family: Georgia, "Times New Roman", serif;
}

.topbar h1 {
  font-size: clamp(1.8rem, 4vw, 2.7rem);
}

.eyebrow,
.card-label {
  margin: 0 0 0.35rem;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 0.72rem;
  color: var(--accent);
  font-weight: 700;
}

.nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  justify-content: flex-end;
}

.nav-link,
.button {
  border-radius: 999px;
  text-decoration: none;
  transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease;
}

.nav-link {
  padding: 0.65rem 1rem;
  background: rgba(255, 255, 255, 0.56);
  color: var(--text);
  border: 1px solid var(--line);
}

.nav-link:hover,
.button:hover {
  transform: translateY(-1px);
}

.frame {
  width: min(1180px, calc(100% - 2rem));
  margin: 0 auto 3rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.hero,
.panel {
  border: 1px solid var(--line);
  background: var(--panel);
  box-shadow: var(--shadow);
  backdrop-filter: blur(12px);
}

.hero {
  border-radius: 30px;
  padding: 1.75rem;
  display: grid;
  gap: 1.25rem;
  grid-template-columns: minmax(0, 1.9fr) minmax(280px, 0.9fr);
}

.hero.compact {
  grid-template-columns: 1fr;
}

.hero .lede,
.muted {
  color: var(--muted);
}

.hero .lede {
  font-size: 1.05rem;
  line-height: 1.6;
  max-width: 58rem;
}

.hero-card {
  border-radius: 24px;
  padding: 1.2rem;
  background: linear-gradient(180deg, rgba(27, 61, 27, 0.96), rgba(23, 47, 23, 0.96));
  color: #f7f8f2;
}

.hero-value {
  margin: 0.25rem 0;
  font-size: clamp(2rem, 5vw, 3rem);
  font-weight: 700;
}

.grid {
  display: grid;
  gap: 1.1rem;
}

.two-up {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.three-up {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.panel {
  border-radius: 24px;
  padding: 1.25rem;
}

.price-card.featured {
  outline: 2px solid rgba(47, 107, 47, 0.18);
  background: linear-gradient(180deg, rgba(242, 249, 238, 0.95), rgba(255, 255, 255, 0.92));
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

.tile {
  border-radius: 18px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.66);
  padding: 0.9rem;
}

.tile h4,
.tile p {
  margin: 0;
}

.tile h4 {
  font-size: 1rem;
}

.meta {
  margin-top: 0.35rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 0.25rem 0.6rem;
  font-size: 0.72rem;
  background: rgba(47, 107, 47, 0.09);
  color: var(--accent-strong);
}

.cta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.7rem;
  margin-top: 1rem;
}

.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.8rem 1.1rem;
  font-weight: 700;
  border: 1px solid transparent;
  cursor: pointer;
}

.button.primary {
  background: var(--accent);
  color: #f8fbf4;
  box-shadow: 0 12px 28px rgba(47, 107, 47, 0.22);
}

.button.ghost {
  background: rgba(255, 255, 255, 0.7);
  color: var(--text);
  border-color: var(--line);
}

.auth-card {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  max-width: 28rem;
}

.auth-card input {
  border-radius: 14px;
  border: 1px solid var(--line);
  padding: 0.8rem 0.95rem;
  font: inherit;
  background: rgba(255, 255, 255, 0.86);
}

@media (max-width: 900px) {
  .hero,
  .two-up,
  .three-up {
    grid-template-columns: 1fr;
  }

  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }
}
"""


def _app_js() -> str:
    return """\
function money(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

function tile(title, subtitle, chips) {
  const meta = (chips || [])
    .map((chip) => `<span class="chip">${chip}</span>`)
    .join("");
  return `<article class="tile"><h4>${title}</h4><p class="muted">${subtitle}</p><div class="meta">${meta}</div></article>`;
}

function renderPortal(data) {
  const quotes = document.getElementById("portal-quotes");
  const jobs = document.getElementById("portal-jobs");
  if (quotes) {
    quotes.innerHTML = (data.quotes || [])
      .map((item) =>
        tile(
          item.package,
          `${item.status} • ${money(item.amount_usd)}`,
          [item.id, item.lead_id]
        )
      )
      .join("");
  }
  if (jobs) {
    const rows = [...(data.jobs || []), ...(data.invoices || [])];
    jobs.innerHTML = rows
      .map((item) =>
        tile(
          item.client,
          item.next_step || `${item.status} • ${money(item.amount_usd)}`,
          [item.id]
        )
      )
      .join("");
  }
}

function renderOps(data) {
  const leads = document.getElementById("ops-leads");
  const invoices = document.getElementById("ops-invoices");
  if (leads) {
    leads.innerHTML = (data.leads || [])
      .map((item) =>
        tile(
          item.company,
          `${item.contact} • ${money(item.value_usd)}`,
          [item.stage, item.id]
        )
      )
      .join("");
  }
  if (invoices) {
    invoices.innerHTML = (data.invoices || [])
      .map((item) =>
        tile(
          item.client,
          `${item.status} • renewal in ${item.renewal_window_days} days`,
          [item.id, money(item.amount_usd)]
        )
      )
      .join("");
  }
}

function renderCatalog(data, config) {
  const container = document.getElementById("catalog-items");
  if (!container || !config.include_catalog_editor) return;
  container.innerHTML = (data.catalog || [])
    .map((item) =>
      tile(
        item.name,
        `${item.category} • from ${money(item.price_from_usd)}`,
        [item.id]
      )
    )
    .join("");
}

const config = window.FAST_MONEY_CONFIG || {};
const data = window.FAST_MONEY_DATA || {};
const page = document.body.getAttribute("data-page");

if (page === "portal") renderPortal(data);
if (page === "ops") renderOps(data);
if (page === "catalog") renderCatalog(data, config);
"""
