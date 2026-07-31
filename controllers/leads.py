import hmac
import json

from odoo import http
from odoo.http import request
from odoo.tools.mail import single_email_re

from .base import API_PREFIX


class VarscoContentApiLeads(http.Controller):
    """Secure S2S endpoint: the frontend BFF forwards form submissions here.

    auth="public" because there's no end-user Odoo session at this point —
    this route is called server-to-server, so the write_token bearer check
    below is the actual gate (architecture.md §5, odoo_api_spec.md §2.2).
    """

    REQUIRED_FIELDS = ("name", "email", "message", "source")

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
        # hmac.compare_digest: constant-time comparison, avoids a timing
        # side-channel on the token check.
        return bool(expected) and hmac.compare_digest(provided, expected)

    @http.route(
        f"{API_PREFIX}/leads",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def create_lead(self, **kwargs):
        if not self._write_token_valid():
            return self._unauthorized()
        try:
            # The frontend BFF sends a plain JSON body (fetch + JSON.stringify),
            # not Odoo's JSON-RPC envelope — parse it directly, matching how
            # every POST route in this addon must handle type="http".
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            return self._bad_request("invalid_json")
        missing = [field for field in self.REQUIRED_FIELDS if not payload.get(field)]
        if missing:
            return self._bad_request(f"missing_fields:{','.join(missing)}")
        if not single_email_re.match(payload["email"]):
            return self._bad_request("invalid_email")

        medium = request.env.ref("utm.utm_medium_website", raise_if_not_found=False)
        lead = (
            request.env["crm.lead"]
            .sudo()
            .create(
                {
                    "name": f"Web inquiry — {payload['name']}",
                    "contact_name": payload["name"],
                    "email_from": payload["email"],
                    "partner_name": payload.get("company") or False,
                    "phone": payload.get("phone") or False,
                    "description": payload["message"],
                    "medium_id": medium.id if medium else False,
                }
            )
        )
        if payload.get("cart_summary"):
            lead.message_post(body=payload["cart_summary"])
        return request.make_json_response(
            {"status": "success", "lead_id": lead.id}, status=201
        )
