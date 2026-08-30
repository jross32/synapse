from synapse_daemon.operator_router import build_operator_plan, classify_intent, normalize_capabilities


def test_normalize_capabilities_aliases():
    assert normalize_capabilities(["reflex", "playwright", "wbscrper", "GitHub"]) == {
        "desktop",
        "browser",
        "web_scraper",
        "github",
    }


def test_classify_diagnose_precedes_generic_fix_words():
    assert classify_intent("Fix the Synapse 502 timeout") == "diagnose"


def test_diagnose_plan_prefers_trace_watchdog_shell_before_desktop():
    plan = build_operator_plan(
        "Synapse is stuck and timing out; fix it",
        ["trace", "watchdog", "synapse", "reflex"],
    )
    assert plan.mode == "diagnose"
    assert [step.capability for step in plan.steps] == ["trace", "watchdogs", "shell", "desktop"]
    assert plan.missing_capabilities == ()


def test_research_plan_uses_scraper_then_browser():
    plan = build_operator_plan("Research current coupon deals", ["wbscrper", "playwright", "reflex"])
    assert plan.mode == "research"
    assert [step.capability for step in plan.steps] == ["web_scraper", "browser"]


def test_browser_plan_reports_missing_browser_but_keeps_desktop_fallback():
    plan = build_operator_plan("Open the website and log in", ["reflex"])
    assert plan.mode == "browser_operate"
    assert [step.capability for step in plan.steps] == ["desktop"]
    assert plan.missing_capabilities == ("browser",)


def test_developer_plan_has_verification_contract():
    plan = build_operator_plan("Implement and test this project", ["synapse", "github", "playwright", "trace"])
    assert plan.mode == "developer"
    shell_step = next(step for step in plan.steps if step.capability == "shell")
    assert "tests" in (shell_step.verification or "")
