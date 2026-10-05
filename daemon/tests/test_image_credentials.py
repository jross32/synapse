"""Tests for encrypted image-provider credentials."""

from __future__ import annotations

import json
from pathlib import Path

from synapse_daemon import image_credentials
from synapse_daemon.storage import Storage


def _storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "data")
    storage.open()
    storage.migrate()
    return storage


def test_stored_openai_key_is_encrypted_and_round_trips(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    storage = _storage(tmp_path)
    plaintext = "sk-test-super-secret-image-key"

    status = image_credentials.set_openai_api_key(storage, plaintext)

    assert status["configured"] is True
    assert status["source"] == "synapse_secret"
    assert status["stored_secret"] is True
    row = storage.conn.execute(
        "SELECT value_json FROM settings WHERE key = ?",
        ("image.openai_api_key",),
    ).fetchone()
    assert row is not None
    assert plaintext not in row["value_json"]
    payload = json.loads(row["value_json"])
    assert payload["ciphertext_b64"]
    assert image_credentials.stored_openai_api_key(storage) == plaintext


def test_environment_override_wins_without_exposing_value(
    tmp_path: Path, monkeypatch
) -> None:
    storage = _storage(tmp_path)
    image_credentials.set_openai_api_key(storage, "stored-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "environment-secret")

    resolved, source = image_credentials.resolve_openai_api_key(storage)
    status = image_credentials.credential_status(storage)

    assert resolved == "environment-secret"
    assert source == "environment"
    assert status == {
        "provider": "openai",
        "configured": True,
        "source": "environment",
        "environment_override": True,
        "stored_secret": True,
    }
    assert "environment-secret" not in json.dumps(status)
    assert "stored-secret" not in json.dumps(status)


def test_clear_removes_only_stored_secret(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    storage = _storage(tmp_path)
    image_credentials.set_openai_api_key(storage, "stored-secret")

    status = image_credentials.clear_openai_api_key(storage)

    assert status["configured"] is False
    assert status["source"] is None
    assert status["stored_secret"] is False
    assert image_credentials.stored_openai_api_key(storage) is None
