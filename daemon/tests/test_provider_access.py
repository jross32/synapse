from dataclasses import replace
from pathlib import Path
import json
import pytest
from synapse_daemon.provider_access import ProviderAccess, choose, eligible, inventory, read_policy, write_policy


def test_unverified_free_account_is_not_automatically_usable():
    account = ProviderAccess(access="free", authenticated=True, included_usage_available=True)
    assert not eligible("grok", account, installed=True)
    assert eligible("grok", replace(account, supports_automation=True), installed=True)


def test_subscription_requires_supported_automation_and_available_included_usage():
    a = ProviderAccess(access="subscription", authenticated=True, supports_automation=True,
                       included_usage_available=True)
    assert eligible("codex", a, installed=True)
    assert not eligible("codex", replace(a, included_usage_available=False), installed=True)


def test_no_unapproved_spending_even_with_api_key():
    api = ProviderAccess(access="api", authenticated=True, supports_automation=True,
                         included_usage_available=False, extra_cost_per_request_usd=0.01)
    assert choose({"grok": True}, {"grok": api}) is None
    assert choose({"grok": True}, {"grok": api}, allow_additional_spend=True) == "grok"
    assert not eligible("grok", replace(api, extra_cost_per_request_usd=None),
                        installed=True, allow_additional_spend=True)


def test_chatgpt_first_and_local_last_when_eligible():
    local = ProviderAccess(access="local", supports_automation=True)
    cli = ProviderAccess(access="free", authenticated=True, supports_automation=True,
                         included_usage_available=True)
    available = {"chatgpt_web": True, "codex": True, "local": True}
    access = {"chatgpt_web": cli, "codex": cli, "local": local}
    assert choose(available, access) == "chatgpt_web"
    assert choose({**available, "chatgpt_web": False}, access) == "codex"
    assert choose({"local": True}, access) == "local"


def test_policy_roundtrip_is_nonsecret_and_default_deny(tmp_path):
    path = tmp_path / "provider-access.json"
    assert read_policy(path)["allow_additional_spend"] is False
    policy = {"allow_additional_spend": False, "providers": {"gemini": ProviderAccess(access="free")}}
    write_policy(path, policy)
    result = read_policy(path)
    assert result["providers"]["gemini"].access == "free"
    assert "api_key" not in path.read_text()
    path.write_text(json.dumps({"allow_additional_spend": True, "providers": {"grok": {"access": "unknown"}}}))
    assert read_policy(path)["allow_additional_spend"] is True


def test_inventory_does_not_claim_unverified_entitlements():
    items = inventory({}, {"codex": True})
    codex = next(i for i in items if i["id"] == "codex")
    assert codex["installed"] is True
    assert codex["eligible_without_extra_spend"] is False
    assert codex["access"]["access"] == "unknown"
