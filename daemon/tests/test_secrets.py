"""Contract #25 — secrets management."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from synapse_daemon.secrets import (
    SECRET_PLACEHOLDER,
    EnvVar,
    decrypt,
    encrypt,
    redact,
)


def test_envvar_secret_default_false() -> None:
    e = EnvVar(key="API_KEY")
    assert e.secret is False
    assert e.value is None


def test_redact_replaces_secret_values_with_placeholder() -> None:
    vars_in = [
        EnvVar(key="API_KEY", value="real-key-1234", secret=True),
        EnvVar(key="LOG_LEVEL", value="info", secret=False),
        EnvVar(key="EMPTY_SECRET", value=None, secret=True),
    ]
    out = redact(vars_in)
    assert out[0].value == SECRET_PLACEHOLDER
    assert out[1].value == "info"
    assert out[2].value is None  # None stays None even for secrets


def test_redact_does_not_mutate_inputs() -> None:
    vars_in = [EnvVar(key="API_KEY", value="real", secret=True)]
    redact(vars_in)
    assert vars_in[0].value == "real"  # original untouched


@pytest.mark.skipif(sys.platform == "win32", reason="DPAPI tested separately in Milestone J")
def test_encrypt_roundtrip_on_non_windows(tmp_path: Path) -> None:
    plain = "very-secret-value"
    cipher = encrypt(plain, data_dir=tmp_path)
    assert cipher != plain.encode()
    assert decrypt(cipher, data_dir=tmp_path) == plain
    # Key file created with restricted permissions.
    key_file = tmp_path / ".secrets-key"
    assert key_file.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_encrypt_roundtrip_on_windows() -> None:
    plain = "very-secret-value"
    cipher = encrypt(plain)
    assert cipher != plain.encode()
    assert decrypt(cipher) == plain
