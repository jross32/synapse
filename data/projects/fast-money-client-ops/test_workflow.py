import json
import tempfile
import unittest
from pathlib import Path

import server


class WorkflowStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp_dir.name) / "workspace-state.json"
        self.store = server.WorkflowStore(self.state_path, server.SEED_DATA)

    def tearDown(self):
        self.temp_dir.cleanup()

    def approve_and_schedule(self):
        self.store.approve_quote("quote-2001")
        self.store.schedule_job(
            "job-2001",
            owner="Jordan",
            scheduled_for="2026-09-01T10:00",
        )

    def test_initial_state_uses_seed_without_writing(self):
        state = self.store.load()
        self.assertEqual(state["schema_version"], 2)
        self.assertEqual(state["workspace_id"], "local-default")
        self.assertEqual(state["data"]["quotes"][0]["status"], "sent")
        self.assertEqual(state["audit_log"], [])
        self.assertFalse(self.state_path.exists())

    def test_approval_persists_shared_state_and_audit_event(self):
        state, result = self.store.approve_quote("quote-2001")
        quote = state["data"]["quotes"][0]
        lead = next(item for item in state["data"]["leads"] if item["id"] == "lead-1001")
        job = next(item for item in state["data"]["jobs"] if item.get("quote_id") == "quote-2001")

        self.assertFalse(result["already_approved"])
        self.assertEqual(quote["status"], "approved")
        self.assertEqual(lead["stage"], "approved")
        self.assertEqual(job["status"], "ready-to-schedule")
        self.assertEqual([event["type"] for event in state["audit_log"]], ["quote.approved"])
        self.assertTrue(self.state_path.exists())

    def test_repeat_approval_is_idempotent(self):
        first_state, _ = self.store.approve_quote("quote-2001")
        second_state, result = self.store.approve_quote("quote-2001")

        jobs = [item for item in second_state["data"]["jobs"] if item.get("quote_id") == "quote-2001"]
        self.assertTrue(result["already_approved"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(second_state["audit_log"]), 1)
        self.assertEqual(second_state["audit_log"][0]["id"], first_state["audit_log"][0]["id"])

    def test_schedule_requires_owner_and_valid_datetime(self):
        self.store.approve_quote("quote-2001")
        with self.assertRaisesRegex(ValueError, "Owner is required"):
            self.store.schedule_job("job-2001", owner="", scheduled_for="2026-09-01T10:00")
        with self.assertRaisesRegex(ValueError, "invalid"):
            self.store.schedule_job("job-2001", owner="Jordan", scheduled_for="not-a-date")

    def test_schedule_is_persisted_and_idempotent(self):
        self.store.approve_quote("quote-2001")
        first_state, first = self.store.schedule_job(
            "job-2001",
            owner="Jordan",
            scheduled_for="2026-09-01T10:00",
        )
        second_state, second = self.store.schedule_job(
            "job-2001",
            owner="Jordan",
            scheduled_for="2026-09-01T10:00",
        )

        job = next(item for item in second_state["data"]["jobs"] if item["id"] == "job-2001")
        self.assertFalse(first["already_scheduled"])
        self.assertTrue(second["already_scheduled"])
        self.assertEqual(job["owner"], "Jordan")
        self.assertEqual(job["scheduled_for"], "2026-09-01T10:00")
        self.assertEqual([event["type"] for event in first_state["audit_log"]], ["quote.approved", "job.scheduled"])
        self.assertEqual(len(second_state["audit_log"]), 2)

    def test_reschedule_records_distinct_audit_event(self):
        self.approve_and_schedule()
        state, result = self.store.schedule_job(
            "job-2001",
            owner="Mina",
            scheduled_for="2026-09-02T14:30",
        )

        self.assertTrue(result["rescheduled"])
        self.assertEqual(state["data"]["jobs"][-1]["owner"], "Mina")
        self.assertEqual(state["audit_log"][-1]["type"], "job.rescheduled")

    def test_complete_requires_scheduled_job(self):
        self.store.approve_quote("quote-2001")
        with self.assertRaisesRegex(ValueError, "Schedule the job"):
            self.store.complete_job("job-2001")

    def test_complete_creates_invoice_once_and_advances_lead(self):
        self.approve_and_schedule()
        state, result = self.store.complete_job("job-2001")
        repeated, second = self.store.complete_job("job-2001")

        invoice = next(item for item in state["data"]["invoices"] if item.get("job_id") == "job-2001")
        lead = next(item for item in state["data"]["leads"] if item["id"] == "lead-1001")
        self.assertFalse(result["already_completed"])
        self.assertEqual(invoice["amount_usd"], 4800)
        self.assertEqual(invoice["status"], "draft")
        self.assertEqual(lead["stage"], "delivered")
        self.assertTrue(second["already_completed"])
        self.assertEqual(
            len([item for item in repeated["data"]["invoices"] if item.get("job_id") == "job-2001"]),
            1,
        )
        self.assertEqual(len([event for event in repeated["audit_log"] if event["type"] == "job.completed"]), 1)

    def test_seed_scheduled_job_can_create_invoice_from_matching_lead(self):
        state, result = self.store.complete_job("job-3001")
        invoice = next(item for item in state["data"]["invoices"] if item["id"] == result["invoice_id"])
        self.assertEqual(invoice["client"], "Bright Dental Group")
        self.assertEqual(invoice["amount_usd"], 9200)
        self.assertEqual(invoice["lead_id"], "lead-1002")

    def test_invoice_send_and_verified_payment_create_renewal_handoff(self):
        self.approve_and_schedule()
        completed, result = self.store.complete_job("job-2001")
        invoice_id = result["invoice_id"]
        sent, send_result = self.store.send_invoice(invoice_id)
        session_id = "cs_test_workflow"
        self.store.bind_checkout(invoice_id, {"id":session_id,"url":"https://checkout.stripe.com/test"})
        invoice = next(i for i in sent["data"]["invoices"] if i["id"] == invoice_id)
        event = {"id":"evt_workflow_1","livemode":False,"type":"checkout.session.completed",
                 "data":{"object":{"id":session_id,"payment_status":"paid",
                 "client_reference_id":invoice_id,"metadata":{"invoice_id":invoice_id},
                 "currency":"usd","amount_total":int(invoice["amount_usd"])*100}}}
        verified = self.store.confirm_stripe_payment(event)
        repeated = self.store.confirm_stripe_payment(event)
        paid = self.store.load()
        paid_invoice = next(i for i in paid["data"]["invoices"] if i["id"] == invoice_id)
        self.assertFalse(send_result["already_sent"])
        self.assertTrue(verified["verified"])
        self.assertTrue(repeated["duplicate"])
        self.assertTrue(paid_invoice["payment_verified"])
        self.assertEqual(paid_invoice["status"], "paid")
        self.assertEqual(paid_invoice["renewal_status"], "ready")
        self.assertEqual(
            [e["type"] for e in paid["audit_log"]],
            ["quote.approved", "job.scheduled", "job.completed", "invoice.sent", "invoice.stripe_verified"])
        self.assertEqual(len(paid["audit_log"]), 5)
        self.assertEqual(completed["data"]["invoices"][-1]["status"], "draft")

    def test_state_survives_new_store_instance(self):
        self.approve_and_schedule()
        self.store.complete_job("job-2001")
        reloaded = server.WorkflowStore(self.state_path, server.SEED_DATA).load()

        self.assertEqual(reloaded["schema_version"], 2)
        self.assertEqual(
            next(item for item in reloaded["data"]["jobs"] if item["id"] == "job-2001")["status"],
            "completed",
        )
        self.assertEqual(len(reloaded["audit_log"]), 3)

    def test_missing_records_do_not_create_state_file(self):
        with self.assertRaises(KeyError):
            self.store.approve_quote("quote-missing")
        with self.assertRaises(KeyError):
            self.store.schedule_job("job-missing", owner="Jordan", scheduled_for="2026-09-01T10:00")
        with self.assertRaises(KeyError):
            self.store.send_invoice("inv-missing")
        self.assertFalse(self.state_path.exists())


if __name__ == "__main__":
    unittest.main()
