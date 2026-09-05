#!/usr/bin/env python3
"""One-shot remediation helper for PR #4 review findings. Delete after it runs."""
from __future__ import annotations

import re
from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"missing marker for {label}: {old[:120]!r}")
    return text.replace(old, new, 1)


# --- review_engine.py -------------------------------------------------------
path = "daemon/synapse_daemon/review_engine.py"
text = read(path)
text = replace_once(
    text,
    "from . import projects as projects_module\n",
    "from . import ai_executions, coder_runtimes, projects as projects_module\n",
    "review engine imports",
)
text = replace_once(
    text,
    '''class ReviewPassPlan(BaseModel):\n    review_kind: str\n    title: str\n    requested_runtime_id: str\n    reason: str\n    focus_points: list[str] = Field(default_factory=list)\n''',
    '''class ReviewPassPlan(BaseModel):\n    review_kind: str\n    title: str\n    requested_runtime_id: str\n    reason: str\n    focus_points: list[str] = Field(default_factory=list)\n    estimated_input_tokens: int = 0\n    output_token_reserve: int = 0\n    estimated_total_tokens: int = 0\n''',
    "review pass budget fields",
)
text = replace_once(
    text,
    '''    estimated_context_tokens: int\n    budget_remaining_after_context: int\n    ai_review_required: bool\n''',
    '''    estimated_context_tokens: int\n    budget_remaining_after_context: int\n    estimated_tokens_per_pass: int\n    estimated_aggregate_tokens: int\n    budget_remaining_after_plan: int\n    ai_review_required: bool\n''',
    "review plan aggregate budget fields",
)
text = replace_once(
    text,
    '''_SECRET_FILENAMES = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json"}\n''',
    '''_SECRET_FILENAMES = {\n    ".env", ".env.local", ".env.production", ".npmrc", ".pypirc",\n    "credentials.json", "secrets.json", "service-account.json",\n    "id_rsa", "id_ed25519",\n}\n_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")\n''',
    "secret filename patterns",
)
text = replace_once(
    text,
    '''def _normalise_path(path: str) -> str:\n    return path.strip().replace("\\\\", "/").lower()\n\n\ndef _is_test(path: str) -> bool:\n''',
    '''def _normalise_path(path: str) -> str:\n    return path.strip().replace("\\\\", "/").lower()\n\n\ndef _is_secret_bearing_path(path: str) -> bool:\n    normalized = _normalise_path(path)\n    base = normalized.rsplit("/", 1)[-1]\n    return (\n        base in _SECRET_FILENAMES\n        or base.startswith(".env.")\n        or base.startswith("id_rsa_")\n        or base.startswith("id_ed25519_")\n        or base.endswith(_SECRET_SUFFIXES)\n        or ("credential" in base and base.endswith((".json", ".yaml", ".yml", ".toml")))\n        or ("secret" in base and base.endswith((".json", ".yaml", ".yml", ".toml")))\n    )\n\n\ndef _is_test(path: str) -> bool:\n''',
    "secret path helper",
)
text = replace_once(
    text,
    '''    secret_files = [path for path in files if path.rsplit("/", 1)[-1] in _SECRET_FILENAMES]\n''',
    '''    secret_files = [path for path in files if _is_secret_bearing_path(path)]\n''',
    "secret path detection",
)

runtime_pattern = re.compile(
    r"def _independent_runtime\(.*?\n\ndef _specialist_passes\(",
    re.DOTALL,
)
runtime_replacement = '''def _eligible_review_runtimes(\n    primary_runtime: str | None,\n    runtime_capacity: list[ai_executions.RuntimeCapacity] | None,\n) -> list[str]:\n    """Return independent runtimes that Synapse can honestly attempt now.\n\n    Daemon routes pass the durable capacity ledger.  Pure callers without a storage\n    handle fall back to the canonical runtime registry + binary probe, never to a\n    hard-coded provider ladder detached from installation truth.\n    """\n\n    primary = (primary_runtime or "").strip().lower()\n    if runtime_capacity is None:\n        return [\n            runtime.value\n            for runtime in coder_runtimes.DEFAULT_LADDER\n            if runtime.value != primary and coder_runtimes.available(runtime)\n        ]\n\n    eligible = [\n        item\n        for item in runtime_capacity\n        if item.runtime_id != primary and item.eligible_for_attempt\n    ]\n    eligible.sort(key=lambda item: (not item.usable_now, item.runtime_id))\n    return _bounded_unique([item.runtime_id for item in eligible], limit=20)\n\n\ndef _specialist_passes('''
if "def _eligible_review_runtimes(" not in text:
    text, count = runtime_pattern.subn(runtime_replacement, text, count=1)
    if count != 1:
        raise SystemExit("could not replace hard-coded runtime ladder")

