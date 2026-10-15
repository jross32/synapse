"""Account-scoped per-device MCP access policies.

Full access is an enrolled-host policy, never a public Internet permission.
An absent device is denied even though newly enrolled devices default on.
"""
from __future__ import annotations

import json
from datetime import datetime, UTC
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import DeviceAccessPolicy, SyncDocument


def _hosts(db: Session, account_id: str) -> set[str]:
    row = db.scalar(select(SyncDocument).where(SyncDocument.account_id == account_id))
    if row is None:
        return set()
    document: Any = json.loads(row.document_json or "{}")
    hosts = document.get("hosts") if isinstance(document, dict) else []
    return {host["id"] for host in hosts if isinstance(host, dict) and isinstance(host.get("id"), str)
            and host["id"] and len(host["id"]) <= 128} if isinstance(hosts, list) else set()


def list_device_access(db: Session, account_id: str) -> list[dict[str, Any]]:
    enrolled = _hosts(db, account_id)
    stored = {row.device_id: row for row in db.scalars(
        select(DeviceAccessPolicy).where(DeviceAccessPolicy.account_id == account_id))}
    return [{"device_id": device_id,
             "remote_write_enabled": stored[device_id].remote_write_enabled if device_id in stored else True,
             "enrolled": True}
            for device_id in sorted(enrolled)]


def change_device_access(db: Session, account_id: str, device_id: str, enabled: bool) -> dict[str, Any]:
    if device_id not in _hosts(db, account_id):
        raise HTTPException(status_code=404, detail="Device is not enrolled in this account.")
    policy = db.scalar(select(DeviceAccessPolicy).where(
        DeviceAccessPolicy.account_id == account_id, DeviceAccessPolicy.device_id == device_id))
    if policy is None:
        policy = DeviceAccessPolicy(account_id=account_id, device_id=device_id,
                                    remote_write_enabled=enabled)
        db.add(policy)
    else:
        policy.remote_write_enabled = enabled
        policy.updated_at = datetime.now(UTC)
    db.flush()
    return {"device_id": device_id, "remote_write_enabled": enabled, "enrolled": True}


def check_device_write(db: Session, account_id: str, device_id: str) -> bool:
    if device_id not in _hosts(db, account_id):
        return False
    policy = db.scalar(select(DeviceAccessPolicy).where(
        DeviceAccessPolicy.account_id == account_id, DeviceAccessPolicy.device_id == device_id))
    return bool(policy.remote_write_enabled) if policy is not None else True
