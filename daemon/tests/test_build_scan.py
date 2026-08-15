"""Scanning a working app for its structure, checked against builds that exist on disk."""

from __future__ import annotations

from pathlib import Path

from synapse_daemon.build_scan import scan_build

REPO = Path(__file__).resolve().parents[2]
PHASE_D = REPO / "benchmarks" / "app-build" / "phase-d-cli"


def _by_module(rows: list[dict]) -> dict[str, dict]:
    return {r["module"]: r for r in rows}


def test_scans_a_real_built_app(tmp_path):
    """phase-d-cli was built by the ladder and works; it is the honest fixture."""
    if not PHASE_D.exists():
        import pytest
        pytest.skip("phase-d-cli build not present")

    rows = _by_module(scan_build(PHASE_D))
    assert {"reader", "summary", "cli", "report"} <= set(rows)

    reader = rows["reader"]
    assert any(f["name"] == "read_rows" for f in reader["functions"])
    assert reader["path"] == "reader.py"

    # `report.py` is the entrypoint: it has main() and the __main__ guard.
    assert rows["report"]["is_entrypoint"]
    assert not rows["reader"]["is_entrypoint"], "a plain module is not an entrypoint"


def test_local_imports_become_dependencies(tmp_path):
    (tmp_path / "a.py").write_text("def one():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text(
        "import a\nimport json\nfrom a import one\n\ndef two():\n    return one()\n",
        encoding="utf-8")

    rows = _by_module(scan_build(tmp_path))
    assert rows["b"]["imports_local"] == ["a"], "json is not a local module"
    assert rows["a"]["imports_local"] == []


def test_scaffolding_files_are_not_part_of_the_app(tmp_path):
    for name in ("_test_x.py", "test_x.py", "x_test.py", "conftest.py", "setup.py",
                 "_private.py"):
        (tmp_path / name).write_text("def f():\n    pass\n", encoding="utf-8")
    (tmp_path / "real.py").write_text("def f():\n    pass\n", encoding="utf-8")

    assert [r["module"] for r in scan_build(tmp_path)] == ["real"]


def test_only_public_module_level_functions_count(tmp_path):
    (tmp_path / "m.py").write_text(
        "CONST = 1\n\n"
        "class K:\n    def method(self):\n        pass\n\n"
        "def _private():\n    pass\n\n"
        "def public(a, b):\n    '''Does a thing.'''\n"
        "    def nested():\n        pass\n"
        "    return a\n",
        encoding="utf-8")

    row = scan_build(tmp_path)[0]
    assert [f["name"] for f in row["functions"]] == ["public"]
    assert row["functions"][0]["args"] == ["a", "b"]
    assert row["functions"][0]["doc"] == "Does a thing."
    assert row["constants"] == ["CONST"]


def test_a_broken_file_is_skipped_not_raised(tmp_path):
    (tmp_path / "good.py").write_text("def f():\n    pass\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("def (((\n", encoding="utf-8")

    assert [r["module"] for r in scan_build(tmp_path)] == ["good"]


def test_missing_directory_is_empty_not_an_error(tmp_path):
    assert scan_build(tmp_path / "nope") == []
    assert scan_build(tmp_path) == []