# Replace the specialist function wholesale so budget and capacity are selected together.
specialist_pattern = re.compile(
    r"def _specialist_passes\(.*?\n    return selected\n",
    re.DOTALL,
)
specialist_replacement = '''def _specialist_passes(\n    project: projects_module.Project,\n    change: ChangeSnapshot,\n    risk: ReviewRisk,\n    policy: ReviewPolicy,\n    primary_runtime: str | None,\n    runtime_capacity: list[ai_executions.RuntimeCapacity] | None,\n    *,\n    estimated_input_tokens: int,\n    output_token_reserve: int,\n) -> list[ReviewPassPlan]:\n    files_text = "\\n".join(_normalise_path(path) for path in change.changed_files)\n    candidates: list[tuple[str, str, str, list[str]]] = []\n\n    candidates.append(\n        (\n            "qa",\n            "Correctness & regression review",\n            "Every material code change benefits from one independent correctness pass.",\n            [\n                "Find concrete bugs or regressions in the changed diff, not speculative repo-wide cleanup.",\n                "Require evidence for claims of completion and identify the smallest missing test/proof.",\n            ],\n        )\n    )\n    if any(part in files_text for part in _UI_PATH_PARTS):\n        candidates.append(\n            (\n                "ux",\n                "UI/UX human-impact review",\n                "The change touches a user-facing surface.",\n                ["Check mobile/desktop behavior, hierarchy, navigation escape paths, and accessibility."],\n            )\n        )\n    if risk == ReviewRisk.HIGH:\n        candidates.append(\n            (\n                "security",\n                "Safety & boundary review",\n                "High-risk paths or behavior changed.",\n                [\n                    "Check authorization, secret exposure, destructive actions, money/execution boundaries, and failure modes.",\n                    "Prefer a specific exploitable or integrity failure over generic security advice.",\n                ],\n            )\n        )\n    if policy.mode in {ReviewMode.THOROUGH, ReviewMode.RELEASE}:\n        candidates.append(\n            (\n                "judge",\n                "Independent release judge",\n                "Risk/depth justifies a second-opinion gate before declaring the change done.",\n                ["Judge only material findings and state whether another AI pass is actually worth its token cost."],\n            )\n        )\n    if policy.mode == ReviewMode.RELEASE:\n        candidates.insert(\n            1,\n            (\n                "release",\n                "Release integrity review",\n                "Release mode must reconcile code, package/runtime version, docs, changelog, and reload behavior.",\n                ["Verify release metadata and operational reload/version gates are internally consistent."],\n            ),\n        )\n\n    runtime_ids = _eligible_review_runtimes(primary_runtime, runtime_capacity)\n    if not runtime_ids:\n        return []\n\n    per_pass_total = estimated_input_tokens + output_token_reserve\n    selected: list[ReviewPassPlan] = []\n    planned_total = 0\n    for kind, title, reason, focus in candidates[: policy.max_ai_passes]:\n        if planned_total + per_pass_total > policy.token_budget:\n            break\n        runtime_id = runtime_ids[len(selected) % len(runtime_ids)]\n        selected.append(\n            ReviewPassPlan(\n                review_kind=kind,\n                title=title,\n                requested_runtime_id=runtime_id,\n                reason=reason,\n                focus_points=_bounded_unique([*focus, *policy.focus_points], limit=24),\n                estimated_input_tokens=estimated_input_tokens,\n                output_token_reserve=output_token_reserve,\n                estimated_total_tokens=per_pass_total,\n            )\n        )\n        planned_total += per_pass_total\n    return selected\n'''
text, count = specialist_pattern.subn(specialist_replacement, text, count=1)
if count != 1:
    raise SystemExit("could not replace specialist planner")

