import json

from odoo import http
from odoo.http import request

from .base import API_PREFIX, require_trusted_origin


class VarscoContentApiCheckout(http.Controller):
    """Direct-checkout endpoint for published storefront products only.

    A product is checkout-able exactly when it's published on the website
    (product.template.is_published, from website_sale) — the same real
    Odoo product data controllers/shop.py exposes publicly. The frontend
    already hides Add to Cart for anything not published, but that's a UI
    convenience, not a security boundary, so every line is re-validated
    against is_published here too. (Previously gated on the separate
    varsco.catalog.item curated model — see docs/decisions.md's ADR on why
    that was the wrong fit for a transactional shop.)
    """

    @staticmethod
    def _bad_request(reason):
        return request.make_json_response({"error": reason}, status=400)

    @staticmethod
    def _unauthorized():
        return request.make_json_response({"error": "unauthorized"}, status=401)

    def _portal_partner(self):
        if request.env.user._is_public():
            return None
        return request.env.user.partner_id

    @staticmethod
    def _owned_by_partner(partner, candidate_id):
        """A shipping/billing target must be the buyer themselves or their
        own contact — never an arbitrary client-supplied partner id
        (security.md's ACL rule: always scope to the authenticated
        partner, never a client-supplied one)."""
        return candidate_id == partner.id or candidate_id in partner.child_ids.ids

    @http.route(
        f"{API_PREFIX}/store/checkout",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def checkout(self, **kwargs):
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

        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return self._bad_request("items_required")
        for line in items:
            if not isinstance(line, dict) or not line.get("product_id") or not line.get("qty"):
                return self._bad_request("invalid_line_item")
            if not isinstance(line["qty"], (int, float)) or line["qty"] <= 0:
                return self._bad_request("invalid_quantity")

        Product = request.env["product.product"].sudo()
        order_lines = []
        for line in items:
            product = Product.search(
                [("id", "=", line["product_id"])], limit=1
            ) or Product.search(
                [("product_tmpl_id", "=", line["product_id"])], limit=1
            )
            if not product or not product.product_tmpl_id.is_published:
                return self._bad_request(f"product_not_purchasable:{line['product_id']}")
            # Mirrors shop.py's _summary() availability logic: a backorderable
            # product (allow_out_of_stock_order) stays purchasable at zero
            # stock — the frontend shows it as available/enables Add to Cart
            # on that same basis, so rejecting it here would break checkout
            # for exactly the products this flag exists to support.
            if (
                product.qty_available < line["qty"]
                and not product.product_tmpl_id.allow_out_of_stock_order
            ):
                return self._bad_request(f"insufficient_stock:{line['product_id']}")
            order_lines.append((0, 0, {"product_id": product.id, "product_uom_qty": line["qty"]}))

        shipping_partner_id = payload.get("shipping_partner_id") or partner.id
        billing_partner_id = payload.get("billing_partner_id") or partner.id
        if not self._owned_by_partner(partner, shipping_partner_id):
            return self._bad_request("invalid_shipping_partner_id")
        if not self._owned_by_partner(partner, billing_partner_id):
            return self._bad_request("invalid_billing_partner_id")

        order = (
            request.env["sale.order"]
            .sudo()
            .create(
                {
                    "partner_id": partner.id,
                    "partner_shipping_id": shipping_partner_id,
                    "partner_invoice_id": billing_partner_id,
                    "order_line": order_lines,
                }
            )
        )
        response = {
            "order_id": order.id,
            "amount_total": order.amount_total,
            "currency": order.currency_id.name,
        }
        # Delegates entirely to midvex_sale_payment_link: no provider/payment
        # logic lives in this module. None means no compatible payment
        # provider is configured — the field is simply omitted, and the
        # frontend falls back to its non-payment "order submitted" state.
        payment_url = order.get_payment_portal_url()
        if payment_url:
            response["payment_url"] = payment_url
        return request.make_json_response(response)
