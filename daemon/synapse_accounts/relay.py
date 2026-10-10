"""Account-owned MCP relay: queue requests for authenticated local Synapse agents.

One stable public MCP URL per account, with outbound device polling. No cloud
handler may execute commands; it only routes JSON-RPC to an explicitly enrolled
daemon. Distinct hashed credentials for external MCP consumers and each device.
"""
from __future__ import annotations

import asyncio
import json
import os
import hmac
import hashlib
import base64
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session, sessionmaker

from .db import (
    Account, RelayConnector, RelayDevice, RelayJob, SyncDocument, session_scope,
)
from .device_access import _hosts, check_device_write


def token_hash(token: str) -> str:
    from hashlib import sha256
    return sha256(token.encode("utf-8")).hexdigest()


def _connector_token(account_id: str, nonce: str) -> str:
    secret = os.getenv("SYNAPSE_RELAY_SIGNING_KEY", "")
    if len(secret) < 48:
        raise HTTPException(status_code=503, detail="Synapse account relay is not configured.")
    digest = hmac.new(secret.encode("utf-8"), f"synapse-relay-v1:{account_id}:{nonce}".encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def issue_connector(db: Session, account: Account, public_base_url: str, *, rotate: bool = False) -> dict[str, str]:
    connector = db.scalar(select(RelayConnector).where(RelayConnector.account_id == account.id))
    if connector is None:
        connector = RelayConnector(account_id=account.id, nonce=secrets.token_hex(24), token_hash="")
        db.add(connector)
    elif rotate:
        connector.nonce = secrets.token_hex(24)
    token = _connector_token(account.id, connector.nonce)
    connector.token_hash = token_hash(token)
    connector.updated_at = datetime.now(UTC)
    db.flush()
    return {"url": f"{public_base_url.rstrip('/')}/mcp/{token}", "rotated": rotate,
            "selected_device_id": connector.selected_device_id,
            "note": "This shared MCP URL stays the same across your computers. Rotate to revoke old connector access."}

def select_connector_device(db: Session, account_id: str, device_id: str) -> dict[str, str]:
    if device_id not in _hosts(db, account_id):
        raise HTTPException(status_code=404, detail="This device is not linked to your Synapse account.")
    connector = db.scalar(select(RelayConnector).where(RelayConnector.account_id == account_id))
    if connector is None:
        raise HTTPException(status_code=404, detail="Create your unified MCP connector first.")
    connector.selected_device_id = device_id
    db.flush()
    return {"selected_device_id": device_id}

def require_connector_account(db: Session, token: str) -> Account:
    if len(token) < 32 or len(token) > 256:
        raise HTTPException(status_code=401, detail="Invalid connector credential.")
    connector = db.scalar(select(RelayConnector).where(RelayConnector.token_hash == token_hash(token)))
    if connector is None:
        raise HTTPException(status_code=401, detail="Connector credential has expired or been revoked.")
    account = db.scalar(select(Account).where(Account.id == connector.account_id))
    if account is None:
        raise HTTPException(status_code=401, detail="Account not found.")
    return account


def enroll_device(db: Session, account: Account, device_id: str) -> dict[str, str]:
    if device_id not in _hosts(db, account.id):
        raise HTTPException(status_code=404, detail="This computer is not registered with your account.")
    raw = secrets.token_urlsafe(48)
    device = db.scalar(select(RelayDevice).where(
        RelayDevice.account_id == account.id, RelayDevice.device_id == device_id))
    if device is None:
        device = RelayDevice(account_id=account.id, device_id=device_id, token_hash=token_hash(raw))
        db.add(device)
    else:
        device.token_hash = token_hash(raw)
        device.updated_at = datetime.now(UTC)
        device.revoked_at = None
    db.flush()
    return {"device_id": device_id, "device_token": raw}


def verify_device(db: Session, device_id: str, credential: str) -> RelayDevice:
    if len(credential) < 32 or len(credential) > 256:
        raise HTTPException(status_code=401, detail="Invalid device credential.")
    device = db.scalar(select(RelayDevice).where(
        RelayDevice.device_id == device_id,
        RelayDevice.token_hash == token_hash(credential),
        RelayDevice.revoked_at.is_(None)))
    if device is None:
        raise HTTPException(status_code=401, detail="Device is not enrolled.")
    return device


def choose_device(db: Session, account_id: str, preferred: str | None) -> str:
    known = _hosts(db, account_id)
    if not known:
        raise HTTPException(status_code=503, detail="No devices are linked to this account.")
    if preferred:
        if preferred not in known:
            raise HTTPException(status_code=404, detail="Unknown device for this Synapse account.")
        enrolled = db.scalar(select(RelayDevice).where(
            RelayDevice.account_id == account_id,
            RelayDevice.device_id == preferred,
            RelayDevice.revoked_at.is_(None)))
        if enrolled is None:
            raise HTTPException(status_code=503, detail="Selected Synapse computer is not connected yet.")
        return preferred
    # Prefer the most recent device heartbeat, otherwise stable alphabetical order.
    devices = list(db.scalars(select(RelayDevice).where(
        RelayDevice.account_id == account_id, RelayDevice.revoked_at.is_(None))))
    active = [device for device in devices if device.device_id in known]
    if not active:
        raise HTTPException(status_code=503, detail="No MCP devices enrolled yet.")
    return sorted(active, key=lambda device: (device.last_seen_at or datetime.min, device.device_id), reverse=True)[0].device_id


def create_job(db: Session, account_id: str, device_id: str, payload: Any, *, mode: str) -> str:
    if device_id not in _hosts(db, account_id):
        raise HTTPException(status_code=404, detail="Device not in account.")
    if not isinstance(payload, (list, dict)):
        raise HTTPException(status_code=400, detail="JSON-RPC must be an object or batch.")
    raw = json.dumps(payload)
    if len(raw) > 131072:
        raise HTTPException(status_code=413, detail="MCP request too large.")
    now = datetime.now(UTC)
    db.execute(delete(RelayJob).where(RelayJob.account_id == account_id,
                                     RelayJob.expires_at < now - timedelta(hours=1)))
    outstanding = db.scalar(select(func.count(RelayJob.id)).where(
        RelayJob.account_id == account_id, RelayJob.status.in_(("pending", "claimed")),
        RelayJob.expires_at > now))
    if outstanding is not None and outstanding >= 24:
        raise HTTPException(status_code=429, detail="Too many pending Synapse requests.")
    job = RelayJob(account_id=account_id, device_id=device_id, request_json=raw,
                   mode="read" if mode == "read" or not check_device_write(db, account_id, device_id) else "full",
                   status="pending", expires_at=now + timedelta(seconds=65))
    db.add(job)
    db.flush()
    return job.id


def claim_job(db: Session, device: RelayDevice) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    # SQLite is single-instance on the Railway persistent volume. Reverify
    # the current device policy at dispatch time so revocation is effective.
    job = db.scalar(select(RelayJob).where(
        RelayJob.account_id == device.account_id, RelayJob.device_id == device.device_id,
        RelayJob.status == "pending", RelayJob.expires_at > now).order_by(RelayJob.created_at).limit(1))
    device.last_seen_at = now
    if job is None:
        return None
    job.status = "claimed"
    job.claimed_at = now
    if not check_device_write(db, device.account_id, device.device_id):
        job.mode = "read"
    db.flush()
    return {"job_id": job.id, "request": json.loads(job.request_json), "mode": job.mode}


def submit_result(db: Session, device: RelayDevice, job_id: str, response: Any) -> None:
    job = db.scalar(select(RelayJob).where(
        RelayJob.id == job_id, RelayJob.account_id == device.account_id,
        RelayJob.device_id == device.device_id))
    if job is None or job.status != "claimed":
        raise HTTPException(status_code=404, detail="Pending request not found.")
    raw = json.dumps(response)
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=413, detail="MCP response too large.")
    job.response_json = raw
    job.status = "complete"
    job.completed_at = datetime.now(UTC)


async def await_result(factory: sessionmaker[Session], account_id: str, job_id: str) -> Any:
    for _ in range(110):  # 55 seconds, never busy-wait a DB session
        with session_scope(factory) as db:
            job = db.scalar(select(RelayJob).where(
                RelayJob.id == job_id, RelayJob.account_id == account_id))
            if job and job.status == "complete":
                result = json.loads(job.response_json or "null")
                db.delete(job)  # minimize cloud retention of tool inputs/results
                return result
        await asyncio.sleep(0.5)
    raise HTTPException(status_code=504, detail="Synapse device did not respond within 55 seconds.")
