#!/usr/bin/env python3
"""One-shot branch helper for ADR-0038.

This exists only so GitHub Actions can make small in-place edits to large existing
files while this feature is being built remotely.  It is idempotent and is deleted
before the feature branch merges.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"bootstrap marker missing in {path}: {old[:120]!r}")
    write(path, text.replace(old, new, 1))


def patch_readme_and_changelog() -> None:
    replace_once(
        "README.md",
        "**Status:** early development (`v0.1.205`).",
        "**Status:** early development (`v0.1.209`).",
    )
    changelog = read("CHANGELOG.md")
    if "Token-aware Smart Review Engine" not in changelog:
        marker = "## [Unreleased]\n"
        if marker not in changelog:
            raise SystemExit("CHANGELOG Unreleased marker missing")
        changelog = changelog.replace(
            marker,
            marker
            + "\n### Added\n"
            + "- **Token-aware Smart Review Engine** -- deterministic/privacy checks run before model spend, risk selects bounded review depth, project contracts can add focused invariants, and targeted passes reuse the existing coder-review runtime across registered projects.\n",
            1,
        )
        write("CHANGELOG.md", changelog)


def patch_ai_discovery() -> None:
    path = "daemon/synapse_daemon/routes_ai.py"
    text = read(path)
    smart_path = "/api/v1/review/engine/plan/{project_id}"
    if smart_path not in text:
        marker = '                {\n                    "purpose": "human review plus the durable proposal backlog:'
        insert = (
            '                {\n'
            '                    "purpose": "plan or queue a token-aware Smart Review for a project change; deterministic checks run before any AI pass and queue reuses normal coder review-pass execution",\n'
            '                    "method": "POST",\n'
            '                    "path": "/api/v1/review/engine/plan/{project_id} | /api/v1/review/engine/queue/{project_id}",\n'
            '                },\n'
        )
        if marker not in text:
            raise SystemExit("routes_ai Smart Review insertion marker missing")
        text = text.replace(marker, insert + marker, 1)
        write(path, text)


def patch_review_route_scope() -> None:
    path = "daemon/synapse_daemon/routes_review.py"
    text = read(path)
    text = text.replace(
        "from fastapi import APIRouter, Query\n",
        "from fastapi import APIRouter, Query, Request\n",
        1,
    )
    if "def _enforce_review_project_scope(" not in text:
        marker = "\n\ndef build_review_router(storage: Storage, bus: EventBus) -> APIRouter:\n"
        helper = '''

def _enforce_review_project_scope(request: Request, project_id: str) -> None:
    """Prevent a project-scoped worker from reviewing another project."""

    subject = request.state.auth_subject
    if subject.kind == "worker" and subject.project_id != project_id:
        from .errors import SynapseError

        raise SynapseError(
            code="auth.worker_scope_denied",
            message="A worker can only review its assigned project.",
            status=403,
            details={"authority": subject.authority or "observe"},
        )
'''
        if marker not in text:
            raise SystemExit("routes_review helper insertion marker missing")
        text = text.replace(marker, helper + marker, 1)

    old_plan = '''    async def plan_project_review(
        project_id: str,
        payload: review_engine.ReviewEngineRequest | None = None,
    ) -> review_engine.ReviewPlan:
        """Plan the cheapest useful review for a project change without spending AI tokens."""

        project = projects_module.get(storage.conn, project_id)
        request = payload or review_engine.ReviewEngineRequest()
        return await asyncio.to_thread(review_engine.plan_project_review, project, request)
'''
    new_plan = '''    async def plan_project_review(
        project_id: str,
        http_request: Request,
        payload: review_engine.ReviewEngineRequest | None = None,
    ) -> review_engine.ReviewPlan:
        """Plan the cheapest useful review for a project change without spending AI tokens."""

        _enforce_review_project_scope(http_request, project_id)
        project = projects_module.get(storage.conn, project_id)
        review_request = payload or review_engine.ReviewEngineRequest()
        return await asyncio.to_thread(review_engine.plan_project_review, project, review_request)
'''
    if new_plan not in text:
        if old_plan not in text:
            raise SystemExit("routes_review plan marker missing")
        text = text.replace(old_plan, new_plan, 1)

    old_queue = '''    async def queue_project_review(
        project_id: str,
        payload: review_engine.ReviewEngineRequest | None = None,
    ) -> dict[str, Any]:
'''
    new_queue = '''    async def queue_project_review(
        project_id: str,
        http_request: Request,
        payload: review_engine.ReviewEngineRequest | None = None,
    ) -> dict[str, Any]:
'''
    if new_queue not in text:
        if old_queue not in text:
            raise SystemExit("routes_review queue marker missing")
        text = text.replace(old_queue, new_queue, 1)

    queue_start = text.find('    @router.post("/engine/queue/{project_id}"')
    if queue_start < 0:
        raise SystemExit("queue route marker missing")
    prefix, suffix = text[:queue_start], text[queue_start:]
    old_body = '''        project = projects_module.get(storage.conn, project_id)
        request = payload or review_engine.ReviewEngineRequest()
        plan = await asyncio.to_thread(review_engine.plan_project_review, project, request)
'''
    new_body = '''        _enforce_review_project_scope(http_request, project_id)
        project = projects_module.get(storage.conn, project_id)
        review_request = payload or review_engine.ReviewEngineRequest()
        plan = await asyncio.to_thread(review_engine.plan_project_review, project, review_request)
'''
    if new_body not in suffix:
        if old_body not in suffix:
            raise SystemExit("queue body marker missing")
        suffix = suffix.replace(old_body, new_body, 1)
    suffix = suffix.replace(
        'active_runtime_id=request.primary_runtime or "codex"',
        'active_runtime_id=review_request.primary_runtime or "codex"',
        1,
    )
    suffix = suffix.replace('"source": request.source,', '"source": review_request.source,', 1)
    write(path, prefix + suffix)


def patch_review_engine() -> None:
    path = "daemon/synapse_daemon/review_engine.py"
    text = read(path)

    if "change_title: str | None" not in text:
        text = text.replace(
            "    primary_runtime: str | None = None\n    force_ai: bool = False\n",
            "    primary_runtime: str | None = None\n    change_title: str | None = Field(default=None, max_length=300)\n    force_ai: bool = False\n",
            1,
        )
    if "diff_complete: bool" not in text:
        text = text.replace(
            '    source: str = "local"\n    git_error: str | None = None\n',
            '    source: str = "local"\n    change_title: str | None = None\n    untracked_files: list[str] = Field(default_factory=list)\n    diff_complete: bool = True\n    git_error: str | None = None\n',
            1,
        )

    explicit_old = '''            docs_only=bool(changed_files) and all(_is_docs(path) for path in changed_files),
            source=request.source,
        )
'''
    explicit_new = '''            docs_only=bool(changed_files) and all(_is_docs(path) for path in changed_files),
            source=request.source,
            change_title=request.change_title,
            diff_complete=bool(diff_text.strip()) or not changed_files,
        )
'''
    if explicit_new not in text:
        if explicit_old not in text:
            raise SystemExit("review_engine explicit change marker missing")
        text = text.replace(explicit_old, explicit_new, 1)

    if "untracked_files = _bounded_unique(" not in text:
        marker = "    changed_files = _status_paths(status_text)\n    diff_text, diff_error = _git(\n"
        replacement = '''    changed_files = _status_paths(status_text)
    untracked_files = _bounded_unique(
        [line[3:].strip() for line in status_text.splitlines() if line.startswith("?? ")],
        limit=500,
    )
    diff_text, diff_error = _git(
'''
        if marker not in text:
            raise SystemExit("review_engine status marker missing")
        text = text.replace(marker, replacement, 1)

    local_old = '''        docs_only=bool(changed_files) and all(_is_docs(path) for path in changed_files),
        source=request.source,
        git_error=git_error,
    )
'''
    local_new = '''        docs_only=bool(changed_files) and all(_is_docs(path) for path in changed_files),
        source=request.source,
        change_title=request.change_title,
        untracked_files=untracked_files,
        diff_complete=not untracked_files,
        git_error=git_error,
    )
'''
    if local_new not in text:
        if local_old not in text:
            raise SystemExit("review_engine local change marker missing")
        text = text.replace(local_old, local_new, 1)

    old_auto = '''def _auto_mode(change: ChangeSnapshot, risk: ReviewRisk) -> ReviewMode:
    normalized_names = {_normalise_path(path).rsplit("/", 1)[-1] for path in change.changed_files}
    release_signal = bool(normalized_names & _RELEASE_FILES) and bool(
        re.search(r"(?i)\\b(version|release|changelog)\\b", change.diff_text[:100_000])
    )
'''
    new_auto = '''def _auto_mode(change: ChangeSnapshot, risk: ReviewRisk) -> ReviewMode:
    normalized_names = {_normalise_path(path).rsplit("/", 1)[-1] for path in change.changed_files}
    release_title = bool(
        change.change_title
        and re.search(r"(?i)(?:\\brelease\\b|\\bv?\\d+\\.\\d+(?:\\.\\d+)?\\b)", change.change_title)
    )
    release_signal = release_title or (
        bool(normalized_names & _RELEASE_FILES)
        and bool(re.search(r"(?i)\\b(version|release|changelog)\\b", change.diff_text[:100_000]))
    )
'''
    if new_auto not in text:
        if old_auto not in text:
            raise SystemExit("review_engine auto-mode marker missing")
        text = text.replace(old_auto, new_auto, 1)

    secret_marker = '_SECRET_FILENAMES = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json"}\n'
    if "_SECRET_ASSIGNMENT_RE" not in text:
        secret_defs = secret_marker + '''_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)^[+ ]?\\s*[A-Z0-9_.-]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIAL)[A-Z0-9_.-]*\\s*[:=]\\s*[\\\"']?([^\\s\\\"']{8,})"
)
_BEARER_VALUE_RE = re.compile(r"(?i)\\bBearer\\s+[A-Za-z0-9._~+/=-]{12,}")
_SAFE_SECRET_HINTS = ("example", "placeholder", "redacted", "dummy", "fake", "test-value", "changeme")


def _diff_has_secret_like_value(diff_text: str) -> bool:
    if _BEARER_VALUE_RE.search(diff_text):
        return True
    for match in _SECRET_ASSIGNMENT_RE.finditer(diff_text):
        value = match.group(1).lower()
        if not any(hint in value for hint in _SAFE_SECRET_HINTS):
            return True
    return False
'''
        if secret_marker not in text:
            raise SystemExit("review_engine secret marker missing")
        text = text.replace(secret_marker, secret_defs, 1)

    source_marker = "    source_files = [path for path in files if _is_source(path)]\n"
    additions = ""
    if 'id="diff-evidence-incomplete"' not in text:
        additions += '''    if not change.diff_complete and change.changed_files:
        findings.append(
            ReviewFinding(
                id="diff-evidence-incomplete",
                severity="warning",
                title="Changed-file evidence is incomplete",
                detail=(
                    "The exact diff is missing for one or more changed files"
                    + (f" (including untracked: {', '.join(change.untracked_files[:8])})" if change.untracked_files else "")
                    + ". Collect an exact bounded diff before spending AI review tokens."
                ),
            )
        )

'''
    if 'id="secret-like-value-in-diff"' not in text:
        additions += '''    if _diff_has_secret_like_value(change.diff_text):
        findings.append(
            ReviewFinding(
                id="secret-like-value-in-diff",
                severity="blocking",
                title="Secret-like value detected in the diff",
                detail="Synapse withheld the diff from AI review. Remove/redact the value or use a clearly fake test placeholder before retrying.",
            )
        )

'''
    if additions:
        if source_marker not in text:
            raise SystemExit("review_engine findings marker missing")
        text = text.replace(source_marker, additions + source_marker, 1)

    old_gate = '''    has_blocker = any(item.severity == "blocking" for item in findings)
    ai_required = (
        has_material_change
        and not has_blocker
'''
    new_gate = '''    has_blocker = any(item.severity == "blocking" for item in findings)
    evidence_complete = change.diff_complete
    ai_required = (
        has_material_change
        and not has_blocker
        and evidence_complete
'''
    if new_gate not in text:
        if old_gate not in text:
            raise SystemExit("review_engine AI gate marker missing")
        text = text.replace(old_gate, new_gate, 1)

    old_reason = '''    elif not has_material_change:
        reason = "No material local change was found, so spending review tokens would add no value."
    elif change.docs_only and not request.force_ai:
'''
    new_reason = '''    elif not has_material_change:
        reason = "No material local change was found, so spending review tokens would add no value."
    elif not evidence_complete:
        reason = "Exact diff evidence is incomplete, so Synapse will not spend review tokens or claim the change was reviewed yet."
    elif change.docs_only and not request.force_ai:
'''
    if new_reason not in text:
        if old_reason not in text:
            raise SystemExit("review_engine reason marker missing")
        text = text.replace(old_reason, new_reason, 1)

    text = text.replace(
        'if any(item.id == "secret-file-changed" for item in plan.deterministic_findings):',
        'if any(item.id in {"secret-file-changed", "secret-like-value-in-diff"} for item in plan.deterministic_findings):',
        1,
    )
    write(path, text)


def patch_docs() -> None:
    path = "docs/api-finds.md"
    text = read(path)
    if "## Smart Review Engine" not in text:
        text += '''

## Smart Review Engine

Synapse can review a change across any registered project without paying for a full-repository council by default.

- `POST /api/v1/review/engine/plan/{project_id}` -- token-free planning. It inspects the supplied bounded diff or local Git change, classifies risk, runs deterministic guards, selects `economy|standard|thorough|release`, and returns the smallest justified reviewer set plus an estimated context budget.
- `POST /api/v1/review/engine/queue/{project_id}` -- creates only the justified **existing coder review passes** and returns canonical `/coder-threads/.../review-passes/{id}/launch` URLs. It does not create a parallel model runner.
- `.synapse/review-policy.json` can bound `mode`, `token_budget`, `max_ai_passes`, `max_diff_chars`, and project-specific `focus_points`.
- Secret-bearing files or secret-like values block AI context. Missing or untracked diff evidence also stops the paid review lane until exact evidence exists.
- Docs-only and empty changes skip AI by default. Review depth is risk-based, and the primary coder is rotated behind an independent reviewer when practical.
- `v1.review.engine_planned` publishes project id, risk, mode, whether AI review is required, and queued-pass count. It contains no diff or secrets.

The `smart-review` quick action teaches Codex, Claude, Copilot, ChatGPT-connected workers, and other Synapse AI operators to use this funnel. Exact provider usage remains measured by the existing coder runtime/execution ledger; planning estimates are not exact billed cost.
'''
        write(path, text)

    path = "docs/api-changes.md"
    text = read(path)
    if "/api/v1/review/engine/plan/{project_id}" not in text:
        header = "| Date | Endpoint or event | Kind | Notes |\n|---|---|---|---|\n"
        rows = (
            "| 2026-09-04 | `POST /api/v1/review/engine/plan/{project_id}` | additive | Token-free Smart Review planner: bounded diff evidence, deterministic/privacy gates, risk classification, token budget, and targeted reviewer plan. |\n"
            "| 2026-09-04 | `POST /api/v1/review/engine/queue/{project_id}` | additive | Queues planner-selected existing coder review passes; no second AI execution path. |\n"
            "| 2026-09-04 | `v1.review.engine_planned` | additive | Safe project/risk/mode/AI-required/queued summary event; no diff content. |\n"
        )
        if header not in text:
            raise SystemExit("api-changes table marker missing")
        write(path, text.replace(header, header + rows, 1))


def patch_tests() -> None:
    path = "daemon/tests/test_review_engine.py"
    text = read(path)
    if "test_release_title_triggers_release_mode_without_release_files" not in text:
        text += '''


def test_release_title_triggers_release_mode_without_release_files(tmp_path) -> None:
    project = _project(tmp_path)
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            change_title="v1.61: make timeline semantics explicit",
            changed_files=["src/feature.py", "tests/test_feature.py"],
            diff_text="+TIMELINE_SEMANTICS = 're-evaluation'\\n",
        ),
    )
    assert plan.mode == review_engine.ReviewMode.RELEASE
    assert any(item.review_kind == "release" for item in plan.review_passes)


def test_changed_file_without_diff_stays_in_free_evidence_lane(tmp_path) -> None:
    project = _project(tmp_path)
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(changed_files=["src/new_file.py"]),
    )
    assert plan.change.diff_complete is False
    assert plan.ai_review_required is False
    assert any(item.id == "diff-evidence-incomplete" for item in plan.deterministic_findings)


def test_secret_like_assignment_blocks_ai_even_in_normal_source_file(tmp_path) -> None:
    project = _project(tmp_path)
    plan = review_engine.plan_project_review(
        project,
        review_engine.ReviewEngineRequest(
            changed_files=["src/config.py"],
            diff_text="+API_KEY=sk_live_1234567890abcdef\\n",
            force_ai=True,
        ),
    )
    assert plan.ai_review_required is False
    assert any(item.id == "secret-like-value-in-diff" for item in plan.deterministic_findings)
    assert "sk_live_1234567890abcdef" not in review_engine.bounded_diff_for_prompt(plan)
'''
        write(path, text)

    integration = ROOT / "daemon/tests/test_smart_review_routes.py"
    if not integration.exists():
        integration.write_text(
            '''from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse_daemon.app import build_app
from synapse_daemon.projects import Project, create
from synapse_daemon.storage import Storage
from synapse_daemon.ws import EventBus


def _client(tmp_path: Path) -> TestClient:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    with storage.transaction() as conn:
        create(
            conn,
            Project(
                id="smart-review-demo",
                name="Smart Review Demo",
                path=str(tmp_path),
                launch_cmd="echo hi",
            ),
        )
    app = build_app(storage, EventBus())
    return TestClient(app, headers={"X-Synapse-Token": app.state.auth.local_token})


def _payload() -> dict:
    return {
        "changed_files": ["src/app.py", "tests/test_app.py"],
        "diff_text": "+def answer():\\n+    return 42\\n",
        "primary_runtime": "codex",
    }


def test_smart_review_is_openapi_and_ai_discoverable(tmp_path: Path) -> None:
    client = _client(tmp_path)
    openapi = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/review/engine/plan/{project_id}" in openapi["paths"]
    assert "/api/v1/review/engine/queue/{project_id}" in openapi["paths"]

    context = client.get("/api/v1/ai/context")
    assert context.status_code == 200, context.text
    advertised = " ".join(item["path"] for item in context.json()["endpoints_for_ai"])
    assert "/api/v1/review/engine/plan/{project_id}" in advertised
    assert "/api/v1/review/engine/queue/{project_id}" in advertised


def test_smart_review_plan_and_queue_reuse_coder_review_passes(tmp_path: Path) -> None:
    client = _client(tmp_path)
    plan_response = client.post("/api/v1/review/engine/plan/smart-review-demo", json=_payload())
    assert plan_response.status_code == 200, plan_response.text
    plan = plan_response.json()
    assert plan["ai_review_required"] is True
    assert plan["review_passes"][0]["requested_runtime_id"] == "claude"

    queued_response = client.post("/api/v1/review/engine/queue/smart-review-demo", json=_payload())
    assert queued_response.status_code == 201, queued_response.text
    queued = queued_response.json()
    assert queued["queued"]
    launch_url = queued["queued"][0]["launch_url"]
    assert launch_url.startswith("/api/v1/coder-threads/")
    assert launch_url.endswith("/launch")
''',
            encoding="utf-8",
        )


def main() -> None:
    patch_readme_and_changelog()
    patch_ai_discovery()
    patch_review_route_scope()
    patch_review_engine()
    patch_docs()
    patch_tests()


if __name__ == "__main__":
    main()
