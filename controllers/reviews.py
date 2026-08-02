import json

from odoo import http
from odoo.http import request

from .base import API_PREFIX, require_trusted_origin

MIN_RATING = 1
MAX_RATING = 5


class VarscoContentApiReviews(http.Controller):
    """Product reviews/ratings for /shop — backed by Odoo's native `rating`
    module (rating.mixin on product.template, already inherited via
    website_sale) rather than a new custom model. See docs/decisions.md's
    ADR on why: reviews/ratings, like the shop itself, should reuse real
    Odoo infrastructure instead of inventing a parallel one.

    Reviews require a verified purchase: the reviewing partner must have at
    least one confirmed (state == "sale") sale.order.line for a variant of
    the product, matching exactly how controllers/checkout.py creates
    orders (partner_id = the buyer directly, not a shipping/billing
    contact). One review per partner per product — Odoo's rating.rating
    model has no uniqueness constraint of its own, so it's enforced here.
    """

    @staticmethod
    def _not_found(reason):
        return request.make_json_response({"error": reason}, status=404)

    @staticmethod
    def _bad_request(reason):
        return request.make_json_response({"error": reason}, status=400)

    @staticmethod
    def _unauthorized():
        return request.make_json_response({"error": "unauthorized"}, status=401)

    @staticmethod
    def _forbidden(reason):
        return request.make_json_response({"error": reason}, status=403)

    def _portal_partner(self):
        if request.env.user._is_public():
            return None
        return request.env.user.partner_id

    @staticmethod
    def _template_from_slug(url_path):
        slug = url_path.rsplit("/", 1)[-1]
        _, template_id = request.env["ir.http"]._unslug(slug)
        if not template_id:
            return None
        template = request.env["product.template"].sudo().browse(template_id).exists()
        if not template or not template.is_published:
            return None
        return template

    @staticmethod
    def _review_summary(rating):
        return {
            "id": rating.id,
            "author_name": rating.partner_id.name or "Verified Buyer",
            "rating": rating.rating,
            "feedback": rating.feedback or "",
            "created_at": rating.create_date.isoformat() + "Z" if rating.create_date else None,
        }

    @staticmethod
    def _has_verified_purchase(partner, template):
        return bool(
            request.env["sale.order.line"]
            .sudo()
            .search_count(
                [
                    ("order_id.partner_id", "=", partner.id),
                    ("order_id.state", "=", "sale"),
                    ("product_id.product_tmpl_id", "=", template.id),
                ]
            )
        )

    @http.route(
        f"{API_PREFIX}/store/products/<string:locale_code>/<path:url_path>/reviews",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def reviews_list(self, locale_code, url_path, **kwargs):
        template = self._template_from_slug(url_path)
        if not template:
            return self._not_found("unknown_product")

        ratings = (
            request.env["rating.rating"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "product.template"),
                    ("res_id", "=", template.id),
                    ("consumed", "=", True),
                ],
                order="create_date desc",
            )
        )
        return request.make_json_response(
            {
                "data": [self._review_summary(r) for r in ratings],
                "meta": {
                    "locale": locale_code,
                    "rating_avg": round(template.rating_avg, 2) if template.rating_count else None,
                    "rating_count": template.rating_count,
                },
            }
        )

    @http.route(
        f"{API_PREFIX}/store/products/<string:locale_code>/<path:url_path>/reviews",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def reviews_submit(self, locale_code, url_path, **kwargs):
        rejection = require_trusted_origin()
        if rejection:
            return rejection
        partner = self._portal_partner()
        if not partner:
            return self._unauthorized()

        template = self._template_from_slug(url_path)
        if not template:
            return self._not_found("unknown_product")

        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            return self._bad_request("invalid_json")

        rating_value = payload.get("rating")
        if not isinstance(rating_value, (int, float)) or not (
            MIN_RATING <= rating_value <= MAX_RATING
        ):
            return self._bad_request("invalid_rating")

        feedback = (payload.get("feedback") or "").strip()

        if not self._has_verified_purchase(partner, template):
            return self._forbidden("purchase_required")

        Rating = request.env["rating.rating"].sudo()
        existing = Rating.search(
            [
                ("res_model", "=", "product.template"),
                ("res_id", "=", template.id),
                ("partner_id", "=", partner.id),
            ],
            limit=1,
        )
        if existing:
            return request.make_json_response({"error": "already_reviewed"}, status=409)

        rating = Rating.create(
            {
                "res_model_id": request.env["ir.model"].sudo()._get("product.template").id,
                "res_id": template.id,
                "partner_id": partner.id,
                "rating": rating_value,
                "feedback": feedback,
                "consumed": True,
            }
        )
        return request.make_json_response({"data": self._review_summary(rating)}, status=201)
