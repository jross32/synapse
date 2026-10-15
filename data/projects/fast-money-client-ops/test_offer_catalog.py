import unittest
from decimal import Decimal
from offer_catalog import STARTER, get_offer, validate_catalog


class OfferCatalogTests(unittest.TestCase):
    def test_catalog_validation(self):
        validate_catalog()

    def test_fixed_price_and_deposit(self):
        self.assertEqual(STARTER.setup_usd, Decimal("1500.00"))
        self.assertEqual(STARTER.deposit_usd, Decimal("750.00"))
        self.assertEqual(STARTER.acceptance_balance_usd, Decimal("750.00"))

    def test_approval_gate_and_draft_only(self):
        summary = get_offer(STARTER.slug).public_summary()
        self.assertTrue(summary["draft_only"])
        self.assertTrue(summary["requires_owner_approval"])
        self.assertIn("Unapproved outbound messaging or unsolicited bulk email", summary["exclusions"])

    def test_optional_support_not_added_to_setup(self):
        self.assertEqual(STARTER.support_monthly_usd, Decimal("200.00"))
        self.assertEqual(STARTER.setup_usd, Decimal("1500.00"))


if __name__ == "__main__":
    unittest.main()
