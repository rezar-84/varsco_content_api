import json

from odoo import http
from odoo.http import request

from .base import API_PREFIX, require_trusted_origin
from .shop import VarscoContentApiShop


class VarscoContentApiWishlist(http.Controller):
    """Wishlist — backed by website_sale_wishlist's native product.wishlist
    model (auto_install alongside website_sale, already a dependency), not
    a new custom model. Unlike the cart, the wishlist requires an account:
    there is no guest/local-only wishlist server-side — persistence is
    always tied to a real partner, matching how a wishlist is expected to
    survive across devices/sessions.

    Wishlist items are serialized through VarscoContentApiShop._summary(),
    the exact same shape as /api/v1/store/products/* — so the frontend can
    render a wishlist item with the same StoreProductCard component used
    everywhere else, no separate shape to handle.
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
    def _item_summary(wishlist_item):
        return VarscoContentApiShop()._summary(wishlist_item.product_id.product_tmpl_id)

    @http.route(
        f"{API_PREFIX}/store/wishlist",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def wishlist_list(self, **kwargs):
        partner = self._portal_partner()
        if not partner:
            return self._unauthorized()
        items = (
            request.env["product.wishlist"]
            .sudo()
            .search([("partner_id", "=", partner.id)], order="create_date desc")
        )
        # An unpublished/removed product silently disappearing from the
        # wishlist is safer than erroring the whole list over one item.
        items = items.filtered(lambda w: w.product_id.product_tmpl_id.is_published)
        return request.make_json_response({"data": [self._item_summary(i) for i in items]})

    @http.route(
        f"{API_PREFIX}/store/wishlist",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def wishlist_add(self, **kwargs):
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

        product_id = payload.get("product_id")
        if not product_id:
            return self._bad_request("product_id_required")

        variant = request.env["product.product"].sudo().browse(product_id).exists()
        if not variant or not variant.product_tmpl_id.is_published:
            return self._not_found("unknown_product")

        Wishlist = request.env["product.wishlist"].sudo()
        existing = Wishlist.search(
            [("partner_id", "=", partner.id), ("product_id", "=", variant.id)], limit=1
        )
        if existing:
            # Adding an already-wishlisted product is idempotent, not an
            # error — unlike reviews, there's no reason to reject a repeat
            # "add to wishlist" click.
            return request.make_json_response({"data": self._item_summary(existing)})

        website = request.env["website"].sudo().get_current_website()
        item = Wishlist.create(
            {"partner_id": partner.id, "product_id": variant.id, "website_id": website.id}
        )
        return request.make_json_response({"data": self._item_summary(item)}, status=201)

    @http.route(
        f"{API_PREFIX}/store/wishlist/<int:product_id>",
        type="http",
        auth="public",
        methods=["DELETE"],
        csrf=False,
    )
    def wishlist_remove(self, product_id, **kwargs):
        rejection = require_trusted_origin()
        if rejection:
            return rejection
        partner = self._portal_partner()
        if not partner:
            return self._unauthorized()

        item = (
            request.env["product.wishlist"]
            .sudo()
            .search([("partner_id", "=", partner.id), ("product_id", "=", product_id)], limit=1)
        )
        if item:
            item.unlink()
        return request.make_json_response({"status": "success"})
