import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "varsco_content")
class TestNewsletterApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.token = "test-write-token-secret"
        cls.env["ir.config_parameter"].sudo().set_param(
            "varsco_content_api.write_token", cls.token
        )
        cls.mailing_installed = "mailing.contact" in cls.env

    def _post(self, payload, token=None):
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        return self.url_open(
            "/api/v1/newsletter",
            data=json.dumps(payload).encode(),
            headers=headers,
        )

    def test_missing_token_is_unauthorized(self):
        response = self._post({"email": "a@example.com"})
        self.assertEqual(response.status_code, 401)

    def test_missing_email_is_bad_request(self):
        response = self._post({}, token=self.token)
        self.assertEqual(response.status_code, 400)

    def test_malformed_email_is_bad_request(self):
        response = self._post({"email": "not-an-email"}, token=self.token)
        self.assertEqual(response.status_code, 400)

    def test_subscribe_creates_contact_not_a_lead(self):
        """The whole point of this endpoint: a subscriber must not land in the
        CRM pipeline. Signups used to be posted to /api/v1/leads, producing a
        crm.lead per subscriber that distorted every pipeline count."""
        if not self.mailing_installed:
            self.skipTest("mass_mailing not installed")
        before = self.env["crm.lead"].sudo().search_count([])
        response = self._post({"email": "sub@example.com"}, token=self.token)
        self.assertEqual(response.status_code, 201)
        body = json.loads(response.content)
        self.assertFalse(body["already_subscribed"])
        contact = self.env["mailing.contact"].sudo().browse(body["contact_id"])
        self.assertEqual(contact.email, "sub@example.com")
        self.assertTrue(contact.list_ids)
        self.assertEqual(self.env["crm.lead"].sudo().search_count([]), before)

    def test_subscribing_twice_is_idempotent(self):
        """A visitor pressing subscribe twice is not an error and must not
        create a duplicate contact."""
        if not self.mailing_installed:
            self.skipTest("mass_mailing not installed")
        first = self._post({"email": "twice@example.com"}, token=self.token)
        second = self._post({"email": "twice@example.com"}, token=self.token)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(
            json.loads(first.content)["contact_id"],
            json.loads(second.content)["contact_id"],
        )
        self.assertTrue(json.loads(second.content)["already_subscribed"])
        self.assertEqual(
            self.env["mailing.contact"].sudo().search_count([("email", "=", "twice@example.com")]),
            1,
        )

    def test_reports_501_when_mailing_is_not_installed(self):
        """mass_mailing is intentionally not a hard dependency, so a
        deployment without it must say so distinguishably from a 404."""
        if self.mailing_installed:
            self.skipTest("mass_mailing is installed in this database")
        response = self._post({"email": "sub@example.com"}, token=self.token)
        self.assertEqual(response.status_code, 501)
