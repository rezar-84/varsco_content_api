import hmac
import json

from odoo import http
from odoo.http import request
from odoo.tools.mail import single_email_re

from .base import API_PREFIX

DEFAULT_LIST_NAME = "Website Newsletter"
LIST_NAME_PARAM = "varsco_content_api.newsletter_list_name"


class VarscoContentApiNewsletter(http.Controller):
    """Newsletter signup, kept out of the CRM pipeline.

    Signups previously went to /api/v1/leads, so every subscriber became a
    crm.lead named "Newsletter Subscriber" with company "N/A" sitting in the
    sales pipeline next to real enquiries. A subscriber is not a lead: nobody
    is going to call them, and they distort every pipeline count.

    mass_mailing is deliberately NOT added to this module's `depends`. The
    module is meant to be reusable across client Odoo instances
    (see __manifest__.py), and most clients will not run mass mailing — so
    rather than forcing that install on everyone, this route reports
    unavailability when the models are absent.
    """

    @staticmethod
    def _unauthorized():
        return request.make_json_response({"error": "unauthorized"}, status=401)

    @staticmethod
    def _bad_request(reason):
        return request.make_json_response({"error": reason}, status=400)

    def _write_token_valid(self):
        header = request.httprequest.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        provided = header[len("Bearer "):].strip()
        expected = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("varsco_content_api.write_token", "")
        )
        return bool(expected) and hmac.compare_digest(provided, expected)

    @staticmethod
    def _target_list():
        """The mailing list to subscribe to, created on first use.

        Configurable via ir.config_parameter so a client can point signups at
        an existing list without editing code.
        """
        Params = request.env["ir.config_parameter"].sudo()
        name = Params.get_param(LIST_NAME_PARAM, DEFAULT_LIST_NAME)
        MailingList = request.env["mailing.list"].sudo()
        mailing_list = MailingList.search([("name", "=", name)], limit=1)
        if not mailing_list:
            mailing_list = MailingList.create({"name": name})
        return mailing_list

    @http.route(
        f"{API_PREFIX}/newsletter",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def subscribe(self, **kwargs):
        if not self._write_token_valid():
            return self._unauthorized()
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            return self._bad_request("invalid_json")

        email = (payload.get("email") or "").strip()
        if not email:
            return self._bad_request("missing_fields:email")
        if not single_email_re.match(email):
            return self._bad_request("invalid_email")

        if "mailing.contact" not in request.env:
            # 501: the request is valid, this deployment just cannot serve it.
            # Distinguishable from a 404 (route missing) so the caller can tell
            # "not installed" from "not deployed".
            return request.make_json_response(
                {"error": "mailing_not_installed"}, status=501
            )

        mailing_list = self._target_list()
        Contact = request.env["mailing.contact"].sudo()

        # Idempotent: re-submitting the same address must not create duplicate
        # contacts, and a visitor pressing subscribe twice is not an error.
        contact = Contact.search([("email", "=", email)], limit=1)
        if not contact:
            values = {"email": email}
            if payload.get("name"):
                values["name"] = payload["name"]
            if payload.get("company"):
                values["company_name"] = payload["company"]
            contact = Contact.create(values)

        already = mailing_list in contact.list_ids
        if not already:
            contact.write({"list_ids": [(4, mailing_list.id)]})

        return request.make_json_response(
            {
                "status": "success",
                "contact_id": contact.id,
                # Lets the frontend say "you are already subscribed" rather
                # than implying a new signup every time.
                "already_subscribed": already,
            },
            status=201,
        )
