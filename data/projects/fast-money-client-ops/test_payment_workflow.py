import tempfile,unittest
from pathlib import Path
from server import WorkflowStore
class PaymentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        seed={"invoices":[{"id":"inv-1","status":"sent","amount_usd":125,"lead_id":"lead-1"}],
              "leads":[{"id":"lead-1","company":"Example","stage":"proposal"}]}
        self.store=WorkflowStore(Path(self.tmp.name)/"state.json",seed)
    def tearDown(self):
        self.tmp.cleanup()
    def event(self,**changes):
        session={"id":"cs_test_example","payment_status":"paid","client_reference_id":"inv-1",
                 "metadata":{"invoice_id":"inv-1"},"currency":"usd","amount_total":12500,
                 "payment_intent":"pi_test_example"}
        session.update(changes)
        return {"id":"evt_test_1","livemode":False,"type":"checkout.session.completed","data":{"object":session}}
    def test_verified_payment_and_replay(self):
        self.store.bind_checkout("inv-1", {"id":"cs_test_example","url":"https://checkout.stripe.com/example"})
        self.assertTrue(self.store.confirm_stripe_payment(self.event())["verified"])
        self.assertTrue(self.store.confirm_stripe_payment(self.event())["duplicate"])
        invoice=self.store.load()["data"]["invoices"][0]
        self.assertEqual(invoice["status"],"paid")
        self.assertTrue(invoice["payment_verified"])
        self.assertEqual(len(self.store.load()["audit_log"]),1)
    def test_live_event_rejected(self):
        self.store.bind_checkout("inv-1", {"id":"cs_test_example","url":"https://checkout.stripe.com/example"})
        event=self.event()
        event["livemode"]=True
        with self.assertRaisesRegex(ValueError, "sandbox"):
            self.store.confirm_stripe_payment(event)
    def test_unknown_session_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown checkout"):
            self.store.confirm_stripe_payment(self.event())
        self.assertEqual(self.store.load()["data"]["invoices"][0]["status"], "sent")
    def test_checkout_binding_persists(self):
        self.store.bind_checkout("inv-1", {"id":"cs_test_example","url":"https://checkout.stripe.com/example"})
        self.assertEqual(self.store.load()["data"]["invoices"][0]["checkout_session_ids"], ["cs_test_example"])
    def test_wrong_checkout_mode_rejected(self):
        with self.assertRaises(ValueError):
            self.store.bind_checkout("inv-1", {"id":"cs_live_fake","url":"https://checkout.stripe.com/example"})
    def test_mismatched_amount_rejected(self):
        self.store.bind_checkout("inv-1", {"id":"cs_test_example","url":"https://checkout.stripe.com/example"})
        with self.assertRaises(ValueError):
            self.store.confirm_stripe_payment(self.event(amount_total=1))
        self.assertEqual(self.store.load()["data"]["invoices"][0]["status"],"sent")
    def test_unpaid_event_ignored(self):
        self.assertTrue(self.store.confirm_stripe_payment(self.event(payment_status="unpaid"))["ignored"])
        self.assertEqual(self.store.load()["data"]["invoices"][0]["status"],"sent")
    def test_wrong_currency_rejected(self):
        self.store.bind_checkout("inv-1", {"id":"cs_test_example","url":"https://checkout.stripe.com/example"})
        with self.assertRaises(ValueError):
            self.store.confirm_stripe_payment(self.event(currency="eur"))
if __name__=="__main__":unittest.main()
