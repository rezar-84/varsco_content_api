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
            data=json.dumps({"phone": "+90 555 111 2233", "company": "New Co"}).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        self.assertEqual(response.status_code, 200)
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.phone, "+90 555 111 2233")
        self.assertEqual(self.partner.company_name, "New Co")
