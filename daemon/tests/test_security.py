"""Contract #16 — refuse Administrator unless explicitly allowed."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from synapse_daemon.security import assert_not_admin


def test_assert_not_admin_passes_when_not_admin() -> None:
    with patch("synapse_daemon.security.is_admin", return_value=False):
        # Must not raise.
        assert_not_admin()


def test_assert_not_admin_exits_when_admin_without_flag() -> None:
    with patch("synapse_daemon.security.is_admin", return_value=True):
        with pytest.raises(SystemExit) as exc:
            assert_not_admin(allow_admin=False)
        assert exc.value.code == 2


def test_assert_not_admin_allows_admin_when_flag_set() -> None:
    with patch("synapse_daemon.security.is_admin", return_value=True):
        # Must not raise.
        assert_not_admin(allow_admin=True)