plan_pattern = re.compile(
    r"def plan_project_review\(.*?\n\ndef bounded_diff_for_prompt",
    re.DOTALL,
)
plan_replacement = '''def plan_project_review(\n    project: projects_module.Project,\n    request: ReviewEngineRequest,\n    *,\n    runtime_capacity: list[ai_executions.RuntimeCapacity] | None = None,\n) -> ReviewPlan:\n    change = collect_change_snapshot(project, request)\n    risk = classify_risk(change.changed_files, change.diff_text)\n    policy = effective_policy(project, request, change, risk)\n    findings = deterministic_findings(change, policy.mode)\n\n    # Planning budget is aggregate across every queued pass.  Each pass receives\n    # its own copy of bounded context, so repeated context is counted repeatedly.\n    diff_chars_in_context = min(change.diff_chars, policy.max_diff_chars)\n    per_pass_context_tokens = math.ceil(diff_chars_in_context / 4) + 1_500\n    output_token_reserve = 1_500\n    per_pass_total = per_pass_context_tokens + output_token_reserve\n\n    has_material_change = bool(change.changed_files or change.diff_text.strip())\n    has_blocker = any(item.severity == "blocking" for item in findings)\n    evidence_complete = change.diff_complete\n    base_ai_eligible = (\n        has_material_change\n        and not has_blocker\n        and evidence_complete\n        and policy.max_ai_passes > 0\n        and (request.force_ai or not change.docs_only)\n        and per_pass_total <= policy.token_budget\n    )\n    eligible_runtimes = _eligible_review_runtimes(request.primary_runtime, runtime_capacity)\n    passes = (\n        _specialist_passes(\n            project, change, risk, policy, request.primary_runtime, runtime_capacity,\n            estimated_input_tokens=per_pass_context_tokens,\n            output_token_reserve=output_token_reserve,\n        )\n        if base_ai_eligible and eligible_runtimes\n        else []\n    )\n    aggregate_context = sum(item.estimated_input_tokens for item in passes)\n    aggregate_total = sum(item.estimated_total_tokens for item in passes)\n    remaining_after_context = max(policy.token_budget - aggregate_context, 0)\n    remaining_after_plan = max(policy.token_budget - aggregate_total, 0)\n    ai_required = bool(passes)\n\n    if has_blocker:\n        reason = "Deterministic blocking finding must be resolved before any diff is sent to an AI reviewer."\n    elif not has_material_change:\n        reason = "No material local change was found, so spending review tokens would add no value."\n    elif not evidence_complete:\n        reason = "Exact diff evidence is incomplete, so Synapse will not spend review tokens or claim the change was reviewed yet."\n    elif change.docs_only and not request.force_ai:\n        reason = "Docs-only change passed through the token-free deterministic lane; AI review was skipped."\n    elif not eligible_runtimes:\n        reason = "No independent reviewer runtime is currently eligible according to Synapse runtime capacity; no doomed pass was queued."\n    elif per_pass_total > policy.token_budget:\n        reason = "One bounded review pass would exceed the configured aggregate planning budget; AI review was not queued."\n    elif not passes:\n        reason = "The configured aggregate planning budget did not justify another AI pass."\n    else:\n        reason = (\n            f"{policy.mode.value} review selected for {risk.value}-risk change with {len(passes)} "\n            f"targeted AI pass(es), reserving about {aggregate_total} of {policy.token_budget} tokens."\n        )\n\n    return ReviewPlan(\n        project_id=project.id,\n        project_name=project.name,\n        risk=risk,\n        mode=policy.mode,\n        policy=policy,\n        change=change,\n        estimated_context_tokens=aggregate_context,\n        budget_remaining_after_context=remaining_after_context,\n        estimated_tokens_per_pass=per_pass_total,\n        estimated_aggregate_tokens=aggregate_total,\n        budget_remaining_after_plan=remaining_after_plan,\n        ai_review_required=ai_required,\n        deterministic_findings=findings,\n        review_passes=passes,\n        reason=reason,\n    )\n\n\ndef bounded_diff_for_prompt'''
text, count = plan_pattern.subn(plan_replacement, text, count=1)
if count != 1:
    raise SystemExit("could not replace plan_project_review")
write(path, text)


