"""Merge portable account state without losing devices from another signed-in host.

The identity server, not each laptop, owns the union. Only portable profile metadata
is accepted here; tokens, project source, credentials and machine control never sync.
"""
from __future__ import annotations

from typing import Any

_COLLECTION_KEYS = {
    "hosts": "id",
    "catalog_preferences": "item_key",
    "service_connections": "id",
}


def merge_documents(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        raise ValueError("Portable sync documents must be JSON objects.")
    result: dict[str, Any] = {"schema": 2}
    old_prefs = existing.get("preferences")
    new_prefs = incoming.get("preferences")
    if isinstance(old_prefs, dict) and isinstance(new_prefs, dict):
        result["preferences"] = (new_prefs if str(new_prefs.get("updated_at") or "") >=
                                 str(old_prefs.get("updated_at") or "") else old_prefs)
    else:
        result["preferences"] = new_prefs if isinstance(new_prefs, dict) else (
            old_prefs if isinstance(old_prefs, dict) else {}
        )

    for collection, field in _COLLECTION_KEYS.items():
        merged: dict[str, dict[str, Any]] = {}
        for source in (existing, incoming):
            values = source.get(collection, [])
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, dict):
                    continue
                key = value.get(field)
                if not isinstance(key, str) or not key or len(key) > 256:
                    continue
                # Do not allow portable metadata to masquerade as local authentication.
                clean = dict(value)
                if collection == "hosts":
                    clean["current_host"] = False
                previous = merged.get(key)
                if previous is None or str(clean.get("updated_at") or "") >= str(previous.get("updated_at") or ""):
                    merged[key] = clean
        result[collection] = list(merged.values())
    # Deliberately exclude unknown fields. Clients must never use this account
    # document to exchange passwords, access tokens, cookies or MCP write grants.
    return result
