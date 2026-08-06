import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "varsco_content")
class TestTrackingApi(HttpCase):
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
            "/api/v1/track",
            data=json.dumps(payload).encode(),
            headers=headers,
        )

    def test_missing_token_is_unauthorized(self):
        response = self._post({"visitor_token": "e1b2c3d4e5f60718293a4b5c6d7e8f94", "events": [{"url": "/"}]})
        self.assertEqual(response.status_code, 401)

    def test_missing_visitor_token_is_bad_request(self):
        response = self._post({"events": [{"url": "/"}]}, token=self.token)
        self.assertEqual(response.status_code, 400)

    def test_missing_events_is_bad_request(self):
        response = self._post({"visitor_token": "e1b2c3d4e5f60718293a4b5c6d7e8f94"}, token=self.token)
        self.assertEqual(response.status_code, 400)

    def test_oversized_batch_is_rejected(self):
        """Bounded so a buggy or malicious client cannot drive an unbounded
        write in a single request."""
        response = self._post(
            {"visitor_token": "e1b2c3d4e5f60718293a4b5c6d7e8f94", "events": [{"url": f"/p/{i}"} for i in range(51)]},
            token=self.token,
        )
        self.assertEqual(response.status_code, 400)

    def test_creates_visitor_and_tracks_pageviews(self):
        response = self._post(
            {
                "visitor_token": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
                "lang_code": "en",
                "events": [
                    {"url": "/products/seafood/olive-flounder"},
                    {"url": "/request-quote"},
                ],
            },
            token=self.token,
        )
        self.assertEqual(response.status_code, 201)
        body = json.loads(response.content)
        self.assertEqual(body["tracked"], 2)
        visitor = self.env["website.visitor"].sudo().browse(body["visitor_id"])
        self.assertEqual(visitor.access_token, "a1b2c3d4e5f60718293a4b5c6d7e8f90")
        urls = self.env["website.track"].sudo().search([("visitor_id", "=", visitor.id)]).mapped("url")
        self.assertIn("/products/seafood/olive-flounder", urls)
        self.assertIn("/request-quote", urls)

    def test_same_token_reuses_the_visitor(self):
        """A returning visitor must extend one journey, not start a new one —
        otherwise the linkage to a later lead is meaningless."""
        first = self._post(
            {"visitor_token": "b1b2c3d4e5f60718293a4b5c6d7e8f91", "events": [{"url": "/"}]},
            token=self.token,
        )
        second = self._post(
            {"visitor_token": "b1b2c3d4e5f60718293a4b5c6d7e8f91", "events": [{"url": "/contactus"}]},
            token=self.token,
        )
        self.assertEqual(
            json.loads(first.content)["visitor_id"],
            json.loads(second.content)["visitor_id"],
        )

    def test_events_without_a_url_are_skipped_not_fatal(self):
        response = self._post(
            {
                "visitor_token": "c1b2c3d4e5f60718293a4b5c6d7e8f92",
                "events": [{"url": "/ok"}, {"url": ""}, {"nourl": True}],
            },
            token=self.token,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(json.loads(response.content)["tracked"], 1)

    def test_unparseable_timestamp_falls_back_instead_of_failing(self):
        response = self._post(
            {
                "visitor_token": "d1b2c3d4e5f60718293a4b5c6d7e8f93",
                "events": [{"url": "/ok", "at": "not-a-date"}],
            },
            token=self.token,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(json.loads(response.content)["tracked"], 1)

    def test_non_hex_visitor_token_is_rejected(self):
        """Regression: Odoo overloads website.visitor.access_token — a 32-char
        hex string means anonymous, anything else is parsed as a res.partner id
        by _compute_partner_id via int(). A free-form token therefore raised
        ValueError inside a computed field during flush and turned every event
        into a 500. Reject at the boundary instead."""
        response = self._post(
            {"visitor_token": "not-a-hex-token", "events": [{"url": "/"}]},
            token=self.token,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["error"], "invalid_visitor_token")
