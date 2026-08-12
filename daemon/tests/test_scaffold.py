"""Tests for the generation scaffold.

Each of these guards a defect that actually shipped in the build-off
(`benchmarks/app-build/RESULTS.md`), so they are regression tests rather than speculation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from synapse_daemon.scaffold import assertions as A
from synapse_daemon.scaffold import contracts as C
from synapse_daemon.scaffold import partials as P


def _run_async(coro):
    """Own loop: pytest-asyncio has already installed a policy, and asyncio.run() then
    blocks forever instead of failing loudly."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------- partials


def test_field_cannot_be_emitted_without_a_label():
    """The build-off shipped pages with zero labels. The label is a required argument here,
    so there is no call that produces an unlabelled input."""
    html = P.field("email", "Email address", kind="email", autocomplete="email")
    assert '<label for="email">Email address</label>' in html
    assert 'id="email"' in html and 'type="email"' in html
    assert 'autocomplete="email"' in html


def test_field_escapes_attacker_controlled_names():
    html = P.field('x" onfocus="alert(1)', "Label")
    assert 'onfocus="alert(1)' not in html
    assert "&quot;" in html


def test_page_ships_the_kit_and_an_escaping_helper():
    html = P.page("Title", "<p>body</p>")
    assert "viewport" in html and "<style>" in html
    # Every page carries escapeHtml, so client-side rendering has a safe default available -
    # its absence is what produced the stored XSS.
    assert "function escapeHtml" in html
    assert "--tap: 44px" in html, "tap-target token must reach the page"


def test_esc_neutralises_markup():
    assert P.esc('<img src=x onerror="1">') == "&lt;img src=x onerror=&quot;1&quot;&gt;"


# ---------------------------------------------------------------- contracts


def test_contract_detects_a_renamed_field(tmp_path: Path):
    """The exact build-off failure: one module returned distance_km, its consumer read
    distance, each passed its own test, and the dashboard rendered nothing."""
    mod = tmp_path / "storage.py"
    mod.write_text("def add_trail(user_id, name, distance):\n    return {}\n", encoding="utf-8")

    expected = C.ModuleContract(module="storage", functions=[
        C.FunctionSpec(name="add_trail", args=["user_id", "name", "distance_km"])])
    problems = C.check_contract(mod, expected)

    assert problems, "signature drift must be caught"
    assert "distance_km" in problems[0], "the message must name the expected signature"


def test_contract_reports_a_missing_function_with_what_does_exist(tmp_path: Path):
    """Arm B invented storage.user_exists() four times. Listing what *is* defined is the
    information that stops the guessing."""
    mod = tmp_path / "storage.py"
    mod.write_text("def get_user_by_email(email):\n    return None\n", encoding="utf-8")

    problems = C.check_contract(mod, C.ModuleContract(
        module="storage", functions=[C.FunctionSpec(name="user_exists", args=["email"])]))

    assert problems
    assert "get_user_by_email" in problems[0], "must list the functions that do exist"


def test_public_interface_reads_real_signatures(tmp_path: Path):
    mod = tmp_path / "m.py"
    mod.write_text("MAX = 3\ndef pub(a, b): ...\ndef _priv(): ...\n", encoding="utf-8")
    got = C.public_interface(mod)
    assert [f.name for f in got.functions] == ["pub"], "private helpers are not contract"
    assert "MAX" in got.constants


# ---------------------------------------------------------------- assertions


def test_assertions_state_got_and_expected():
    """A bare AssertionError cost four wasted repairs; the message is the fix."""
    with pytest.raises(AssertionError) as exc:
        A.equals(4, 5, "field count", hint="hash_password and verify_password must agree")
    text = str(exc.value)
    assert "expected: 5" in text and "actually got: 4" in text
    assert "likely cause" in text


def test_status_assertion_explains_a_5xx():
    with pytest.raises(AssertionError) as exc:
        A.status_is(500, 422, "POST /api/signup")
    assert "the handler raised" in str(exc.value)


def test_fields_match_names_the_missing_key_and_lists_what_exists():
    with pytest.raises(AssertionError) as exc:
        A.fields_match({"distance_km": 1, "name": "x"}, ["distance", "name"], "trail row")
    text = str(exc.value)
    assert "['distance']" in text and "distance_km" in text


# ---------------------------------------------------------------- early escalation


def test_pipeline_stops_when_the_same_error_repeats(tmp_path, monkeypatch):
    """Arm B spent ~20 minutes emitting four identical errors. Two is enough to know."""
    from synapse_daemon import local_pipeline as LP

    calls = {"n": 0}

    def fake_generate(spec, *a, **k):
        calls["n"] += 1
        # Always "changes" the code so the existing no-change guard cannot be what stops it.
        return f"def add(a, b):\n    return a - b  # attempt {calls['n']}\n"

    def always_same_error(_path, _cwd, timeout=45.0):
        return False, ("Traceback:\n  File \"/tmp/x.py\", line 3, in <module>\n"
                       "AttributeError: module 'storage' has no attribute 'user_exists'")

    monkeypatch.setattr(LP, "generate_code", fake_generate)

    result = _run_async(LP.run_pipeline("Write add(a, b).", workspace=tmp_path,
                                        max_repairs=10, runner=always_same_error))

    assert not result.passed
    assert "same error" in result.stop_reason, result.stop_reason
    assert len(result.attempts) <= 3, (
        f"should escalate after the error repeats, not burn all 10 attempts "
        f"(took {len(result.attempts)})")


def test_fingerprint_ignores_line_numbers_and_paths():
    from synapse_daemon.local_pipeline import error_fingerprint as fp
    a = 'File "/tmp/aaa/x.py", line 12\nValueError: too many values to unpack'
    b = 'File "/tmp/bbb/y.py", line 88\nValueError: too many values to unpack'
    assert fp(a) == fp(b)
    assert fp(a) != fp("AssertionError: anonymous must be 401")
