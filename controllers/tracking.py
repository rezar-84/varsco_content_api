import hmac
import json
from datetime import datetime

from odoo import fields, http
from odoo.http import request

from .base import API_PREFIX, VISITOR_TOKEN_RE

MAX_EVENTS_PER_BATCH = 50
MAX_URL_LENGTH = 500


class VarscoContentApiTracking(http.Controller):
    """Visitor tracking for a decoupled frontend.

    Odoo already models this well — website.visitor holds a visitor and
    website.track holds their pageviews — but both are populated by the
    `website` module's own request handling. They only see traffic Odoo itself
    serves. With the frontend on TanStack Start, Odoo sees nothing but the
    server-to-server lead POST, so a CRM user opening a lead has no idea what
    the buyer read before enquiring.

    Nothing in Odoo is broken; it is simply never in the request path. This
    route lets the frontend's BFF forward the events Odoo would otherwise have
    collected itself, so the existing models, views and lead linkage keep
    working unchanged.

    The browser never calls this directly. The BFF forwards, which keeps the
    write token server-side and means events can be dropped before they leave
    the origin when the visitor has not consented.
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
    def _get_or_create_visitor(token, payload):
        """Resolve the website.visitor for a frontend-issued visitor token.

        access_token is Odoo's own identifier column for a visitor and is
        indexed, so reusing it avoids adding a parallel key. The frontend
        generates the value; it is opaque and carries no personal data.
        """
        Visitor = request.env["website.visitor"].sudo()
        visitor = Visitor.search([("access_token", "=", token)], limit=1)
        if visitor:
            return visitor

        values = {"access_token": token}
        # Odoo requires a website on the visitor; fall back to the first one
        # rather than failing, since a decoupled deployment may have only one.
        website = request.env["website"].sudo().search([], limit=1)
        if website:
            values["website_id"] = website.id
        if payload.get("lang_code"):
            lang = (
                request.env["res.lang"]
                .sudo()
                .search([("code", "=like", f"{payload['lang_code']}%"), ("active", "=", True)], limit=1)
            )
            if lang:
                values["lang_id"] = lang.id
        if payload.get("country_code"):
            country = (
                request.env["res.country"]
                .sudo()
                .search([("code", "=", payload["country_code"].upper())], limit=1)
            )
            if country:
                values["country_id"] = country.id
        return Visitor.create(values)

    @http.route(
        f"{API_PREFIX}/track",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def track(self, **kwargs):
        if not self._write_token_valid():
            return self._unauthorized()
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            return self._bad_request("invalid_json")

        token = (payload.get("visitor_token") or "").strip().lower()
        if not VISITOR_TOKEN_RE.match(token):
            return self._bad_request("invalid_visitor_token")

        events = payload.get("events")
        if not isinstance(events, list) or not events:
            return self._bad_request("missing_fields:events")
        # Bounded so a malicious or buggy client cannot drive an unbounded
        # write in one request. The BFF batches, so this is generous in
        # practice.
        if len(events) > MAX_EVENTS_PER_BATCH:
            return self._bad_request("too_many_events")

        visitor = self._get_or_create_visitor(token, payload)
        Track = request.env["website.track"].sudo()

        written = 0
        for event in events:
            if not isinstance(event, dict):
                continue
            url = (event.get("url") or "").strip()[:MAX_URL_LENGTH]
            if not url:
                continue
            values = {
                "visitor_id": visitor.id,
                "url": url,
                "page_id": False,
            }
            # visit_datetime is supplied by the client so a batch flushed late
            # still records when each view actually happened. Anything
            # unparseable falls back to now rather than rejecting the batch.
            stamp = event.get("at")
            if stamp:
                try:
                    values["visit_datetime"] = fields.Datetime.to_datetime(
                        datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    )
                except (ValueError, TypeError):
                    pass
            Track.create(values)
            written += 1

        # last_connection_datetime drives Odoo's own "online now" indicator and
        # visitor list ordering; without touching it a forwarded visitor would
        # always look stale.
        visitor.write({"last_connection_datetime": fields.Datetime.now()})

        return request.make_json_response(
            {"status": "success", "visitor_id": visitor.id, "tracked": written},
            status=201,
        )