# --- routes_review.py -------------------------------------------------------
path = "daemon/synapse_daemon/routes_review.py"
text = read(path)
text = replace_once(
    text,
    "from . import coder_workspace\n",
    "from . import ai_executions\nfrom . import coder_workspace\n",
    "review route capacity import",
)
text = replace_once(
    text,
    '''        f"Review token budget: {plan.policy.token_budget}\\n"\n        f"Estimated context tokens: {plan.estimated_context_tokens}\\n"\n        f"Why this pass exists: {pass_plan.reason}\\n\\n"\n''',
    '''        f"Aggregate Smart Review planning budget: {plan.policy.token_budget}\\n"\n        f"Aggregate reserved tokens: {plan.estimated_aggregate_tokens}\\n"\n        f"This pass input/context estimate: {pass_plan.estimated_input_tokens}\\n"\n        f"This pass output reserve: {pass_plan.output_token_reserve}\\n"\n        f"Why this pass exists: {pass_plan.reason}\\n\\n"\n''',
    "review prompt budget wording",
)
text = replace_once(
    text,
    '''        "- Recommend another AI pass only when its likely value justifies more tokens.\\n\\n"\n''',
    '''        "- Recommend another AI pass only when its likely value justifies more tokens.\\n"\n        f"- Keep the review concise enough to fit the ~{pass_plan.output_token_reserve}-token output reserve.\\n\\n"\n''',
    "review prompt output reserve",
)
text = replace_once(
    text,
    '''        review_request = payload or review_engine.ReviewEngineRequest()\n        return await asyncio.to_thread(review_engine.plan_project_review, project, review_request)\n''',
    '''        review_request = payload or review_engine.ReviewEngineRequest()\n        runtime_capacity = ai_executions.list_capacity(storage.conn)\n        return await asyncio.to_thread(\n            review_engine.plan_project_review,\n            project,\n            review_request,\n            runtime_capacity=runtime_capacity,\n        )\n''',
    "plan route runtime capacity",
)
text = replace_once(
    text,
    '''        review_request = payload or review_engine.ReviewEngineRequest()\n        plan = await asyncio.to_thread(review_engine.plan_project_review, project, review_request)\n''',
    '''        review_request = payload or review_engine.ReviewEngineRequest()\n        runtime_capacity = ai_executions.list_capacity(storage.conn)\n        plan = await asyncio.to_thread(\n            review_engine.plan_project_review,\n            project,\n            review_request,\n            runtime_capacity=runtime_capacity,\n        )\n''',
    "queue route runtime capacity",
)
text = replace_once(
    text,
    '''                existing_threads = coder_workspace.list_threads(conn, project_id)\n                thread = existing_threads[0] if existing_threads else coder_workspace.create_thread(\n                    conn,\n                    project_id,\n                    coder_workspace.CoderThreadCreate(\n                        title=f"Smart review · {project.name}",\n                        active_runtime_id=review_request.primary_runtime or "codex",\n                        thread_kind="review",\n                        metadata={"created_by": "review-engine", "review_engine_version": "v1"},\n                    ),\n                )\n''',
    '''                existing_threads = coder_workspace.list_threads(conn, project_id)\n                engine_thread = next(\n                    (\n                        item.thread\n                        for item in existing_threads\n                        if item.thread.metadata.get("created_by") == "review-engine"\n                    ),\n                    None,\n                )\n                thread = engine_thread or coder_workspace.create_thread(\n                    conn,\n                    project_id,\n                    coder_workspace.CoderThreadCreate(\n                        title=f"Smart review · {project.name}",\n                        active_runtime_id=review_request.primary_runtime or plan.review_passes[0].requested_runtime_id,\n                        thread_kind="review",\n                        metadata={"created_by": "review-engine", "review_engine_version": "v1"},\n                    ),\n                )\n''',
    "dedicated smart review thread",
)
text = replace_once(
    text,
    '''                                "token_budget": plan.policy.token_budget,\n                                "estimated_context_tokens": plan.estimated_context_tokens,\n                                "source": review_request.source,\n''',
    '''                                "token_budget": plan.policy.token_budget,\n                                "estimated_input_tokens": pass_plan.estimated_input_tokens,\n                                "output_token_reserve": pass_plan.output_token_reserve,\n                                "estimated_total_tokens": pass_plan.estimated_total_tokens,\n                                "estimated_aggregate_tokens": plan.estimated_aggregate_tokens,\n                                "budget_remaining_after_plan": plan.budget_remaining_after_plan,\n                                "budget_kind": "aggregate_planning_reserve",\n                                "source": review_request.source,\n''',
    "review pass budget metadata",
)
write(path, text)


