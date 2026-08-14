"""Repair the function that failed, not the whole file.

The measured failure mode is regression, not incapacity. Building `storage` locally, the
scenario positions ran `[18, 21, 18]`: the model fixed `create_user`, advanced to the next
assertion, then broke `create_user` again - because a repair prompt asks for the entire
module back and the model rewrites all nine functions to change one.

Splicing a single function into the existing file makes that structurally impossible instead
of merely discouraged.
"""

from __future__ import annotations

import asyncio

from synapse_daemon.local_pipeline import (
    failing_function,
    public_functions,
    run_pipeline,
    splice_function,
)

MODULE = '''"""A module."""
import sqlite3


def alpha(x):
    """First."""
    return x + 1


def beta(y):
    return y * 2


def gamma():
    return "unchanged"
'''


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_public_functions_reports_line_ranges():
    found = public_functions(MODULE)
    assert set(found) == {"alpha", "beta", "gamma"}
    start, end = found["alpha"]
    assert MODULE.splitlines()[start - 1].startswith("def alpha")
    assert MODULE.splitlines()[end - 1].strip() == "return x + 1"


def test_the_failing_function_is_read_from_the_traceback_frame():
    error = ('Traceback (most recent call last):\n'
             '  File "_test.py", line 3, in <module>\n'
             '  File "mod.py", line 9, in beta\n'
             'TypeError: bad')
    assert failing_function(error, public_functions(MODULE)) == "beta"


def test_the_failing_function_is_read_from_a_scenario_message():
    """Blueprint scenarios deliberately phrase failures as 'alpha must RETURN ...'."""
    error = "AssertionError: alpha must RETURN the new id, it returned None"
    assert failing_function(error, public_functions(MODULE)) == "alpha"


def test_an_ambiguous_failure_is_not_pinned_on_a_guess():
    """Repairing the wrong function is worse than repairing the file - it looks targeted."""
    error = "AssertionError: alpha and beta disagree"
    assert failing_function(error, public_functions(MODULE)) == ""


def test_a_name_that_is_not_defined_is_never_targeted():
    error = "AssertionError: delta must return a dict"
    assert failing_function(error, public_functions(MODULE)) == ""


def test_splicing_replaces_one_function_and_nothing_else():
    spliced = splice_function(MODULE, "beta", "def beta(y):\n    return y * 3\n")
    assert "return y * 3" in spliced
    # Every other line survives byte-identical. This is the entire point.
    assert '"""A module."""' in spliced
    assert "import sqlite3" in spliced
    assert "return x + 1" in spliced
    assert 'return "unchanged"' in spliced
    assert public_functions(spliced).keys() == public_functions(MODULE).keys()


def test_splicing_tolerates_a_replacement_wrapped_in_other_text():
    """Models return the function with imports or a stray helper around it."""
    spliced = splice_function(
        MODULE, "beta", "import math\n\n\ndef beta(y):\n    return math.floor(y * 3)\n")
    assert "math.floor(y * 3)" in spliced
    assert "return x + 1" in spliced


def test_splicing_refuses_rather_than_producing_a_broken_file():
    assert splice_function(MODULE, "beta", "def beta(y:\n  return") == ""
    assert splice_function(MODULE, "beta", "def unrelated():\n    pass\n") == ""
    assert splice_function(MODULE, "nosuch", "def nosuch():\n    pass\n") == ""


def test_a_targeted_repair_cannot_regress_a_neighbouring_function(tmp_path, monkeypatch):
    """The end-to-end version of the measured `[18, 21, 18]` regression."""
    import synapse_daemon.local_pipeline as lp

    # The first draft gets beta right and alpha wrong.
    draft = "def alpha():\n    return 0\n\n\ndef beta():\n    return 2\n"
    # A whole-file rewrite that fixes alpha and breaks beta - the measured `[18, 21, 18]`.
    sabotage = "def alpha():\n    return 1\n\n\ndef beta():\n    return 999\n"

    prompts: list[str] = []

    def stub(spec: str, *a, **k) -> str:
        if "Write a test for that code" in spec:
            return ("from solution import *\n\nassert alpha() == 1\nassert beta() == 2\n"
                    "print('OK')\n")
        prompts.append(spec)
        if "Rewrite ONLY the function" in spec:
            return "def alpha():\n    return 1\n"
        if "Running the tests produced" in spec:
            return sabotage  # what a whole-file repair would have done
        return draft

    monkeypatch.setattr(lp, "generate_code", stub)

    calls = {"n": 0}

    def runner(test_file, cwd):
        calls["n"] += 1
        if calls["n"] == 1:
            return False, ('Traceback (most recent call last):\n'
                           '  File "solution.py", line 2, in alpha\n'
                           'AssertionError: alpha must return 1')
        return True, ""

    result = _run_async(run_pipeline("spec", workspace=tmp_path, max_repairs=2,
                                     runner=runner, targeted=True))

    assert any("Rewrite ONLY the function `alpha`" in p for p in prompts), (
        f"the repair was not targeted at the named function: {prompts}")
    assert "return 999" not in result.code, (
        "the targeted repair let a whole-file rewrite through and broke beta")
    assert "def beta():\n    return 2" in result.code


def test_targeting_off_uses_the_whole_file_repair(tmp_path, monkeypatch):
    """The switch has to actually switch, or the A/B measures nothing."""
    import synapse_daemon.local_pipeline as lp

    prompts: list[str] = []

    def stub(spec: str, *a, **k) -> str:
        if "Write a test for that code" in spec:
            return "from solution import *\n\nassert alpha() == 1\nprint('OK')\n"
        prompts.append(spec)
        return "def alpha():\n    return 1\n"

    monkeypatch.setattr(lp, "generate_code", stub)

    calls = {"n": 0}

    def runner(test_file, cwd):
        calls["n"] += 1
        return (False, 'File "solution.py", line 2, in alpha\nAssertionError: no') \
            if calls["n"] == 1 else (True, "")

    _run_async(run_pipeline("spec", workspace=tmp_path, max_repairs=2, runner=runner,
                            targeted=False))

    assert not any("Rewrite ONLY the function" in p for p in prompts), (
        "targeted repair ran while switched off")


def test_the_models_own_test_can_be_demoted_to_advisory(tmp_path, monkeypatch):
    """With a blueprint scenario present, the model's test is a second opinion.

    It has asserted `user_id == 1` (true only of a fresh database) and its message-less
    assertions collided into one fingerprint that stopped a progressing loop early. Skipping
    it also saves a whole generation per piece.
    """
    import synapse_daemon.local_pipeline as lp

    asked_for_test = {"yes": False}

    def stub(spec: str, *a, **k) -> str:
        if "Write a test for that code" in spec:
            asked_for_test["yes"] = True
            return "from solution import *\n\nassert False, 'model test ran'\n"
        return "def value():\n    return 1\n"

    monkeypatch.setattr(lp, "generate_code", stub)
    result = _run_async(run_pipeline(
        "spec", workspace=tmp_path, max_repairs=0,
        extra_test="assert value() == 1, 'scenario ran'",
        advisory_model_test=True))

    assert not asked_for_test["yes"], "a generation was spent on a test that is not the gate"
    assert result.passed
    assert "model test ran" not in result.test_code
    assert "scenario ran" in result.test_code, "the scenario must still be the gate"
