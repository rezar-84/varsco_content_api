from odoo import http
from odoo.http import request

from .base import API_PREFIX


class VarscoContentApiShop(http.Controller):
    """Public transactional storefront — backed by real Odoo product data
    (product.template + website_sale's is_published/public_categ_ids), NOT
    the curated varsco.catalog.item model products.py uses for the separate
    informational /products portfolio. See docs/decisions.md's ADR on why:
    a transactional shop should reuse real Odoo product data (toggle
    "Published", it shows up) rather than require re-entering every product
    a second time in a custom model.

    Locale handling is intentionally simple for now: every locale reads the
    same (environment-default-language) field values — no per-locale
    translation-context switching yet. Odoo's own translatable fields
    (name, description_sale) still return sane values regardless; this is a
    known simplification, not a bug, and can be revisited if serving each
    locale's own translated product copy becomes a real requirement.
    """

    @staticmethod
    def _not_found(reason):
        return request.make_json_response({"error": reason}, status=404)

    @staticmethod
    def _iso(value):
        return value.isoformat() + "Z" if value else None

    @staticmethod
    def _image_url(model, record_id, field="image_1024"):
        return f"/web/image/{model}/{record_id}/{field}"

    def _published_templates(self):
        return request.env["product.template"].sudo().search([("is_published", "=", True)])

    def _category_summary(self, category):
        if not category:
            return None
        slug = request.env["ir.http"]._slug(category)
        return {
            "slug": slug,
            "name": category.name,
            "url_path": f"/shop/category/{slug}",
        }

    def _summary(self, template):
        slug = request.env["ir.http"]._slug(template)
        category = template.public_categ_ids[:1]
        variant = template.product_variant_id
        return {
            "slug": slug,
            "name": template.name,
            "summary": template.description_sale or "",
            "url_path": f"/shop/{slug}",
            "category": self._category_summary(category),
            "primary_media": (
                {"url": self._image_url("product.template", template.id), "alt": template.name}
                if template.image_1920
                else None
            ),
            "updated_at": self._iso(template.write_date),
            "purchase": {
                "product_id": variant.id,
                "amount": template.list_price,
                "currency": template.currency_id.name,
                "available": template.qty_available > 0,
                "qty_available": template.qty_available,
            },
        }

    @http.route(
        f"{API_PREFIX}/store/products/<string:locale_code>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def shop_products_list(self, locale_code, **kwargs):
        templates = self._published_templates()
        data = [self._summary(template) for template in templates]
        last_write = max((template.write_date for template in templates), default=None)
        return request.make_json_response(
            {
                "data": data,
                "meta": {"locale": locale_code, "updated_at": self._iso(last_write)},
            }
        )

    @http.route(
        f"{API_PREFIX}/store/products/<string:locale_code>/<path:url_path>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def shop_product_detail(self, locale_code, url_path, **kwargs):
        slug = url_path.rsplit("/", 1)[-1]
        _, template_id = request.env["ir.http"]._unslug(slug)
        if not template_id:
            return self._not_found("unknown_product")

        template = request.env["product.template"].sudo().browse(template_id).exists()
        if not template or not template.is_published:
            return self._not_found("unknown_product")

        data = self._summary(template)
        category = template.public_categ_ids[:1]
        data.update(
            {
                "eyebrow": category.name or "",
                "description_html": (
                    f"<p>{template.description_sale}</p>" if template.description_sale else ""
                ),
                "media": (
                    [{"url": self._image_url("product.template", template.id), "alt": template.name}]
                    if template.image_1920
                    else []
                ),
                # Mapping product attributes (size/weight/packaging variants)
                # into spec rows is real work, deliberately deferred to the
                # tracked "Attributes & variations" follow-up, not half-built
                # here.
                "specification_groups": [],
                "quote_cta_enabled": True,
            }
        )
        return request.make_json_response(
            {
                "data": data,
                "meta": {"locale": locale_code, "updated_at": self._iso(template.write_date)},
                "seo": {
                    "title": template.name,
                    "description": template.description_sale or "",
                    "canonical": "",
                    "og": {},
                    "hreflang": {},
                    "jsonld": [],
                },
            }
        )
