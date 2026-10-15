import unittest
from release_preflight import assess

class ReleasePreflightTests(unittest.TestCase):
    def test_demo_configuration_blocks_external_release(self):
        report = assess({"auth": {"provider": "local-placeholder"},
                         "billing": {"provider": "stripe-placeholder"}}, {})
        self.assertFalse(report["ready_for_external_release"])
        self.assertEqual(len(report["checks"]), 6)
        self.assertFalse(any(c["passed"] for c in report["checks"]))

    def test_test_keys_do_not_count_as_live_payments(self):
        report = assess({"auth": {"provider": "verified-oidc"},
                         "billing": {"provider": "stripe"},
                         "https_secure_sessions": True,
                         "verified_outbound_approval": True,
                         "verified_deployment_rollback": True},
                        {"STRIPE_SECRET_KEY": "sk_test_example",
                         "STRIPE_WEBHOOK_SECRET": "whsec_example"})
        checks = {item["id"]: item["passed"] for item in report["checks"]}
        self.assertTrue(checks["stripe_test_checkout"])
        self.assertFalse(checks["stripe_live_billing"])
        self.assertFalse(report["ready_for_external_release"])

    def test_missing_webhook_blocks_even_with_live_key(self):
        report = assess({"auth": {"provider": "verified-oidc"},
                         "billing": {"provider": "stripe"}}, {"STRIPE_SECRET_KEY": "sk_live_example"})
        self.assertFalse(report["ready_for_external_release"])
        self.assertFalse(next(x["passed"] for x in report["checks"] if x["id"] == "stripe_live_billing"))

if __name__ == "__main__":
    unittest.main()
