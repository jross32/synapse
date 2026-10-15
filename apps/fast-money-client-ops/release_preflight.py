"""Fail-closed release readiness checks. Does not print secrets."""
import json
import os
from pathlib import Path

def assess(config, env=None):
    env = os.environ if env is None else env
    auth = config.get("auth") or {}
    billing = config.get("billing") or {}
    checks = [
        ("production_identity", auth.get("provider") not in (None, "", "local-placeholder")),
        ("https_secure_sessions", config.get("https_secure_sessions") is True),
        ("stripe_test_checkout", env.get("STRIPE_SECRET_KEY", "").startswith("sk_test_") and env.get("STRIPE_WEBHOOK_SECRET", "").startswith("whsec_")),
        ("stripe_live_billing", billing.get("provider") == "stripe" and env.get("STRIPE_SECRET_KEY", "").startswith("sk_live_") and env.get("STRIPE_WEBHOOK_SECRET", "").startswith("whsec_")),
        ("outbound_approval", config.get("verified_outbound_approval") is True),
        ("deployment_rollback", config.get("verified_deployment_rollback") is True),
    ]
    return {"ready_for_external_release": all(ok for _, ok in checks),
            "checks": [{"id": key, "passed": bool(ok)} for key, ok in checks]}

def main():
    config = json.loads((Path(__file__).parent / "fast_money.config.json").read_text(encoding="utf-8"))
    result = assess(config)
    print(json.dumps(result, indent=2))
    return 0 if result["ready_for_external_release"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
