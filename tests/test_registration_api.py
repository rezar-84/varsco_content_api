import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "varsco_content")
class TestRegistrationApi(HttpCase):
    def _register(self, **overrides):
        payload = {
            "name": "New Buyer",
            "email": "new.buyer@example.com",
            "phone": "+90 555 222 3344",
            "company": "New Buyer Aquafarms",
            "country": "Turkey",
            "password": "StrongPass123!",
        }
        payload.update(overrides)
        return self.url_open(
            "/api/v1/portal/auth/register",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )

    def test_register_creates_real_working_account(self):
        response = self._register()
        self.assertEqual(response.status_code, 201)
        payload = json.loads(response.content)
        self.assertTrue(payload["session_id"])
        self.assertEqual(payload["user"]["email"], "new.buyer@example.com")

        # Regression check (see test_portal_api.py's identical test for the
        # full rationale): the JSON body's session_id must match the actual
        # Set-Cookie session, or a caller storing this field gets rejected
        # as unauthorized on every following request.
        self.assertEqual(payload["session_id"], response.cookies.get("session_id"))

        user = self.env["res.users"].sudo().search([("login", "=", "new.buyer@example.com")])
        self.assertEqual(len(user), 1)
        self.assertIn(self.env.ref("base.group_portal"), user.group_ids)
        self.assertNotIn(self.env.ref("base.group_user"), user.group_ids)

        # The password actually works for a subsequent, independent login —
        # not just accepted and discarded.
        login_response = self.url_open(
            "/api/v1/portal/auth/login",
            data=json.dumps(
                {"login": "new.buyer@example.com", "password": "StrongPass123!"}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(login_response.status_code, 200)

    def test_register_rejects_duplicate_email(self):
        first = self._register()
        self.assertEqual(first.status_code, 201)
        second = self._register(name="Someone Else")
        self.assertEqual(second.status_code, 409)
        self.assertEqual(
            self.env["res.users"].sudo().search_count([("login", "=", "new.buyer@example.com")]), 1
        )

    def test_register_rejects_missing_required_field(self):
        response = self._register(password="")
        self.assertEqual(response.status_code, 400)

    def test_register_rejects_invalid_email_format(self):
        response = self._register(email="not-an-email")
        self.assertEqual(response.status_code, 400)

    def test_register_rejects_short_password(self):
        response = self._register(email="short.pw@example.com", password="abc")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.env["res.users"].sudo().search_count([("login", "=", "short.pw@example.com")]), 0
        )

    def test_register_rejects_cross_origin_request(self):
        response = self._register(email="cross.origin@example.com")
        # baseline sanity check uses no Origin header (allowed); now confirm
        # a foreign Origin is rejected before any account is created.
        self.assertEqual(response.status_code, 201)
        rejected = self.url_open(
            "/api/v1/portal/auth/register",
            data=json.dumps(
                {
                    "name": "Attacker Buyer",
                    "email": "attacker@example.com",
                    "phone": "+90 555 000 1111",
                    "company": "Attacker Co",
                    "country": "Turkey",
                    "password": "StrongPass123!",
                }
            ).encode(),
            headers={"Content-Type": "application/json", "Origin": "https://evil.example.com"},
        )
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(
            self.env["res.users"].sudo().search_count([("login", "=", "attacker@example.com")]), 0
        )
