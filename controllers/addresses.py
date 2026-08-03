import json

import psycopg2

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from .base import API_PREFIX, require_trusted_origin, resolve_country

ADDRESS_TYPES = ("invoice", "delivery")
WRITABLE_FIELDS = ("name", "street", "street2", "city", "zip", "phone")


class VarscoContentApiAddresses(http.Controller):
    """Address book — extra shipping/billing contacts a customer can save
    and pick between at checkout, backed by plain res.partner child
    contacts (type in 'invoice'/'delivery'), the same native model
    checkout.py already validates shipping_partner_id/billing_partner_id
    ownership against. This module never manages the buyer's own partner
    record here — that's the profile endpoint's job (portal.py); this is
    strictly the *additional* addresses a buyer can add beyond themselves.
    """

    @staticmethod
    def _unauthorized():
        return request.make_json_response({"error": "unauthorized"}, status=401)

    @staticmethod
    def _not_found(reason):
        return request.make_json_response({"error": reason}, status=404)

    @staticmethod
    def _bad_request(reason):
        return request.make_json_response({"error": reason}, status=400)

    def _portal_partner(self):
        if request.env.user._is_public():
            return None
        return request.env.user.partner_id

    @staticmethod
    def _summary(address):
        return {
            "id": address.id,
            "type": address.type,
            "name": address.name or "",
            "street": address.street or "",
            "street2": address.street2 or "",
            "city": address.city or "",
            "zip": address.zip or "",
            "state": address.state_id.name or "",
            "country": address.country_id.name or "",
            "phone": address.phone or "",
        }

    def _owned_address(self, partner, address_id):
        return (
            request.env["res.partner"]
            .sudo()
            .search(
                [
                    ("id", "=", address_id),
                    ("parent_id", "=", partner.id),
                    ("type", "in", list(ADDRESS_TYPES)),
                ],
                limit=1,
            )
        )

    @http.route(
        f"{API_PREFIX}/store/addresses",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def address_list(self, **kwargs):
        partner = self._portal_partner()
        if not partner:
            return self._unauthorized()
        addresses = (
            request.env["res.partner"]
            .sudo()
            .search(
                [("parent_id", "=", partner.id), ("type", "in", list(ADDRESS_TYPES))],
                order="create_date desc",
            )
        )
        return request.make_json_response({"data": [self._summary(a) for a in addresses]})

    @http.route(
        f"{API_PREFIX}/store/addresses",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def address_create(self, **kwargs):
        rejection = require_trusted_origin()
        if rejection:
            return rejection
        partner = self._portal_partner()
        if not partner:
            return self._unauthorized()

        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            return self._bad_request("invalid_json")

        address_type = payload.get("type")
        if address_type not in ADDRESS_TYPES:
            return self._bad_request("invalid_type")
        if not payload.get("name") or not payload.get("street") or not payload.get("city"):
            return self._bad_request("missing_required_fields")
        if not payload.get("country"):
            return self._bad_request("country_required")
        country = resolve_country(payload["country"])
        if not country:
            return self._bad_request("unknown_country")

        values = {
            key: payload[key] for key in WRITABLE_FIELDS if payload.get(key) is not None
        }
        values.update({"type": address_type, "parent_id": partner.id, "country_id": country.id})
        address = request.env["res.partner"].sudo().create(values)
        return request.make_json_response({"data": self._summary(address)}, status=201)

    @http.route(
        f"{API_PREFIX}/store/addresses/<int:address_id>",
        type="http",
        auth="public",
        methods=["PUT"],
        csrf=False,
    )
    def address_update(self, address_id, **kwargs):
        rejection = require_trusted_origin()
        if rejection:
            return rejection
        partner = self._portal_partner()
        if not partner:
            return self._unauthorized()

        address = self._owned_address(partner, address_id)
        if not address:
            return self._not_found("address_not_found")

        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            return self._bad_request("invalid_json")

        values = {
            key: payload[key] for key in WRITABLE_FIELDS if payload.get(key) is not None
        }
        if payload.get("type"):
            if payload["type"] not in ADDRESS_TYPES:
                return self._bad_request("invalid_type")
            values["type"] = payload["type"]
        if payload.get("country"):
            country = resolve_country(payload["country"])
            if not country:
                return self._bad_request("unknown_country")
            values["country_id"] = country.id

        address.write(values)
        return request.make_json_response({"data": self._summary(address)})

    @http.route(
        f"{API_PREFIX}/store/addresses/<int:address_id>",
        type="http",
        auth="public",
        methods=["DELETE"],
        csrf=False,
    )
    def address_delete(self, address_id, **kwargs):
        rejection = require_trusted_origin()
        if rejection:
            return rejection
        partner = self._portal_partner()
        if not partner:
            return self._unauthorized()

        address = self._owned_address(partner, address_id)
        if not address:
            return self._not_found("address_not_found")

        try:
            # unlink()'s DELETE FROM res_partner runs as raw SQL, so a FK
            # violation (address still referenced as a sale order's
            # shipping/billing partner) surfaces as a bare
            # psycopg2.errors.ForeignKeyViolation, not a UserError — Odoo
            # only translates it to a friendly UserError message much
            # higher up the dispatch stack, past where we can catch it.
            # The savepoint keeps the aborted DELETE from poisoning the
            # rest of this request's transaction.
            with request.env.cr.savepoint():
                address.unlink()
        except (UserError, ValidationError, psycopg2.IntegrityError):
            # Already referenced by a confirmed sale order's
            # shipping/billing partner — same "can't hard-delete
            # referenced records" constraint documented elsewhere for
            # catalog items; the address stays usable for existing
            # orders, it just can't be removed from the book.
            return request.make_json_response({"error": "address_in_use"}, status=409)
        return request.make_json_response({"status": "success"})
