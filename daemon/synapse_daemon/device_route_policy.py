"""Account-scoped, fail-closed target planning for Synapse multi-device jobs.

This module makes *decisions*, not remote calls. Only the authenticated cloud
relay may execute an approved plan; a hostname is never an authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Literal


class DeviceRouteError(ValueError):
    """An account/device mismatch or unavailable execution target."""


@dataclass(frozen=True)
class DeviceTarget:
    device_id: str
    account_id: str
    display_name: str
    last_heartbeat: datetime | None
    relay_connected: bool
    enabled: bool
    capabilities: frozenset[str]
    revoked: bool = False
    priority: int = 0


@dataclass(frozen=True)
class RoutePlan:
    account_id: str
    selector: str
    device_ids: tuple[str, ...]
    required_capabilities: frozenset[str]
    operation: str


def _alive(device: DeviceTarget, now: datetime, max_age_seconds: int) -> bool:
    seen = device.last_heartbeat
    if seen is None or seen.tzinfo is None:
        return False
    age = (now - seen.astimezone(timezone.utc)).total_seconds()
    return 0 <= age <= max_age_seconds


def plan_devices(
    *,
    account_id: str,
    selector: str,
    devices: Iterable[DeviceTarget],
    operation: str,
    required_capabilities: Iterable[str] = (),
    now: datetime | None = None,
    max_age_seconds: int = 90,
    allow_multiple: bool = False,
    approved_device_ids: Iterable[str] | None = None,
    preferred_capabilities: Iterable[str] = (),
    preferred_device_ids: Iterable[str] = (),
) -> RoutePlan:
    """Resolve explicit ID, 'auto' or 'both' using verified device IDs.

    No cross-account device may be selected; a missing or stale relay is
    never interpreted as an invitation to fall back to a different host.
    Hostname aliases are deliberately unsupported because they can collide.
    'both' requires an explicit multi-target opt-in and approval set.
    """
    if not account_id or not operation or max_age_seconds <= 0:
        raise DeviceRouteError("Account, operation and positive heartbeat limit required")
    if not selector:
        raise DeviceRouteError("An explicit target, 'auto', or 'both' is required")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise DeviceRouteError("Current time must have timezone")
    required = frozenset(required_capabilities)
    entries = tuple(devices)
    ids = [x.device_id for x in entries]
    if not all(ids) or len(ids) != len(set(ids)):
        raise DeviceRouteError("Missing or duplicated stable device IDs")
    available = {
        d.device_id: d for d in entries
        if d.account_id == account_id and d.enabled and not d.revoked
        and d.relay_connected and required.issubset(d.capabilities)
        and _alive(d, now, max_age_seconds)
    }
    if selector == "both":
        if not allow_multiple or approved_device_ids is None:
            raise DeviceRouteError("Multi-device execution requires approved device IDs")
        approved_targets = frozenset(approved_device_ids)
        if len(approved_targets) != 2 or not approved_targets.issubset(available):
            raise DeviceRouteError("Approve exactly two reachable devices")
        chosen = tuple(sorted(approved_targets))
    elif selector == "auto":
        if not available:
            raise DeviceRouteError("No eligible online device for this account")
        # Auto selection favors relevant tools and a project?s known machine before
        # general priority. Preferences never bypass the hard eligibility gates.
        preferred = frozenset(preferred_capabilities)
        affinity = tuple(preferred_device_ids)
        if len(affinity) != len(set(affinity)):
            raise DeviceRouteError("Duplicate preferred device identity")
        affinity_rank = {value: index for index, value in enumerate(affinity)}
        best = min(available.values(), key=lambda d: (
            -len(preferred.intersection(d.capabilities)),
            affinity_rank.get(d.device_id, len(affinity)),
            -d.priority, d.device_id))
        chosen = (best.device_id,)
    else:
        if selector not in available:
            raise DeviceRouteError("Requested device unavailable or unauthorized")
        chosen = (selector,)
    if approved_device_ids is not None:
        approved = frozenset(approved_device_ids)
        if not set(chosen).issubset(approved):
            raise DeviceRouteError("Operation not approved for every selected device")
    return RoutePlan(account_id, selector, chosen, required, operation)



def verify_execution_target(expected_device_id: str, reported_device_id: str,
                            *, account_id: str, reported_account_id: str) -> None:
    """Fail closed if a routed execution acknowledgement comes from another device.

    Caller must obtain the reported identity from an authenticated device-bound
    relay receipt, not from a hostname or arbitrary client-provided string.
    """
    if not expected_device_id or not reported_device_id or not account_id:
        raise DeviceRouteError("Missing execution identity")
    if reported_account_id != account_id or reported_device_id != expected_device_id:
        raise DeviceRouteError("Execution target mismatch; refusing wrong-machine operation")