# --- tests ------------------------------------------------------------------
path = "daemon/tests/test_review_engine.py"
text = read(path)
text = replace_once(
    text,
    "import json\n\nfrom synapse_daemon import review_engine\n",
    "import json\nfrom datetime import UTC, datetime\n\nimport pytest\n\nfrom synapse_daemon import ai_executions, coder_runtimes, review_engine\n",
    "review engine test imports",
)
fixture = '''\n\n@pytest.fixture(autouse=True)\ndef _pretend_default_runtimes_are_installed(monkeypatch) -> None:\n    # Pure planner tests do not have the daemon's SQLite capacity ledger.\n    monkeypatch.setattr(coder_runtimes, "available", lambda runtime: True)\n'''
if "def _pretend_default_runtimes_are_installed" not in text:
    insert_at = text.index("\n\ndef _project")
    text = text[:insert_at] + fixture + text[insert_at:]
append = '''\n\ndef test_aggregate_budget_counts_repeated_context_across_passes(tmp_path) -> None:\n    project = _project(tmp_path)\n    diff = "+x = 1\\n" * 18_000\n    plan = review_engine.plan_project_review(\n        project,\n        review_engine.ReviewEngineRequest(\n            mode=review_engine.ReviewMode.RELEASE,\n            changed_files=["src/app.py", "tests/test_app.py"],\n            diff_text=diff,\n            change_title="release v9.9.9",\n        ),\n    )\n    assert plan.review_passes\n    assert plan.estimated_aggregate_tokens == sum(\n        item.estimated_total_tokens for item in plan.review_passes\n    )\n    assert plan.estimated_context_tokens == sum(\n        item.estimated_input_tokens for item in plan.review_passes\n    )\n    assert plan.estimated_aggregate_tokens <= plan.policy.token_budget\n    assert plan.budget_remaining_after_plan == plan.policy.token_budget - plan.estimated_aggregate_tokens\n\n\ndef test_runtime_capacity_skips_unavailable_or_primary_reviewers(tmp_path) -> None:\n    now = datetime.now(UTC)\n    capacity = [\n        ai_executions.RuntimeCapacity(\n            runtime_id="codex", state=ai_executions.RuntimeCapacityState.AVAILABLE,\n            usable_now=True, eligible_for_attempt=True, updated_at=now,\n        ),\n        ai_executions.RuntimeCapacity(\n            runtime_id="claude", state=ai_executions.RuntimeCapacityState.QUOTA_EXHAUSTED,\n            usable_now=False, eligible_for_attempt=False, updated_at=now,\n        ),\n        ai_executions.RuntimeCapacity(\n            runtime_id="copilot", state=ai_executions.RuntimeCapacityState.AVAILABLE,\n            usable_now=True, eligible_for_attempt=True, updated_at=now,\n        ),\n    ]\n    plan = review_engine.plan_project_review(\n        _project(tmp_path),\n        review_engine.ReviewEngineRequest(\n            changed_files=["src/app.py", "tests/test_app.py"],\n            diff_text="+x = 1\\n",\n            primary_runtime="codex",\n        ),\n        runtime_capacity=capacity,\n    )\n    assert plan.ai_review_required is True\n    assert {item.requested_runtime_id for item in plan.review_passes} == {"copilot"}\n\n\ndef test_no_independent_runtime_means_no_doomed_review_pass(tmp_path) -> None:\n    now = datetime.now(UTC)\n    capacity = [\n        ai_executions.RuntimeCapacity(\n            runtime_id="codex", state=ai_executions.RuntimeCapacityState.AVAILABLE,\n            usable_now=True, eligible_for_attempt=True, updated_at=now,\n        ),\n        ai_executions.RuntimeCapacity(\n            runtime_id="claude", state=ai_executions.RuntimeCapacityState.NOT_INSTALLED,\n            usable_now=False, eligible_for_attempt=False, updated_at=now,\n        ),\n    ]\n    plan = review_engine.plan_project_review(\n        _project(tmp_path),\n        review_engine.ReviewEngineRequest(\n            changed_files=["src/app.py"], diff_text="+x = 1\\n", primary_runtime="codex"\n        ),\n        runtime_capacity=capacity,\n    )\n    assert plan.ai_review_required is False\n    assert plan.review_passes == []\n    assert "No independent reviewer runtime" in plan.reason\n\n\ndef test_common_secret_file_patterns_block_ai_context(tmp_path) -> None:\n    for secret_path in (".env.development", ".npmrc", "certs/private.pem", "config/credentials.yaml"):\n        plan = review_engine.plan_project_review(\n            _project(tmp_path),\n            review_engine.ReviewEngineRequest(\n                changed_files=[secret_path],\n                diff_text="+SAFE_EXAMPLE=placeholder-value\\n",\n                force_ai=True,\n            ),\n        )\n        assert plan.ai_review_required is False\n        assert any(item.id == "secret-file-changed" for item in plan.deterministic_findings)\n        assert "withheld" in review_engine.bounded_diff_for_prompt(plan)\n'''
if "test_aggregate_budget_counts_repeated_context_across_passes" not in text:
    text += append
