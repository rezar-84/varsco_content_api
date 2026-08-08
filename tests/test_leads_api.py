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

    def test_lead_is_created_as_lead_not_opportunity(self):
        """CRM is configured with a qualification step (Settings > CRM >
        Leads) — every web-submitted lead must land in that queue as
        type='lead', never skip straight to an opportunity. The public user
        that authenticates this S2S route isn't in crm.group_use_lead, so
        the ORM's own default (crm_lead.py's `type` field) would silently
        pick 'opportunity' unless we set it explicitly."""
        response = self._post(
            {
                "name": "Jane Buyer",
                "email": "jane@example.com",
                "message": "Interested in Artemia cysts.",
                "source": "request_quote",
            },
            token=self.token,
        )
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertEqual(lead.type, "lead")

    def test_subject_distinguishes_leads(self):
        """Every lead used to be named "Web inquiry — {contact name}", so the
        CRM list was a column of near-identical rows. The subject now leads
        with what the buyer wants and what they asked about."""
        response = self._post(
            {
                "name": "Jane Buyer",
                "email": "jane@example.com",
                "company": "Acme Ltd",
                "message": "20 mton please",
                "source": "product-quote-drawer",
                "product_title": "Olive Flounder",
            },
            token=self.token,
        )
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertEqual(lead.name, "Quote — Olive Flounder — Acme Ltd")

    def test_subject_falls_back_without_product_or_company(self):
        response = self._post(
            {
                "name": "Jane Buyer",
                "email": "jane@example.com",
                "message": "hello there",
                "source": "contact",
                "topic": "Technical support",
            },
            token=self.token,
        )
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertEqual(lead.name, "Contact — Technical support — Jane Buyer")

    def test_unknown_source_still_produces_a_readable_subject(self):
        """A form added on the frontend must not need an Odoo deploy first."""
        response = self._post(
            {
                "name": "Jane",
                "email": "jane@example.com",
                "message": "hello there",
                "source": "some-new-form",
            },
            token=self.token,
        )
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertEqual(lead.name, "Some New Form — Jane")

    def test_source_is_persisted_as_utm_source(self):
        """Regression: `source` was in REQUIRED_FIELDS but was only rendered
        into the description — it never reached the lead, so attribution
        reporting was impossible and every lead shared one fixed medium."""
        response = self._post(
            {
                "name": "Jane",
                "email": "jane@example.com",
                "message": "hello there",
                "source": "horeca-middle-east",
            },
            token=self.token,
        )
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertTrue(lead.source_id)
        self.assertEqual(lead.source_id.name, "HORECA")

    def test_campaign_visit_overrides_form_attribution(self):
        response = self._post(
            {
                "name": "Jane",
                "email": "jane@example.com",
                "message": "hello there",
                "source": "contact",
                "utm_source": "linkedin",
                "utm_medium": "cpc",
                "utm_campaign": "flounder-q3",
            },
            token=self.token,
        )
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertEqual(lead.source_id.name, "linkedin")
        self.assertEqual(lead.medium_id.name, "cpc")
        self.assertEqual(lead.campaign_id.name, "flounder-q3")

    def test_country_is_mapped_to_country_id(self):
        response = self._post(
            {
                "name": "Jane",
                "email": "jane@example.com",
                "message": "hello there",
                "source": "contact",
                "country": "Spain",
            },
            token=self.token,
        )
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertEqual(lead.country_id.name, "Spain")

    def test_unknown_country_does_not_break_submission(self):
        response = self._post(
            {
                "name": "Jane",
                "email": "jane@example.com",
                "message": "hello there",
                "source": "contact",
                "country": "Nowhereland",
            },
            token=self.token,
        )
        self.assertEqual(response.status_code, 201)
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertFalse(lead.country_id)

    def test_submission_context_and_custom_fields_reach_the_note(self):
        response = self._post(
            {
                "name": "Jane",
                "email": "jane@example.com",
                "message": "hello there",
                "source": "product-quote-drawer",
                "topic": "Frozen fillet",
                "page_path": "/products/seafood/olive-flounder",
                "page_section": "olive-flounder",
                "locale": "tr",
                "referrer_host": "www.google.com",
                "utm_campaign": "flounder-q3",
                "custom_fields": {"Size band": "500-600 g/pc", "Fins": "attached"},
            },
            token=self.token,
        )
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        for expected in (
            "Submitted from",
            "/products/seafood/olive-flounder",
            "www.google.com",
            "Requested specifications",
            "Size band",
            "500-600 g/pc",
        ):
            self.assertIn(expected, lead.description)

    def test_custom_field_values_are_html_escaped(self):
        """custom_fields is buyer-controlled and lands in an Html field
        rendered to internal users — same stored-XSS surface as the message."""
        response = self._post(
            {
                "name": "Jane",
                "email": "jane@example.com",
                "message": "hello there",
                "source": "contact",
                "custom_fields": {"<b>k</b>": "<script>alert(1)</script>"},
            },
            token=self.token,
        )
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertNotIn("<script>", lead.description)
        self.assertIn("&lt;script&gt;", lead.description)

    def test_legacy_payload_without_new_fields_still_works(self):
        """The frontend and this addon deploy independently; an older caller
        sending only the original five fields must keep working."""
        response = self._post(
            {
                "name": "Jane",
                "email": "jane@example.com",
                "company": "Buyer Co",
                "message": "Interested in Artemia.",
                "source": "request_quote",
            },
            token=self.token,
        )
        self.assertEqual(response.status_code, 201)
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertEqual(lead.name, "Request Quote — Buyer Co")
        self.assertEqual(lead.type, "lead")

    def test_lead_description_is_formatted_and_escapes_html(self):
        response = self._post(
            {
                "name": "<b>Jane</b> Buyer",
                "email": "jane@example.com",
                "company": "Buyer & Co",
                "phone": "+90 555 000 0000",
                "message": "Line one\nLine two",
                "source": "request_quote",
                "cart_summary": "Artemia Cysts (x2)\nFish Meal (x1)",
            },
            token=self.token,
        )
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        # Structured sections present
        for label in ("Contact", "Company", "Message", "Requested Items", "Source"):
            self.assertIn(label, lead.description)
        # User input is HTML-escaped, not injected raw into the stored HTML
        self.assertNotIn("<b>Jane</b>", lead.description)
        self.assertIn("&lt;b&gt;Jane&lt;/b&gt;", lead.description)
        self.assertIn("Buyer &amp; Co", lead.description)
        # cart_summary lines rendered as a real list, not a single blob
        self.assertIn("Artemia Cysts (x2)", lead.description)
        self.assertIn("Fish Meal (x1)", lead.description)

    def _visitor_linking_available(self):
        """crm.lead.visitor_ids ships with `website_crm`, which this addon does
        not depend on. Skip rather than fail where it is absent — the
        controller is written to degrade the same way."""
        if "visitor_ids" not in self.env["crm.lead"]._fields:
            self.skipTest("website_crm not installed; visitor linkage unavailable")

    def test_lead_links_to_the_visitor_that_browsed(self):
        """The journey and the enquiry were being stored as unrelated facts:
        /track recorded the pageviews, /leads recorded the lead, and nothing
        joined them, so sales could not see what a buyer read before asking."""
        self._visitor_linking_available()
        token = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
        visitor = self.env["website.visitor"].sudo().create({
            "access_token": token,
            "website_id": self.env["website"].sudo().search([], limit=1).id,
        })
        response = self._post(
            {
                "name": "Jane Buyer",
                "email": "jane@example.com",
                "message": "Interested in Artemia cysts.",
                "source": "request_quote",
                "visitor_token": token,
            },
            token=self.token,
        )
        self.assertEqual(response.status_code, 201)
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertIn(visitor, lead.visitor_ids)

    def test_unknown_visitor_token_creates_no_visitor(self):
        """A token with no visitor behind it means the buyer never accepted
        analytics. Minting one here would put a visitor with zero pageviews
        into the report, so the lead is simply created unlinked."""
        self._visitor_linking_available()
        token = "ffffffffffffffffffffffffffffffff"
        before = self.env["website.visitor"].sudo().search_count([])
        response = self._post(
            {
                "name": "Jane Buyer",
                "email": "jane@example.com",
                "message": "Interested in Artemia cysts.",
                "source": "request_quote",
                "visitor_token": token,
            },
            token=self.token,
        )
        self.assertEqual(response.status_code, 201)
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertFalse(lead.visitor_ids)
        self.assertEqual(self.env["website.visitor"].sudo().search_count([]), before)

    def test_malformed_visitor_token_still_creates_the_lead(self):
        """Odoo parses a non-hex access_token as a res.partner id, which raises
        inside a computed field. A bad token must cost the linkage, never the
        enquiry."""
        response = self._post(
            {
                "name": "Jane Buyer",
                "email": "jane@example.com",
                "message": "Interested in Artemia cysts.",
                "source": "request_quote",
                "visitor_token": "../../etc/passwd",
            },
            token=self.token,
        )
        self.assertEqual(response.status_code, 201)
        lead = self.env["crm.lead"].sudo().browse(json.loads(response.content)["lead_id"])
        self.assertEqual(lead.email_from, "jane@example.com")
