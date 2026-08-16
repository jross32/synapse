"""Scenario boilerplate, generated. The judgement is still yours; the typing is not.

The safety property that matters: a skeleton must FAIL until someone fills it in. A stub that
passed while asserting nothing would be a false pass wearing a TODO, which is the exact
failure this project keeps catching.
"""

from __future__ import annotations

from synapse_daemon.scenario_skeleton import scenario_skeleton

FUNCTIONS = [
    {"name": "read_rows", "args": ["text", "required"], "doc": "Parse a CSV."},
    {"name": "init_db", "args": []},
    {"name": "delete_record", "args": ["record_id", "user_id"]},
    {"name": "_private", "args": []},
]


def test_it_is_valid_python():
    compile(scenario_skeleton("reader", FUNCTIONS), "<s>", "exec")


def test_every_stub_fails_until_it_is_replaced():
    """An unfinished scenario must never report a pass."""
    src = scenario_skeleton("reader", FUNCTIONS)
    stubs = src.count("assert False")
    assert stubs == 3, f"expected one failing stub per public function, got {stubs}"

    namespace = {"read_rows": lambda *a: "x", "init_db": lambda: None,
                 "delete_record": lambda *a: True}
    try:
        exec(compile(src, "<s>", "exec"), namespace)
    except AssertionError as exc:
        assert "TODO" in str(exc)
    else:  # pragma: no cover - the point of the test
        raise AssertionError("a skeleton with no assertions filled in passed")


def test_private_functions_are_not_part_of_the_interface():
    assert "_private" not in scenario_skeleton("reader", FUNCTIONS)


def test_placeholder_arguments_are_typed_by_name():
    """`user_id` wants a number; a string there fails for the wrong reason."""
    src = scenario_skeleton("storage", FUNCTIONS)
    assert "delete_record(0, 0)" in src
    assert 'read_rows("", "")' in src
    assert "init_db()" in src


def test_the_header_says_what_a_scenario_is_for():
    src = scenario_skeleton("reader", FUNCTIONS)
    assert "CALLER" in src
    assert "never pass" in src


def test_no_functions_still_produces_a_usable_file():
    src = scenario_skeleton("empty", [])
    compile(src, "<s>", "exec")
    assert "assert False" not in src
    assert src.endswith("\n")


def test_missing_keys_do_not_raise():
    src = scenario_skeleton("m", [{"name": "f"}])
    compile(src, "<s>", "exec")
    assert "f()" in src
