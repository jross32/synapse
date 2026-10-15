import hashlib,hmac,json,os,time,unittest
from unittest.mock import patch
from stripe_payments import verified_webhook,checkout_session,StripeConfigurationError
class StripeAdapterTests(unittest.TestCase):
    def test_missing_key_blocks_checkout(self):
        with patch.dict(os.environ,{"STRIPE_SECRET_KEY":""}):
            with self.assertRaises(StripeConfigurationError):
                checkout_session(invoice_id="inv-1",amount_cents=1000,success_url="https://example.com/s",cancel_url="https://example.com/c")
    def test_webhook_valid_and_tamper_rejected(self):
        raw=json.dumps({"id":"evt_1","type":"checkout.session.completed"}).encode()
        stamp=int(time.time())
        sig=hmac.new(b"whsec_example",str(stamp).encode()+b"."+raw,hashlib.sha256).hexdigest()
        with patch.dict(os.environ,{"STRIPE_WEBHOOK_SECRET":"whsec_example"}):
            self.assertEqual(verified_webhook(raw,f"t={stamp},v1={sig}")["id"],"evt_1")
            with self.assertRaises(ValueError):
                verified_webhook(raw+b" ",f"t={stamp},v1={sig}")
            with self.assertRaises(ValueError):
                verified_webhook(raw,f"t={stamp-600},v1={sig}")
if __name__=="__main__":unittest.main()
