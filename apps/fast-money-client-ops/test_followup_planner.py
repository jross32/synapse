import unittest
from followup_planner import plan_actions
class FollowUpTests(unittest.TestCase):
 def test_review_only(self):
  data={"data":{"leads":[{"id":"l","company":"Example"}],"quotes":[{"id":"q","lead_id":"l","status":"sent"}],"jobs":[{"id":"j","status":"scheduled","scheduled_for":"2026-11-01T10:00"}],"invoices":[{"id":"i","status":"sent"}]}}
  result=plan_actions(data)
  self.assertEqual(len(result),3)
  self.assertTrue(all(x["approval_required"] and not x["send_enabled"] for x in result))
 def test_no_completed_followups(self):
  self.assertEqual(plan_actions({"data":{"jobs":[{"id":"j","status":"completed"}],"invoices":[{"id":"i","status":"paid"}]}}),[])