write(path, text)

path = "daemon/tests/test_smart_review_routes.py"
text = read(path)
text = replace_once(
    text,
    "from fastapi.testclient import TestClient\n\nfrom synapse_daemon.app import build_app\n",
    "from fastapi.testclient import TestClient\nimport pytest\n\nfrom synapse_daemon import coder_runtimes\nfrom synapse_daemon.app import build_app\n",
    "smart review route test imports",
)
fixture = '''\n\n@pytest.fixture(autouse=True)\ndef _pretend_review_runtimes_are_installed(monkeypatch) -> None:\n    monkeypatch.setattr(coder_runtimes, "available", lambda runtime: True)\n'''
if "def _pretend_review_runtimes_are_installed" not in text:
    insert_at = text.index("\n\ndef _client")
    text = text[:insert_at] + fixture + text[insert_at:]
append = '''\n\ndef test_queue_uses_dedicated_engine_thread_when_project_already_has_threads(tmp_path: Path) -> None:\n    client = _client(tmp_path)\n    existing = client.post(\n        "/api/v1/projects/smart-review-demo/coder-threads",\n        json={"title": "Existing normal chat", "active_runtime_id": "codex"},\n    )\n    assert existing.status_code == 201, existing.text\n    normal_thread_id = existing.json()["thread"]["id"] if "thread" in existing.json() else existing.json()["id"]\n\n    queued_response = client.post("/api/v1/review/engine/queue/smart-review-demo", json=_payload())\n    assert queued_response.status_code == 201, queued_response.text\n    queued = queued_response.json()\n    assert queued["thread"]["id"] != normal_thread_id\n    assert queued["thread"]["metadata"]["created_by"] == "review-engine"\n    assert queued["queued"][0]["review_pass"]["metadata"]["budget_kind"] == "aggregate_planning_reserve"\n'''
if "test_queue_uses_dedicated_engine_thread_when_project_already_has_threads" not in text:
    text += append
write(path, text)


# --- docs / changelog -------------------------------------------------------
path = "docs/security.md"
text = read(path)
security_note = '''\n\n### Smart Review privacy boundary\n\nSmart Review never sends a diff to an AI reviewer when deterministic inspection sees a known\nsecret-bearing path (including `.env*`, `.npmrc`, key/certificate credential files, and common\ncredential/secret config names) or a secret-like assignment/Bearer value. Local changes with\nuntracked files also remain in the token-free evidence lane until their exact bounded content is\navailable. Review token budgets are **aggregate planning reserves**: repeated prompt context is\ncounted once per queued pass and each pass carries an explicit output reserve. Provider-reported\nactual usage remains authoritative in Synapse's normal execution/accounting ledger; the planning\nreserve is not represented as a provider-side hard output cap.\n'''
if "### Smart Review privacy boundary" not in text:
    text += security_note
write(path, text)

path = "CHANGELOG.md"
text = read(path)
marker = "### Added\n- **Token-aware Smart Review Engine** -- deterministic/privacy checks run before model spend, risk selects bounded review depth, project contracts can add focused invariants, and targeted passes reuse the existing coder-review runtime across registered projects.\n"
addition = marker + "\n### Fixed\n- **Smart Review review findings** -- project-scoped authorization is enforced, existing coder-thread summaries no longer break queueing because Smart Review uses its own engine-owned thread, reviewer choice follows canonical runtime capacity, common secret-bearing paths are withheld, untracked evidence fails closed, and aggregate planning budgets count repeated context across every queued pass.\n"
if "**Smart Review review findings**" not in text:
    if marker not in text:
        raise SystemExit("CHANGELOG Smart Review marker missing")
    text = text.replace(marker, addition, 1)
write(path, text)

print("Smart Review remediation applied")
