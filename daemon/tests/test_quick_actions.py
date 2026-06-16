"""Unit tests for the quick-action template loader (ADR-0003 Phase F · v0.1.34)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synapse_daemon.quick_actions import (
    QuickActionError,
    find_template,
    load_templates,
)


def _write(dir_path: Path, name: str, payload: dict) -> Path:
    f = dir_path / name
    f.write_text(json.dumps(payload), encoding="utf-8")
    return f


def _valid(action_id: str = "do-thing", **overrides) -> dict:
    return {
        "id": action_id,
        "name": "Do Thing",
        "description": "Walk me through doing a thing.",
        "prompt": "Tell me about a thing.",
        "icon": "wand",
        "default_argv": ["claude"],
        **overrides,
    }


def test_load_templates_returns_empty_when_dir_missing(tmp_path: Path) -> None:
    assert load_templates(tmp_path / "does-not-exist") == []


def test_load_templates_reads_all_jsons_and_sorts_by_name(tmp_path: Path) -> None:
    _write(tmp_path, "a.json", _valid("zebra-action", name="Zebra"))
    _write(tmp_path, "b.json", _valid("alpha-action", name="Alpha"))
    out = load_templates(tmp_path)
    assert [a.id for a in out] == ["alpha-action", "zebra-action"]
    assert out[0].default_argv == ["claude"]


def test_load_templates_skips_malformed_files(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text("{this is not json", encoding="utf-8")
    _write(tmp_path, "ok.json", _valid())
    out = load_templates(tmp_path)
    assert len(out) == 1
    assert out[0].id == "do-thing"


def test_load_templates_skips_missing_required_fields(tmp_path: Path) -> None:
    bad = _valid()
    del bad["prompt"]
    _write(tmp_path, "bad.json", bad)
    assert load_templates(tmp_path) == []


def test_load_templates_rejects_non_kebab_id(tmp_path: Path) -> None:
    _write(tmp_path, "underscored.json", _valid("_leading-underscore"))
    _write(tmp_path, "spaced.json", _valid("has spaces"))
    _write(tmp_path, "ok.json", _valid())
    out = load_templates(tmp_path)
    assert [a.id for a in out] == ["do-thing"]


def test_load_templates_first_id_wins_on_duplicates(tmp_path: Path) -> None:
    _write(tmp_path, "01.json", _valid(name="First"))
    _write(tmp_path, "02.json", _valid(name="Second copy"))
    out = load_templates(tmp_path)
    assert len(out) == 1
    assert out[0].name == "First"


def test_load_templates_rejects_non_list_default_argv(tmp_path: Path) -> None:
    _write(tmp_path, "bad.json", _valid(default_argv="claude"))
    assert load_templates(tmp_path) == []


def test_find_template_picks_by_id(tmp_path: Path) -> None:
    _write(tmp_path, "a.json", _valid("alpha"))
    _write(tmp_path, "b.json", _valid("beta"))
    assert find_template("beta", tmp_path).id == "beta"
    assert find_template("gamma", tmp_path) is None


def test_to_dict_round_trips_fields(tmp_path: Path) -> None:
    _write(tmp_path, "a.json", _valid())
    action = load_templates(tmp_path)[0]
    d = action.to_dict()
    assert d["id"] == "do-thing"
    assert d["prompt"] == "Tell me about a thing."
    assert d["default_argv"] == ["claude"]
    assert d["icon"] == "wand"


def test_bundled_templates_load_cleanly() -> None:
    """The repo ships two templates -- make sure they parse without errors."""

    out = load_templates()
    ids = [a.id for a in out]
    # Both bundled templates exist (or the templates dir doesn't exist in a
    # bare checkout, in which case skip silently).
    if not ids:
        pytest.skip("no bundled templates available in this checkout")
    assert "new-mcp-server" in ids
    assert "new-synapse-tool" in ids
