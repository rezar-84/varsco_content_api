import json

from odoo import http
from odoo.exceptions import AccessDenied, UserError, ValidationError
from odoo.http import request
from odoo.tools.mail import single_email_re

from .base import API_PREFIX, require_trusted_origin, resolve_country

REGISTER_REQUIRED_FIELDS = ("name", "email", "phone", "company", "country", "password")
MIN_PASSWORD_LENGTH = 6  # matches the frontend's registerSchema (api.auth.register.ts)


class VarscoContentApiPortal(http.Controller):
    """Customer portal endpoints, session-cookie authenticated (odoo_api_spec.md §2.3).

    Note: /api/v1/portal/customs is intentionally not implemented yet — there
    is no customs/shipping-file model in this Odoo instance to read from.
    The frontend's existing mock fallback covers that gap until a follow-up
    session defines and builds that model.
    """

    @staticmethod
    def _bad_request(reason):
        return request.make_json_response({"error": reason}, status=400)

    @staticmethod
    def _unauthorized():
        return request.make_json_response({"error": "unauthorized"}, status=401)

    @staticmethod
    def _parsed_body():
        return json.loads(request.httprequest.get_data(as_text=True) or "{}")

    def _portal_partner(self):
        """The res.partner for the currently session-authenticated user, or None."""
        if request.env.user._is_public():
            return None
        return request.env.user.partner_id

    @http.route(
        f"{API_PREFIX}/portal/auth/login",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def portal_login(self, **kwargs):
        try:
            payload = self._parsed_body()
        except ValueError:
            return self._bad_request("invalid_json")
        login = payload.get("login")
        password = payload.get("password")
        if not login or not password:
            return self._bad_request("missing_fields:login,password")

        credential = {"login": login, "password": password, "type": "password"}
        try:
            # Standard Odoo session auth — same mechanism /web/login uses.
            # This mutates request.session in place and sets its cookie on
            # the response for us.
            request.session.authenticate(request.env, credential)
        except AccessDenied:
            return self._unauthorized()

        # authenticate() only sets session.should_rotate — the actual sid
        # rotation happens later, in the response-dispatch pipeline, unless
        # forced now via _save_session() (exactly what core Odoo's own
        # /web/session/authenticate does before reading session data back).
        # Without this, request.session.sid below is still the PRE-rotation
        # value: different from what the Set-Cookie header on this same
        # response ends up carrying, so a caller that stores this JSON
        # field as their session id (as this frontend's login flow does)
        # gets a value Odoo will reject as unauthorized on every subsequent
        # request — this was the real cause behind "unauthorised at
        # checkout", not just the separate cookie-lifetime mismatch.
        request._save_session(request.env)

        partner = request.env.user.partner_id
        return request.make_json_response(
            {
                "session_id": request.session.sid,
                "user": {
                    "id": partner.id,
                    "name": partner.name,
                    "email": partner.email or login,
                    "company": partner.commercial_company_name or "",
                    "phone": partner.phone or "",
                    "street": partner.street or "",
                    "city": partner.city or "",
                    "country": partner.country_id.name or "",
                },
            }
        )

    @http.route(
        f"{API_PREFIX}/portal/auth/register",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def portal_register(self, **kwargs):
        """Self-service B2B portal signup: creates a real res.partner +
        portal res.users (never an internal/base.group_user account — only
        base.group_portal), then logs the new account in immediately so the
        response mirrors portal_login's shape. Unlike the old frontend-only
        flow this replaces, the password the visitor sets is the one their
        account actually gets — no session is minted unless Odoo really
        created and authenticated the account.
        """
        rejection = require_trusted_origin()
        if rejection:
            return rejection
        try:
            payload = self._parsed_body()
        except ValueError:
            return self._bad_request("invalid_json")

        missing = [f for f in REGISTER_REQUIRED_FIELDS if not payload.get(f)]
        if missing:
            return self._bad_request(f"missing_fields:{','.join(missing)}")

        email = payload["email"].strip()
        if not single_email_re.match(email):
            return self._bad_request("invalid_email")

        password = payload["password"]
        if len(password) < MIN_PASSWORD_LENGTH:
            return self._bad_request("password_too_short")

        existing = request.env["res.users"].sudo().search_count([("login", "=", email)])
        if existing:
            return request.make_json_response({"error": "email_already_registered"}, status=409)

        country = resolve_country(payload["country"])
        if not country:
            return self._bad_request("unknown_country")

        partner = (
            request.env["res.partner"]
            .sudo()
            .create(
                {
                    "name": payload["name"],
                    "email": email,
                    "phone": payload["phone"],
                    "company_name": payload["company"],
                    "country_id": country.id,
                }
            )
        )
        try:
            request.env["res.users"].sudo().create(
                {
                    "name": payload["name"],
                    "login": email,
                    "password": password,
                    "partner_id": partner.id,
                    "group_ids": [(6, 0, [request.env.ref("base.group_portal").id])],
                }
            )
        except (ValidationError, UserError) as exc:
            partner.unlink()
            return self._bad_request(f"account_creation_failed:{exc}")

        try:
            request.session.authenticate(
                request.env, {"login": email, "password": password, "type": "password"}
            )
        except AccessDenied:
            # Should be unreachable — we just created these exact
            # credentials — but never claim success without a real session.
            return request.make_json_response(
                {"error": "account_created_but_login_failed"}, status=500
            )

        # See portal_login()'s identical call for why this is required —
        # without it, session_id below is the pre-rotation value.
        request._save_session(request.env)

        return request.make_json_response(
            {
                "session_id": request.session.sid,
                "user": {
                    "id": partner.id,
                    "name": partner.name,
                    "email": partner.email,
                    "company": partner.commercial_company_name or "",
                    "phone": partner.phone or "",
                    "street": partner.street or "",
                    "city": partner.city or "",
                    "country": partner.country_id.name or "",
                },
            },
            status=201,
        )

    @http.route(
        f"{API_PREFIX}/portal/orders",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def portal_orders(self, **kwargs):
        partner = self._portal_partner()
        if not partner:
            return self._unauthorized()
        orders = (
            request.env["sale.order"]
            .sudo()
            .search([("partner_id", "=", partner.id)], order="date_order desc")
        )
        picking_has_tracking = "carrier_tracking_ref" in request.env["stock.picking"]._fields
        data = []
        for order in orders:
            tracking_number = ""
            if picking_has_tracking:
                tracking = order.picking_ids.filtered("carrier_tracking_ref")[:1]
                tracking_number = tracking.carrier_tracking_ref if tracking else ""
            data.append(
                {
                    "order_id": order.id,
                    "name": order.name,
                    "date": order.date_order.isoformat() + "Z" if order.date_order else None,
                    "amount_total": order.amount_total,
                    "state": order.state,
                    "tracking_number": tracking_number,
                }
            )
        return request.make_json_response({"data": data})

    @http.route(
        f"{API_PREFIX}/portal/profile",
        type="http",
        auth="public",
        methods=["PUT"],
        csrf=False,
    )
    def portal_profile_update(self, **kwargs):
        rejection = require_trusted_origin()
        if rejection:
            return rejection
        partner = self._portal_partner()
        if not partner:
            return self._unauthorized()
        try:
            payload = self._parsed_body()
        except ValueError:
            return self._bad_request("invalid_json")

        # Explicit allow-list translating the frontend's field names
        # (src/routes/api.portal.profile.ts's profileSchema) to res.partner
        # fields — never let an arbitrary payload key write to a field it
        # wasn't meant to (field discipline, same convention as the
        # read-side serializers in this addon).
        values = {}
        if payload.get("name"):
            values["name"] = payload["name"]
        if payload.get("email"):
            values["email"] = payload["email"]
        if payload.get("phone"):
            values["phone"] = payload["phone"]
        if payload.get("street"):
            values["street"] = payload["street"]
        if payload.get("city"):
            values["city"] = payload["city"]
        if payload.get("company"):
            values["company_name"] = payload["company"]
        if payload.get("country"):
            country = resolve_country(payload["country"])
            if not country:
                return self._bad_request("unknown_country")
            values["country_id"] = country.id
        if not values:
            return self._bad_request("no_updatable_fields")
        partner.sudo().write(values)
        return request.make_json_response({"status": "success"})
