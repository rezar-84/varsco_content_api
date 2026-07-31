from odoo import http
from odoo.http import request

from .base import API_PREFIX


class VarscoContentApiProducts(http.Controller):
    """Public allow-listed catalog endpoints; ERP relationships stay private."""

    def _locale(self, code):
        return request.env["varsco.content.locale"].sudo().search(
            [("code", "=", code)], limit=1
        )

    def _base_url(self):
        config = request.env["ir.config_parameter"].sudo()
        base = config.get_param("varsco_content_api.base_url") or config.get_param(
            "web.base.url", ""
        )
        return base.rstrip("/")

    @staticmethod
    def _url_path(locale, url_path):
        return f"{locale.url_prefix or ''}/{url_path}"

    @staticmethod
    def _iso(value):
        return value.isoformat() + "Z" if value else None

    @staticmethod
    def _not_found(reason):
        return request.make_json_response({"error": reason}, status=404)

    def _published_items(self):
        return request.env["varsco.catalog.item"].sudo().search(
            [("published", "=", True)], order="sequence, id"
        )

    def _summary(self, item, locale):
        translation = item._translation_for(locale)
        category_translation = item.category_id._translation_for(locale)
        media = translation.media or []
        return {
            "slug": item.slug,
            "name": translation.name,
            "summary": translation.summary or "",
            "url_path": self._url_path(locale, item.url_path),
            "category": {
                "slug": item.category_id.slug,
                "name": category_translation.name,
                "url_path": self._url_path(locale, item.category_id.url_path),
            },
            "primary_media": media[0] if media else None,
            "updated_at": self._iso(item.write_date),
            # None for quote-only items (informational / purchasable_later) —
            # only 'purchasable_now' items ever carry price/stock, and only
            # list_price/qty_available, never standard_price/margin.
            "purchase": item._public_commerce_fields(),
        }

    def _hreflang(self, item):
        base = self._base_url()
        locales = request.env["varsco.content.locale"].sudo().search(
            [], order="sequence"
        )
        return {
            locale.code: f"{base}{self._url_path(locale, item.url_path)}"
            for locale in locales
            if item._is_servable(locale)
        }

    @http.route(
        f"{API_PREFIX}/products/<string:locale_code>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def products_list(self, locale_code, **kwargs):
        locale = self._locale(locale_code)
        if not locale:
            return self._not_found("unknown_locale")
        servable_items = self._published_items().filtered(
            lambda item: item._is_servable(locale)
        )
        data = [self._summary(item, locale) for item in servable_items]
        last_write = max((item.write_date for item in servable_items), default=None)
        return request.make_json_response(
            {
                "data": data,
                "meta": {
                    "locale": locale.code,
                    "updated_at": self._iso(last_write),
                },
            }
        )

    @http.route(
        f"{API_PREFIX}/products/<string:locale_code>/<path:url_path>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def product_detail(self, locale_code, url_path, **kwargs):
        locale = self._locale(locale_code)
        if not locale:
            return self._not_found("unknown_locale")
        item = self._published_items().filtered(
            lambda candidate: candidate.url_path == url_path
        )[:1]
        if not item or not item._is_servable(locale):
            return self._not_found("unknown_product")
        translation = item._translation_for(locale)
        data = self._summary(item, locale)
        data.update(
            {
                "eyebrow": translation.eyebrow or "",
                "description_html": translation.description_html or "",
                "media": translation.media or [],
                "specification_groups": translation.specification_groups or [],
                "quote_cta_enabled": item.quote_cta_enabled,
            }
        )
        public_path = self._url_path(locale, item.url_path)
        return request.make_json_response(
            {
                "data": data,
                "meta": {
                    "locale": locale.code,
                    "updated_at": self._iso(item.write_date),
                },
                "seo": {
                    "title": translation.meta_title,
                    "description": translation.meta_description,
                    "canonical": f"{self._base_url()}{public_path}",
                    "og": {},
                    "hreflang": self._hreflang(item),
                    "jsonld": [],
                },
            }
        )
