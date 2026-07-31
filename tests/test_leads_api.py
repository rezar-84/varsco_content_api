import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "varsco_content")
class TestLeadsApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.token = "test-write-token-secret"
        cls.env["ir.config_parameter"].sudo().set_param(
            "varsco_content_api.write_token", cls.token
        )

    def _post(self, payload, token=None):
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        return self.url_open(
            "/api/v1/leads",
            data=json.dumps(payload).encode(),
            headers=headers,
        )

    def test_missing_token_is_unauthorized(self):
        response = self._post({"name": "A", "email": "a@example.com", "message": "hi", "source": "test"})
        self.assertEqual(response.status_code, 401)

    def test_wrong_token_is_unauthorized(self):
        response = self._post(
            {"name": "A", "email": "a@example.com", "message": "hi", "source": "test"},
            token="wrong-token",
        )
        self.assertEqual(response.status_code, 401)

    def test_missing_required_field_is_bad_request(self):
        response = self._post({"name": "A", "email": "a@example.com"}, token=self.token)
        self.assertEqual(response.status_code, 400)

    def test_malformed_email_is_bad_request(self):
        response = self._post(
            {"name": "A", "email": "not-an-email", "message": "hi", "source": "test"},
            token=self.token,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.env["crm.lead"].sudo().search_count([("contact_name", "=", "A")]), 0)

    def test_valid_lead_creates_crm_lead(self):
        response = self._post(
            {
                "name": "Jane Buyer",
                "email": "jane@example.com",
                "company": "Buyer Co",
                "phone": "+90 555 000 0000",
                "message": "Interested in Artemia cysts, 500kg/month.",
                "source": "request_quote",
                "cart_summary": "Artemia Cysts (x2)",
            },
            token=self.token,
        )
        self.assertEqual(response.status_code, 201)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], "success")
        lead = self.env["crm.lead"].sudo().browse(payload["lead_id"])
        self.assertEqual(lead.email_from, "jane@example.com")
        self.assertEqual(lead.contact_name, "Jane Buyer")
