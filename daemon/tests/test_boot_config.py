"""Boot-time config load/save resilience -- the paths a route test never hits.

boot_config decides the listen host BEFORE SQLite is open, so it must never crash the daemon over
a bad file. These pin every documented degrade-to-defaults path + the atomic save.
"""

from __future__ import annotations

from pathlib import Path

from synapse_daemon.boot_config import BootConfig, load, save


def test_load_missing_returns_defaults(tmp_path: Path) -> None:
    cfg = load(tmp_path)
    assert cfg == BootConfig()
    assert cfg.bind_lan is False


def test_save_load_roundtrip(tmp_path: Path) -> None:
    save(tmp_path, BootConfig(bind_lan=True))
    assert load(tmp_path).bind_lan is True


def test_load_bad_json_returns_defaults(tmp_path: Path) -> None:
    (tmp_path / "boot-config.json").write_text("{not valid json", encoding="utf-8")
    assert load(tmp_path).bind_lan is False


def test_load_non_dict_json_returns_defaults(tmp_path: Path) -> None:
    (tmp_path / "boot-config.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert load(tmp_path).bind_lan is False


def test_load_ignores_unknown_keys(tmp_path: Path) -> None:
    (tmp_path / "boot-config.json").write_text(
        '{"bind_lan": true, "future_knob": 5}', encoding="utf-8"
    )
    # Unknown key is ignored (forward-compat), known key still applied.
    assert load(tmp_path).bind_lan is True


def test_load_ignores_wrong_typed_bind_lan(tmp_path: Path) -> None:
    # A truthy string must NOT be accepted as the bool -- stays the default.
    (tmp_path / "boot-config.json").write_text('{"bind_lan": "yes"}', encoding="utf-8")
    assert load(tmp_path).bind_lan is False


def test_save_creates_data_dir_and_leaves_no_tmp(tmp_path: Path) -> None:
    nested = tmp_path / "brand" / "new" / "dir"
    save(nested, BootConfig(bind_lan=True))
    assert (nested / "boot-config.json").is_file()
    # Atomic write must not leave a stray .tmp behind.
    assert not list(nested.glob("*.tmp"))
    assert load(nested).bind_lan is True
