"""User-owned provider entitlements and safe, zero-unapproved-spend routing.

Availability is evidence-based: installed binary != authenticated or permitted use.
Never store credentials here; API credentials belong in the existing secret vault.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import os
import tempfile

PROVIDERS = {
    "chatgpt_web": ("ChatGPT UI", "browser", ("coding", "reasoning")),
    "codex": ("Codex", "cli", ("coding", "reasoning")),
    "claude": ("Claude Code", "cli", ("coding", "reasoning")),
    "copilot": ("GitHub Copilot", "cli", ("coding",)),
    "gemini": ("Gemini CLI", "cli", ("coding", "reasoning")),
    "local": ("Ollama", "local", ("coding", "reasoning")),
    "grok": ("Grok (xAI)", "api", ("reasoning", "coding")),
    "groq": ("Groq", "api", ("reasoning", "coding")),
    "openrouter": ("OpenRouter", "api", ("reasoning", "coding")),
    "deepseek": ("DeepSeek", "api", ("reasoning", "coding")),
    "mistral": ("Mistral", "api", ("reasoning", "coding")),
    "together": ("Together AI", "api", ("reasoning", "coding")),
    "lm_studio": ("LM Studio", "local", ("reasoning", "coding")),
}

ORDER = ("chatgpt_web", "codex", "claude", "copilot", "gemini", "grok", "groq", "openrouter", "deepseek", "mistral", "together", "lm_studio", "local")

@dataclass(frozen=True)
class ProviderAccess:
    enabled: bool = True
    access: str = "unknown"  # unknown, free, subscription, api, local
    authenticated: bool = False
    supports_automation: bool = False
    included_usage_available: bool = False
    extra_cost_per_request_usd: float | None = None

    @classmethod
    def parse(cls, value: dict) -> "ProviderAccess":
        allowed = {key: value[key] for key in cls.__dataclass_fields__ if key in value}
        obj = cls(**allowed)
        if obj.access not in {"unknown", "free", "subscription", "api", "local"}:
            raise ValueError("invalid provider access type")
        if obj.extra_cost_per_request_usd is not None and obj.extra_cost_per_request_usd < 0:
            raise ValueError("negative provider cost")
        return obj


def read_policy(path: Path) -> dict:
    if not path.exists():
        return {"allow_additional_spend": False, "providers": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("providers", {}), dict):
        raise ValueError("invalid provider policy")
    return {"allow_additional_spend": data.get("allow_additional_spend") is True,
            "providers": {name: ProviderAccess.parse(value) for name, value in data.get("providers", {}).items() if name in PROVIDERS}}


def write_policy(path: Path, policy: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    providers = {name: asdict(value) for name, value in policy.get("providers", {}).items() if name in PROVIDERS}
    payload = {"allow_additional_spend": policy.get("allow_additional_spend") is True, "providers": providers}
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix="provider-access-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def eligible(name: str, access: ProviderAccess, *, allow_additional_spend: bool = False,
             installed: bool = False, capacity: bool = True, capability: str = "coding") -> bool:
    if name not in PROVIDERS or capability not in PROVIDERS[name][2]:
        return False
    if not (access.enabled and access.supports_automation and installed and capacity):
        return False
    if access.access != "local" and not access.authenticated:
        return False
    if access.included_usage_available or access.access == "local":
        return True
    # Unknown costs are never assumed free. Even opt-in paid use requires a known estimate.
    return bool(allow_additional_spend and access.extra_cost_per_request_usd is not None)


def choose(availability: dict[str, bool], access: dict[str, ProviderAccess], *,
           allow_additional_spend: bool = False, preferred: tuple[str, ...] = ORDER,
           capability: str = "coding") -> str | None:
    ordered = tuple(dict.fromkeys((*preferred, *ORDER)))
    return next((name for name in ordered if eligible(name, access.get(name, ProviderAccess()),
                 allow_additional_spend=allow_additional_spend,
                 installed=availability.get(name, False), capability=capability)), None)


def inventory(access: dict[str, ProviderAccess], availability: dict[str, bool]) -> list[dict]:
    return [{"id": name, "label": details[0], "method": details[1], "capabilities": list(details[2]),
             "installed": availability.get(name, False),
             "access": asdict(access.get(name, ProviderAccess())),
             "eligible_without_extra_spend": eligible(name, access.get(name, ProviderAccess()),
                 installed=availability.get(name, False))} for name, details in PROVIDERS.items()]
