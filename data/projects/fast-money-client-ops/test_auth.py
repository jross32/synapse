import copy
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

import server
from local_auth import LocalSessionStore, SESSION_TTL_SECONDS


class LocalSessionStoreTests(unittest.TestCase):
    def test_expired_session_is_removed(self):
        now = [1_788_220_800.0]
        store = LocalSessionStore(ttl_seconds=10, clock=lambda: now[0])
        session = store.create("operator")

        self.assertIs(store.get(session.token), session)
        now[0] += 11
        self.assertIsNone(store.get(session.token))

    def test_public_payload_only_exposes_csrf_when_requested(self):
        store = LocalSessionStore()
        session = store.create("customer")

        self.assertNotIn("csrf_token", session.public())
        self.assertEqual(
            session.public(include_csrf=True)["csrf_token"],
            session.csrf_token,
        )


class HandlerAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        seed = copy.deepcopy(server.SEED_DATA)
        seed["quotes"].append(
            {
                "id": "quote-2002",
                "lead_id": "lead-1002",
                "package": "Expansion Retainer",
                "status": "sent",
                "amount_usd": 9200,
            }
        )
        server.WORKFLOW_STORE = server.WorkflowStore(
            Path(self.temp_dir.name) / "workspace-state.json",
            seed,
        )
        self.now = [1_788_220_800.0]
        server.SESSION_STORE = LocalSessionStore(
            ttl_seconds=60,
            clock=lambda: self.now[0],
        )
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def request(self, method, path, *, body=None, cookie=None, csrf=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Accept": "application/json"}
        payload = None
        if body is not None:
            payload = json.dumps(body)
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        result = (
            json.loads(raw.decode("utf-8"))
            if raw and content_type.startswith("application/json")
            else raw.decode("utf-8")
        )
        headers_out = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return response.status, headers_out, result

    def login(self, role, *, cookie=None):
        status, headers, payload = self.request(
            "POST",
            "/api/session/login",
            body={"role": role},
            cookie=cookie,
        )
        self.assertEqual(status, 200)
        session_cookie = headers["set-cookie"].split(";", 1)[0]
        return session_cookie, headers["set-cookie"], payload

    def test_signed_stripe_webhook_updates_invoice_over_http(self):
        import hashlib, hmac, os, time
        from unittest.mock import patch
        invoice = {"id":"inv-http","status":"sent","amount_usd":75,"lead_id":"lead-1001"}
        server.WORKFLOW_STORE.seed_data["invoices"].append(invoice)
        server.WORKFLOW_STORE.bind_checkout("inv-http", {"id":"cs_test_http","url":"https://checkout.stripe.com/test"})
        event = {"id":"evt_http_1","livemode":False,"type":"checkout.session.completed",
                 "data":{"object":{"id":"cs_test_http","payment_status":"paid",
                   "client_reference_id":"inv-http","metadata":{"invoice_id":"inv-http"},
                   "currency":"usd","amount_total":7500}}}
        raw=json.dumps(event).encode()
        stamp=int(time.time())
        signature=hmac.new(b"whsec_local_test",str(stamp).encode()+b"."+raw,hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET":"whsec_local_test"}):
            connection=http.client.HTTPConnection("127.0.0.1",self.port,timeout=5)
            connection.request("POST","/api/stripe/webhook",body=raw,
                               headers={"Stripe-Signature":f"t={stamp},v1={signature}",
                                        "Content-Type":"application/json"})
            response=connection.getresponse()
            payload=json.loads(response.read())
            connection.close()
        self.assertEqual(response.status,200)
        self.assertTrue(payload["result"]["verified"])
        invoice=next(i for i in server.WORKFLOW_STORE.load()["data"]["invoices"] if i["id"]=="inv-http")
        self.assertTrue(invoice["payment_verified"])
        self.assertEqual(invoice["status"],"paid")

    def test_checkout_requires_operator_and_csrf(self):
        status, _, _ = self.request("POST", "/api/invoices/inv-unknown/checkout")
        self.assertEqual(status, 401)
        cookie, _, auth = self.login("customer")
        status, _, _ = self.request("POST", "/api/invoices/inv-unknown/checkout",
                                    cookie=cookie, csrf=auth["session"]["csrf_token"])
        self.assertEqual(status, 403)
        cookie, _, auth = self.login("operator")
        status, _, _ = self.request("POST", "/api/invoices/inv-unknown/checkout",cookie=cookie)
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/invoices/inv-unknown/checkout",
                                    cookie=cookie, csrf=auth["session"]["csrf_token"])
        self.assertEqual(status, 404)

    def test_unsigned_stripe_webhook_rejected_over_http(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET":"whsec_local_test"}):
            status, _, result = self.request("POST", "/api/stripe/webhook",
                                              body={"id":"evt_fake","type":"checkout.session.completed"})
        self.assertEqual(status, 400)
        self.assertFalse(result["ok"])
        self.assertFalse(any(x.get("payment_verified") for x in server.WORKFLOW_STORE.load()["data"]["invoices"]))

    def test_client_hunter_run_requires_operator_and_csrf(self):
        status, _, _ = self.request("POST", "/api/client-hunter/run")
        self.assertEqual(status, 401)
        cookie, _, auth = self.login("customer")
        status, _, _ = self.request("POST", "/api/client-hunter/run", cookie=cookie,
                                    csrf=auth["session"]["csrf_token"])
        self.assertEqual(status, 403)
        op, _, login = self.login("operator")
        status, _, _ = self.request("POST", "/api/client-hunter/run", cookie=op)
        self.assertEqual(status, 403)
        status, _, result = self.request("POST", "/api/client-hunter/run", cookie=op,
                                        csrf=login["session"]["csrf_token"])
        self.assertEqual(status, 200)
        self.assertEqual(result["processed"], 3)
        self.assertEqual(result["external_messages_sent"], 0)
        self.assertEqual(result["mode"], "DRY_RUN_NO_SEND")
    def test_client_hunter_readiness_operator_only(self):
        status, _, _ = self.request("GET", "/api/client-hunter/readiness")
        self.assertEqual(status, 401)
        customer_cookie, _, _ = self.login("customer")
        status, _, _ = self.request("GET", "/api/client-hunter/readiness", cookie=customer_cookie)
        self.assertEqual(status, 403)
        operator_cookie, _, _ = self.login("operator")
        status, headers, result = self.request("GET", "/api/client-hunter/readiness", cookie=operator_cookie)
        self.assertEqual(status, 200)
        self.assertFalse(result["ready_for_outreach"])
        self.assertEqual(result["drafts"], 3)
        self.assertEqual(headers.get("cache-control"), "no-store")
    def test_workspace_requires_a_session_and_ops_page_redirects(self):
        status, _, payload = self.request("GET", "/api/workspace-state")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "Sign in to continue.")

        status, headers, _ = self.request("GET", "/ops")
        self.assertEqual(status, 303)
        self.assertEqual(headers["location"], "/signin")

    def test_customer_session_is_scoped_and_cookie_is_hardened_for_local_http(self):
        cookie, set_cookie, login = self.login("customer")
        self.assertEqual(login["session"]["role"], "customer")
        self.assertIn("csrf_token", login["session"])
        self.assertIn("expires_at", login["session"])
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)
        self.assertIn(f"Max-Age={SESSION_TTL_SECONDS}", set_cookie)
        self.assertNotIn("Secure", set_cookie)

        status, _, workspace = self.request(
            "GET",
            "/api/workspace-state",
            cookie=cookie,
        )
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in workspace["data"]["leads"]], ["lead-1001"])
        self.assertEqual([item["id"] for item in workspace["data"]["quotes"]], ["quote-2001"])
        self.assertEqual(workspace["audit_log"], [])

    def test_authenticated_mutation_rejects_missing_and_forged_csrf(self):
        cookie, _, login = self.login("customer")
        csrf = login["session"]["csrf_token"]

        status, _, payload = self.request(
            "POST",
            "/api/quotes/quote-2001/approve",
            cookie=cookie,
        )
        self.assertEqual(status, 403)
        self.assertEqual(
            payload["error"],
            "Request verification failed. Refresh and try again.",
        )

        status, _, payload = self.request(
            "POST",
            "/api/quotes/quote-2001/approve",
            cookie=cookie,
            csrf="forged-token",
        )
        self.assertEqual(status, 403)

        status, _, payload = self.request(
            "POST",
            "/api/quotes/quote-2001/approve",
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

    def test_customer_can_approve_own_quote_but_not_another_lead_or_operator_action(self):
        cookie, _, login = self.login("customer")
        csrf = login["session"]["csrf_token"]

        status, _, payload = self.request(
            "POST",
            "/api/quotes/quote-2001/approve",
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

        status, _, payload = self.request(
            "POST",
            "/api/quotes/quote-2002/approve",
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "That quote is outside this customer session.")

        status, _, payload = self.request(
            "POST",
            "/api/jobs/job-2001/schedule",
            cookie=cookie,
            csrf=csrf,
            body={"owner": "Jordan", "scheduled_for": "2026-09-01T10:00"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Operator access is required.")

    def test_operator_can_read_full_workspace_and_run_operator_transition(self):
        cookie, _, login = self.login("operator")
        csrf = login["session"]["csrf_token"]
        self.assertEqual(login["session"]["role"], "operator")

        status, _, workspace = self.request(
            "GET",
            "/api/workspace-state",
            cookie=cookie,
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            {item["id"] for item in workspace["data"]["leads"]},
            {"lead-1001", "lead-1002"},
        )

        status, _, payload = self.request(
            "POST",
            "/api/jobs/job-3001/complete",
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

        status, _, payload = self.request(
            "POST",
            "/api/quotes/quote-2001/approve",
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Customer access is required.")

    def test_role_switch_revokes_previous_session(self):
        operator_cookie, _, _ = self.login("operator")
        customer_cookie, _, customer_login = self.login(
            "customer",
            cookie=operator_cookie,
        )

        status, _, payload = self.request(
            "GET",
            "/api/workspace-state",
            cookie=operator_cookie,
        )
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "Sign in to continue.")

        status, _, workspace = self.request(
            "GET",
            "/api/workspace-state",
            cookie=customer_cookie,
        )
        self.assertEqual(status, 200)
        self.assertEqual(customer_login["session"]["role"], "customer")
        self.assertEqual([item["id"] for item in workspace["data"]["leads"]], ["lead-1001"])

    def test_expired_session_is_rejected(self):
        cookie, _, _ = self.login("operator")
        self.now[0] += 61

        status, _, payload = self.request(
            "GET",
            "/api/workspace-state",
            cookie=cookie,
        )
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "Sign in to continue.")

    def test_logout_requires_csrf_and_invalidates_session(self):
        cookie, _, login = self.login("operator")
        csrf = login["session"]["csrf_token"]

        status, _, payload = self.request(
            "POST",
            "/api/session/logout",
            cookie=cookie,
        )
        self.assertEqual(status, 403)
        self.assertEqual(
            payload["error"],
            "Request verification failed. Refresh and try again.",
        )

        status, headers, payload = self.request(
            "POST",
            "/api/session/logout",
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("Max-Age=0", headers["set-cookie"])

        status, _, payload = self.request(
            "GET",
            "/api/workspace-state",
            cookie=cookie,
        )
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "Sign in to continue.")


if __name__ == "__main__":
    unittest.main()
