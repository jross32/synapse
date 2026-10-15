import unittest
from unittest.mock import patch
from stripe_payments import checkout_session
class CheckoutRetryTests(unittest.TestCase):
    def test_retries_have_unique_keys(self):
        keys=[]
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,*args): return b'{"id":"cs_test_mock","url":"https://checkout.stripe.com/mock"}'
        def fake_urlopen(req,timeout):
            keys.append(req.get_header("Idempotency-key"))
            return Response()
        with patch.dict("os.environ",{"STRIPE_SECRET_KEY":"sk_test_mock"}),patch("stripe_payments.urlopen",side_effect=fake_urlopen):
            for _ in range(2):
                checkout_session(invoice_id="inv-1",amount_cents=1000,success_url="https://example.com/s",cancel_url="https://example.com/c")
        self.assertEqual(len(keys),2)
        self.assertNotEqual(keys[0],keys[1])
        self.assertTrue(all(key.startswith("whatif-checkout-inv-1-") for key in keys))
if __name__=="__main__":unittest.main()
