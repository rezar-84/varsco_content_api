import json

from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import request

from .base import API_PREFIX


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
                    "country": partner.country_id.name or "",
                },
            }
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
        if payload.get("company"):
            values["company_name"] = payload["company"]
        if payload.get("country"):
            country = (
                request.env["res.country"]
                .sudo()
                .search([("name", "=", payload["country"])], limit=1)
            )
            if not country:
                return self._bad_request("unknown_country")
            values["country_id"] = country.id
        if not values:
            return self._bad_request("no_updatable_fields")
        partner.sudo().write(values)
        return request.make_json_response({"status": "success"})
