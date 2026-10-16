"""Strict account-relay single-device selection gateway.

Uses existing select_mcp_device(account access token). Current cloud connector
supports one selected device. This code does not transfer daemon tokens.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Protocol
from .device_route_policy import DeviceRouteError, DeviceTarget, RoutePlan, plan_devices


class AccountRelayClient(Protocol):
    def select_mcp_device(self, *, access_token: str, device_id: str) -> dict: ...


@dataclass(frozen=True)
class AccountDeviceSelection:
    plan: RoutePlan
    device_id: str


def select_account_device(
    *, client: AccountRelayClient, account_id: str, account_access_token: str,
    selector: str, devices: Iterable[DeviceTarget], operation: str,
    required_capabilities: Iterable[str] = (),
    approved_device_ids: Iterable[str] | None = None,
    preferred_capabilities: Iterable[str] = (),
    preferred_device_ids: Iterable[str] = (),
    now: datetime | None = None,
) -> AccountDeviceSelection:
    """Authorize an exact account-owned, reachable host and confirm selection."""
    if not account_access_token:
        raise DeviceRouteError("An authenticated Synapse account is required")
    plan = plan_devices(
        account_id=account_id, selector=selector, devices=devices,
        operation=operation, required_capabilities=required_capabilities,
        approved_device_ids=approved_device_ids,
        preferred_capabilities=preferred_capabilities, preferred_device_ids=preferred_device_ids, now=now,
    )
    if len(plan.device_ids) != 1:
        raise DeviceRouteError("The current account MCP relay supports only one selected device")
    target = plan.device_ids[0]
    response = client.select_mcp_device(access_token=account_access_token, device_id=target)
    if not isinstance(response, dict) or response.get("selected_device_id") != target:
        raise DeviceRouteError("Synapse account relay did not confirm the requested device")
    return AccountDeviceSelection(plan=plan, device_id=target)
