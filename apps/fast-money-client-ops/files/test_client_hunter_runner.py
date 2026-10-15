import json,tempfile,unittest
from pathlib import Path
from client_hunter_runner import run_cycle
from client_hunter_readiness import PIPELINE
class RunnerTests(unittest.TestCase):
 def test_real_pipeline_three_reviews_no_send(self):
  result=run_cycle()
  self.assertEqual(len(result['actions']),3)
  self.assertEqual(result['external_messages_sent'],0)
  self.assertEqual(result['mode'],'DRY_RUN_NO_SEND')
  self.assertTrue(all(not a['send_allowed'] for a in result['actions']))
 def test_missing_evidence_queues_research(self):
  with tempfile.TemporaryDirectory() as d:
   state=json.loads(PIPELINE.read_text(encoding='utf-8-sig'))
   state['leads'][0]['public_source']=''
   p=Path(d)/'leads.json';p.write_text(json.dumps(state),encoding='utf-8')
   result=run_cycle(p)
   self.assertEqual(result['actions'][0]['recommended_action'],'RESEARCH')
 def test_even_with_approval_dry_run_does_not_send(self):
  with tempfile.TemporaryDirectory() as d:
   state=json.loads(PIPELINE.read_text(encoding='utf-8-sig'))
   state['sender_address_verified']=True
   for lead in state['leads']:
    lead['recipient_approved']=True
    lead['opt_out_checked']=True
   p=Path(d)/'leads.json';p.write_text(json.dumps(state),encoding='utf-8')
   result=run_cycle(p)
   self.assertTrue(result['summary']['ready_for_outreach'])
   self.assertEqual(result['external_messages_sent'],0)
if __name__=='__main__':unittest.main()
