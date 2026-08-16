"""Drafting a blueprint from an app that already works.

Authoring a blueprint by hand is the expensive part of the whole system, and the only thing
standing between "delegate this shape" and "delegate anything". Most of it is mechanical.
The part that is not - the acceptance scenario - is deliberately left empty.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_daemon.blueprints import distil_from_build, get_blueprint

REPO = Path(__file__).resolve().parents[2]
PHASE_D = REPO / "benchmarks" / "app-build" / "phase-d-cli"


@pytest.fixture()
def drafted():
    if not PHASE_D.exists():
        pytest.skip("phase-d-cli build not present")
    return distil_from_build(PHASE_D, blueprint_id="drafted-cli", name="Drafted CLI")


def test_it_recovers_the_shape_of_the_hand_written_blueprint(drafted):
    """The CLI blueprint was written by hand; distilling its build should find it again."""
    assert {p.name for p in drafted.pieces} == {"reader", "summary", "cli"}
    assert drafted.entrypoint["path"] == "report.py"

    original = {p.name for p in get_blueprint("cli-csv-report").pieces}
    assert {p.name for p in drafted.pieces} == original


def test_the_entrypoint_is_the_module_nothing_imports(drafted):
    """`cli.py` defines main() and looks main-like, but `report.py` imports it.

    Keying on "imports the most modules" picked cli.py, which is a dependency.
    """
    assert drafted.entrypoint["path"] == "report.py"
    assert "cli" in {p.name for p in drafted.pieces}


def test_contracts_and_dependencies_come_off_the_source(drafted):
    by_name = {p.name: p for p in drafted.pieces}
    assert sorted(by_name["cli"].depends_on) == ["reader", "summary"]
    assert by_name["reader"].depends_on == []

    reader_fns = {f["name"] for f in by_name["reader"].contract["functions"]}
    assert "read_rows" in reader_fns


def test_scenarios_are_left_empty_and_the_draft_says_so(drafted):
    """A scenario says what a CALLER needs, which is not recoverable from working code.

    Inferring one from the implementation would assert whatever the code already does - a
    check that cannot fail, which is worse than no check.
    """
    assert drafted.draft is True
    assert drafted.source == "distilled"

    # A skeleton is supplied, not a scenario: every stub FAILS until someone states what a
    # caller needs. That is a stronger guarantee than leaving `tests` empty, which would let
    # a draft run and report nothing wrong.
    for piece in drafted.pieces:
        if not piece.contract["functions"]:
            continue
        assert "assert False" in piece.tests, f"{piece.name} has no failing stub"
        assert "TODO" in piece.tests


def test_installed_scaffold_assets_are_not_mistaken_for_app_code(drafted):
    """`scaffold_partials.py` is copied into every workspace by the scaffold itself."""
    assert "scaffold_partials" not in {p.name for p in drafted.pieces}


def test_an_empty_directory_drafts_an_empty_blueprint(tmp_path):
    blueprint = distil_from_build(tmp_path, blueprint_id="empty", name="Empty")
    assert blueprint.pieces == [] and blueprint.draft is True
