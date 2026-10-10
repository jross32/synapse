"""Focused safeguards for Claude Code authentication in Synapse profiles."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from synapse_daemon.profile import ProfileManager, ServiceConnectionStatus

ROOT = Path(__file__).resolve().parents[2]

class ClaudeProfileAuthTests(unittest.TestCase):
    def manager(self):
        manager = ProfileManager.__new__(ProfileManager)
        manager._local_detect_cache = {}
        return manager

    def test_healthy_cli_status_marks_connected(self):
        with patch("synapse_daemon.profile.resolve_command", return_value="claude.cmd"), patch(
            "synapse_daemon.profile.subprocess.run", return_value=SimpleNamespace(returncode=0)
        ) as run:
            result = self.manager()._detect_local_service(
                "claude-code", SimpleNamespace(id="desktop"), use_cache=False
            )
        self.assertEqual(result.status, ServiceConnectionStatus.READY)
        self.assertTrue(result.details["auth_verified"])
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][1:], ["auth", "status"])

    def test_expired_cli_status_does_not_mark_connected(self):
        with patch("synapse_daemon.profile.resolve_command", return_value="claude.cmd"), patch(
            "synapse_daemon.profile.subprocess.run", return_value=SimpleNamespace(returncode=1)
        ):
            result = self.manager()._detect_local_service(
                "claude-code", SimpleNamespace(id="desktop"), use_cache=False
            )
        self.assertEqual(result.status, ServiceConnectionStatus.NEEDS_ATTENTION)
        self.assertFalse(result.details["auth_verified"])

    def test_no_cli_never_marks_connected(self):
        with patch("synapse_daemon.profile.resolve_command", return_value=None), patch(
            "synapse_daemon.profile.subprocess.run"
        ) as run:
            result = self.manager()._detect_local_service(
                "claude-code", SimpleNamespace(id="desktop"), use_cache=False
            )
        self.assertEqual(result.status, ServiceConnectionStatus.DISCONNECTED)
        run.assert_not_called()

    def test_login_cannot_be_started_from_remote_api(self):
        api = (ROOT / "daemon" / "synapse_daemon" / "routes_profile.py").read_text(encoding="utf-8")
        electron = (ROOT / "electron" / "main.ts").read_text(encoding="utf-8")
        self.assertNotIn('service-connections/claude-code/login', api)
        self.assertIn("event.sender !== mainWindow.webContents", electron)
        self.assertIn("synapse:claude-auth-login", electron)
        self.assertIn("auth login", electron)

    def test_ui_exposes_connect_and_verify_actions(self):
        page = (ROOT / "renderer" / "components" / "AccountAppsCatalog.tsx").read_text(encoding="utf-8")
        bridge = (ROOT / "renderer" / "lib" / "electron-bridge.ts").read_text(encoding="utf-8")
        self.assertIn("Connect Claude", page)
        self.assertIn("Verify connection", page)
        self.assertIn("claudeAuthLogin", bridge)

if __name__ == "__main__":
    unittest.main()
