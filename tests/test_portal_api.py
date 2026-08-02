import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "varsco_content")
class TestPortalApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = "Test1234!"
        cls.partner = cls.env["res.partner"].create(
            {"name": "Portal Buyer", "email": "portal.buyer@example.com"}
        )
        cls.portal_user = cls.env["res.users"].create(
            {
                "name": "Portal Buyer",
                "login": "portal.buyer@example.com",
                "password": cls.password,
                "partner_id": cls.partner.id,
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )
        cls.order = cls.env["sale.order"].create({"partner_id": cls.partner.id})

    def test_login_wrong_password_is_unauthorized(self):
        response = self.url_open(
            "/api/v1/portal/auth/login",
            data=json.dumps({"login": "portal.buyer@example.com", "password": "wrong"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 401)

    def test_login_success_returns_session_and_user(self):
        response = self.url_open(
            "/api/v1/portal/auth/login",
            data=json.dumps(
                {"login": "portal.buyer@example.com", "password": self.password}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["session_id"])
        self.assertEqual(payload["user"]["email"], "portal.buyer@example.com")

    def test_login_response_session_id_matches_the_actual_session_cookie(self):
        """Regression test: session.authenticate() only flags should_rotate —
        the sid itself doesn't change until _save_session() runs. Reading
        session.sid before forcing that (portal_login()'s previous bug)
        returns a pre-rotation value in the JSON body that differs from the
        Set-Cookie header on the very same response. A caller (this repo's
        own frontend) that stores the JSON field as its session id then gets
        rejected as unauthorized on every following request — this is
        exactly what previously produced "unauthorised" checkout errors.
        """
        response = self.url_open(
            "/api/v1/portal/auth/login",
            data=json.dumps(
                {"login": "portal.buyer@example.com", "password": self.password}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        payload = json.loads(response.content)
        self.assertEqual(
            payload["session_id"],
            response.cookies.get("session_id"),
            "JSON body's session_id must match the Set-Cookie session_id — "
            "otherwise every caller that authenticates against this "
            "endpoint gets a session id Odoo will reject as unauthorized.",
        )

    def test_orders_requires_authentication(self):
        response = self.url_open("/api/v1/portal/orders")
        self.assertEqual(response.status_code, 401)

    def test_orders_returns_authenticated_partner_orders(self):
        self.authenticate("portal.buyer@example.com", self.password)
        response = self.url_open("/api/v1/portal/orders")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual([o["order_id"] for o in payload["data"]], [self.order.id])

    def test_profile_update_writes_allowed_fields_only(self):
        self.authenticate("portal.buyer@example.com", self.password)
        response = self.url_open(
            "/api/v1/portal/profile",
            data=json.dumps(
                {
                    "phone": "+90 555 111 2233",
                    "company": "New Co",
                    "street": "Ismet Kaptan Mah. No:6",
                    "city": "Izmir",
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        self.assertEqual(response.status_code, 200)
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.phone, "+90 555 111 2233")
        self.assertEqual(self.partner.company_name, "New Co")
        self.assertEqual(self.partner.street, "Ismet Kaptan Mah. No:6")
        self.assertEqual(self.partner.city, "Izmir")

    def test_login_response_includes_street_and_city(self):
        self.partner.write({"street": "Test Street 1", "city": "Konak"})
        response = self.url_open(
            "/api/v1/portal/auth/login",
            data=json.dumps(
                {"login": "portal.buyer@example.com", "password": self.password}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        payload = json.loads(response.content)
        self.assertEqual(payload["user"]["street"], "Test Street 1")
        self.assertEqual(payload["user"]["city"], "Konak")

    def test_profile_update_rejects_cross_origin_request(self):
        """A browser holding a real erp.varsco.com session cookie (e.g. via
        /web/login directly) must not be CSRF'd into a profile write from an
        unrelated site — docs/security.md §3's promise that Odoo rejects
        cross-origin browser calls outside the sanctioned frontend proxy."""
        self.authenticate("portal.buyer@example.com", self.password)
        response = self.url_open(
            "/api/v1/portal/profile",
            data=json.dumps({"phone": "+90 555 999 8888"}).encode(),
            headers={"Content-Type": "application/json", "Origin": "https://evil.example.com"},
            method="PUT",
        )
        self.assertEqual(response.status_code, 403)
        self.partner.invalidate_recordset()
        self.assertNotEqual(self.partner.phone, "+90 555 999 8888")

    def test_profile_update_accepts_turkey_english_name(self):
        """Odoo's own res.country data stores Turkey as 'Türkiye' — a form
        submitting the English name (what this frontend actually sends)
        must still resolve, not 400 with unknown_country."""
        self.authenticate("portal.buyer@example.com", self.password)
        response = self.url_open(
            "/api/v1/portal/profile",
            data=json.dumps({"country": "Turkey"}).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        self.assertEqual(response.status_code, 200)
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.country_id.code, "TR")

    def test_profile_update_allows_configured_frontend_origin(self):
        self.authenticate("portal.buyer@example.com", self.password)
        response = self.url_open(
            "/api/v1/portal/profile",
            data=json.dumps({"phone": "+90 555 111 2233"}).encode(),
            headers={"Content-Type": "application/json", "Origin": "https://varsco.com"},
            method="PUT",
        )
        self.assertEqual(response.status_code, 200)
