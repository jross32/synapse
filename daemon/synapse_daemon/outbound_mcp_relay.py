"""Background Synapse host agent for the account-wide MCP URL.

A signed-in Synapse daemon authenticates *outbound* to the shared accounts
service and dispatches only tasks routed to its own enrolled machine ID.
The cloud never learns this daemon's local MCP token.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .profile import ProfileManager
from .secrets import encrypt, decrypt

log = logging.getLogger(__name__)
_CREDENTIAL_FILE = "relay-device-credential.json"


class OutboundMcpRelay:
    def __init__(self, manager: ProfileManager, local_token: str, *, local_port: int = 7878) -> None:
        self.manager = manager
        self.local_token = local_token
        self.local_port = local_port
        self.data_dir = Path(manager._storage.data_dir)
        self._stopping = False

    def _identity(self) -> tuple[str, str] | None:
        row = self.manager._state_row()
        account_id = row["user_id"]
        device_id = row["current_host_id"]
        if not account_id or not device_id:
            return None
        return str(account_id), str(device_id)

    def _read_saved_credential(self, account_id: str, device_id: str) -> str | None:
        path = self.data_dir / _CREDENTIAL_FILE
        if not path.exists():
            return None
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("account_id") != account_id or doc.get("device_id") != device_id:
                return None
            ciphertext = base64.b64decode(doc["encrypted_token"], validate=True)
            return decrypt(ciphertext, data_dir=self.data_dir)
        except (ValueError, KeyError, OSError, TypeError):
            log.warning("Stored relay device credential is unreadable; remote MCP agent paused.")
            return None

    def _save_credential(self, account_id: str, device_id: str, token: str) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        raw = {
            "account_id": account_id,
            "device_id": device_id,
            "encrypted_token": base64.b64encode(encrypt(token, data_dir=self.data_dir)).decode("ascii"),
        }
        # Atomic replacement; never write a plaintext credential to disk.
        target = self.data_dir / _CREDENTIAL_FILE
        fd, temporary = tempfile.mkstemp(prefix="relay-device-", suffix=".tmp", dir=self.data_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(raw, out)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _enroll_once(self, account_id: str, device_id: str) -> str:
        # The account's host inventory must contain this device before cloud
        # registration; this call synchronizes its durable ID first.
        self.manager.list_hosts()
        access = self.manager._ensure_access_token()
        result = self.manager._accounts.enroll_relay_device(access_token=access, device_id=device_id)
        credential = result.get("device_token")
        if not isinstance(credential, str) or len(credential) < 32:
            raise RuntimeError("Relay device enrollment returned an invalid credential.")
        self._save_credential(account_id, device_id, credential)
        log.info("Synapse device enrolled for account-wide MCP relay (device ID %s).", device_id)
        return credential

    def _invoke_local_mcp(self, request: Any, mode: str) -> Any:
        # The per-device cloud policy is applied to every job. Read-only jobs
        # are pinned to the daemon's read-only MCP dispatcher.
        suffix = "?mode=read" if mode == "read" else ""
        url = f"http://127.0.0.1:{self.local_port}/mcp/{self.local_token}{suffix}"
        body = json.dumps(request).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=51) as response:
                if response.status == 202:
                    return None
                data = response.read(2_000_001)
                if len(data) > 2_000_000:
                    raise RuntimeError("Local MCP reply exceeds relay size limit.")
                return json.loads(data)
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
            return {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
                    "error": {"code": -32000, "message": "Synapse local MCP dispatch failed."}}

    def _run_one_cycle(self) -> None:
        identity = self._identity()
        if identity is None:
            return
        account_id, device_id = identity
        credential = self._read_saved_credential(account_id, device_id)
        if credential is None:
            # Missing credentials are created on first account login, not by
            # a remote unauthenticated request. A previously revoked credential
            # remains on disk and will NOT silently re-enroll after 401.
            credential = self._enroll_once(account_id, device_id)
        job = self.manager._accounts.relay_agent_poll(device_id=device_id, device_token=credential)
        if not job.get("job_id"):
            return
        # Check sign-out / account-switch immediately before dispatch.
        if self._identity() != identity:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32001, "message": "Synapse account session changed."}}
        else:
            # Fail closed on a cloud control-plane outage. Check again directly
            # before invoking local commands to honor recently disabled writes.
            access = self.manager._accounts.relay_agent_access(device_id=device_id, device_token=credential)
            effective_mode = "read" if not access.get("remote_write_enabled") else job.get("mode", "read")
            if self._identity() != identity:
                response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32001,
                            "message": "Synapse account session changed before dispatch."}}
            else:
                response = self._invoke_local_mcp(job.get("request"), effective_mode)
        self.manager._accounts.relay_agent_finish(
            device_id=device_id, device_token=credential, job_id=str(job["job_id"]), response=response)

    async def run(self) -> None:
        log.info("Outbound Synapse MCP relay agent ready; waiting for account sign-in.")
        while not self._stopping:
            try:
                await asyncio.to_thread(self._run_one_cycle)
                # Keep CPU usage low; cloud polling holds the request for ~16s.
                await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # NEVER include bearer tokens or request bodies in logs.
                log.warning("Outbound MCP relay unavailable (%s); will retry.", type(exc).__name__)
                await asyncio.sleep(10)

    def stop(self) -> None:
        self._stopping = True
