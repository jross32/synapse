import copy, json, tempfile, unittest
from pathlib import Path
from client_hunter_readiness import PIPELINE, readiness

class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(PIPELINE.read_text(encoding='utf-8-sig'))
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'pipeline.json'
    def tearDown(self):
        self.tmp.cleanup()
    def check(self, data):
        self.path.write_text(json.dumps(data), encoding='utf-8')
        return readiness(self.path)
    def test_baseline_is_blocked(self):
        r=self.check(self.data)
        self.assertFalse(r['ready_for_outreach'])
        self.assertEqual(r['verified_sent'],0)
    def test_global_approval_does_not_authorize_recipients(self):
        self.data['sender_address_verified']=True
        self.data['outbound_approval']=True
        self.assertFalse(self.check(self.data)['ready_for_outreach'])
    def test_false_sent_requires_receipt(self):
        self.data['leads'][0]['status']='SENT'
        self.assertIn('Missing provider send receipt: gq-cleaning', self.check(self.data)['blockers'])
    def test_false_paid_requires_payment_event(self):
        self.data['leads'][0]['status']='PAID'
        self.assertIn('Missing verified payment event: gq-cleaning', self.check(self.data)['blockers'])
    def test_optout_is_blocked_even_when_approved(self):
        self.data['sender_address_verified']=True
        for lead in self.data['leads']:
            lead['recipient_approved']=True
            lead['opt_out_checked']=True
        self.data['leads'][0]['opted_out']=True
        self.assertFalse(self.check(self.data)['ready_for_outreach'])
    def test_cleared_pipeline_is_ready(self):
        self.data['sender_address_verified']=True
        for lead in self.data['leads']:
            lead['recipient_approved']=True
            lead['opt_out_checked']=True
        self.assertTrue(self.check(self.data)['ready_for_outreach'])
if __name__ == '__main__': unittest.main()
