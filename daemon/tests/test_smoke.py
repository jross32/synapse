"""Milestone A smoke test — proves the package imports and version is set."""

from __future__ import annotations

import re

import synapse_daemon


def test_version_string_present() -> None:
    assert isinstance(synapse_daemon.__version__, str)
    # PEP 440 pre-release like "0.1.0a1" or release like "0.1.0"
    assert re.match(r"^\d+\.\d+\.\d+([abrc]\d+|\.dev\d+|\.post\d+)?$", synapse_daemon.__version__)


def test_entrypoint_importable() -> None:
    from synapse_daemon import __main__

    assert callable(__main__.main)
