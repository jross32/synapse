"""Account-level MCP tools for the unified Synapse connector.

The cloud only manages account device selection; execution stays on the
authorized local device through the existing outbound relay.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import RelayConnector, RelayDevice
from .device_access import _hosts, check_device_write
from .relay import select_connector_device

ACCOUNT_MCP_TOOLS = [
    {
        "name": "synapse_account_list_devices",
        "description": "List this Synapse account's linked computers with relay availability, selected host and write permissions.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "idempotentHint": True},
    },
    {
        "name": "synapse_account_call_device",
        "description": (
            "Run a named Synapse MCP tool on one explicitly selected online device "
            "owned by this account, without changing the connector's default device. "
            "Provide device_id, tool, and arguments. Device write permissions still apply."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "tool": {"type": "string"},
                "arguments": {"type": "object"},
            },
            "required": ["device_id", "tool"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
    },
    {
        "name": "synapse_account_select_device",
        "description": "Select one online account-owned Synapse computer for future calls through this same MCP connection. Requires the stable device_id, not a hostname.",
        "inputSchema": {
            "type": "object",
            "properties": {"device_id": {"type": "string"}},
            "required": ["device_id"], "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
    },
]


def account_device_inventory(db: Session, account_id: str) -> dict:
    linked = _hosts(db, account_id)
    connector = db.scalar(select(RelayConnector).where(RelayConnector.account_id == account_id))
    enrolled = {r.device_id: r for r in db.scalars(
        select(RelayDevice).where(RelayDevice.account_id == account_id))}
    now = datetime.now(UTC)
    devices = []
    for device_id in sorted(linked):
        row = enrolled.get(device_id)
        active = row is not None and row.revoked_at is None
        seen = row.last_seen_at if row else None
        if seen is not None and seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)
        online = bool(active and seen is not None and timedelta(0) <= now - seen <= timedelta(seconds=120))
        devices.append({
            "device_id": device_id,
            "enrolled": bool(active),
            "online": online,
            "last_seen_at": seen.isoformat() if seen else None,
            "remote_write_enabled": bool(active and check_device_write(db, account_id, device_id)),
            "selected": bool(connector and connector.selected_device_id == device_id),
        })
    return {"devices": devices, "selected_device_id": connector.selected_device_id if connector else None}


def execute_account_tool(db: Session, account_id: str, name: str, arguments: dict, *, read_only: bool) -> dict:
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=400, detail="Tool arguments must be an object.")
    if name == "synapse_account_list_devices":
        if arguments:
            raise HTTPException(status_code=400, detail="Unexpected arguments.")
        return account_device_inventory(db, account_id)
    if name != "synapse_account_select_device":
        raise HTTPException(status_code=404, detail="Unknown account tool.")
    if read_only:
        raise HTTPException(status_code=403, detail="Cannot change selected device through a read-only connection.")
    device_id = arguments.get("device_id")
    if not isinstance(device_id, str) or not device_id or set(arguments) != {"device_id"}:
        raise HTTPException(status_code=422, detail="A stable device_id is required.")
    available = {x["device_id"]: x for x in account_device_inventory(db, account_id)["devices"]}
    if device_id not in available or not available[device_id]["enrolled"]:
        raise HTTPException(status_code=404, detail="Device not enrolled under this account.")
    if not available[device_id]["online"]:
        raise HTTPException(status_code=503, detail="Device relay has not recently checked in.")
    return select_connector_device(db, account_id, device_id)


def rpc_tool_success(request_id: object, value: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id,
            "result": {"content": [{"type": "text", "text": json.dumps(value, sort_keys=True)}]}}


_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_-]{2,100}$")


def plan_explicit_device_call(db: Session, account_id: str, args: dict) -> tuple[str, str, dict]:
    """Fail closed before enqueueing any remote work."""
    if not isinstance(args, dict) or set(args) - {"device_id", "tool", "arguments"}:
        raise HTTPException(status_code=422, detail="Invalid device dispatch arguments.")
    device_id = args.get("device_id")
    tool = args.get("tool")
    arguments = args.get("arguments", {})
    if not isinstance(device_id, str) or not device_id:
        raise HTTPException(status_code=422, detail="A stable device_id is required.")
    if not isinstance(tool, str) or _TOOL_NAME.fullmatch(tool) is None:
        raise HTTPException(status_code=422, detail="Invalid Synapse tool name.")
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=422, detail="Tool arguments must be an object.")
    if tool.startswith("synapse_account_"):
        raise HTTPException(status_code=422, detail="Nested account control operations are unsupported.")
    devices = {x["device_id"]: x for x in account_device_inventory(db, account_id)["devices"]}
    device = devices.get(device_id)
    if device is None or not device["enrolled"]:
        raise HTTPException(status_code=404, detail="Device not enrolled under this account.")
    if not device["online"]:
        raise HTTPException(status_code=503, detail="Device relay has not recently checked in.")
    return device_id, tool, arguments
