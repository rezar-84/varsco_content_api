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

    def _media_list(self, template):
        """Real multi-image gallery: the main template image first, then
        website_sale's product_template_image_ids (its own extra-photos
        mechanism) in order. Previously only image_1920 was ever exposed,
        capping every shop product at a single image regardless of how many
        photos the Odoo record actually had."""
        items = []
        if template.image_1920:
            items.append(
                {"url": self._image_url("product.template", template.id), "alt": template.name}
            )
        items.extend(
            {"url": self._image_url("product.image", img.id), "alt": img.name or template.name}
            for img in template.product_template_image_ids
            if img.image_1920
        )
        return items

    def _specification_groups(self, template):
        """Real attribute data (size/weight/packaging variants etc.) instead
        of the previous hardcoded []. One group is enough for now — richer
        multi-group layouts aren't something attribute_line_ids models."""
        items = [
            {"label": line.attribute_id.name, "value": ", ".join(line.value_ids.mapped("name"))}
            for line in template.attribute_line_ids
            if line.value_ids
        ]
        return [{"heading": "Specifications", "items": items}] if items else []

    def _summary(self, template):
        slug = request.env["ir.http"]._slug(template)
        category = template.public_categ_ids[:1]
        variant = template.product_variant_id
        media = self._media_list(template)
        return {
            "slug": slug,
            "name": template.name,
            "summary": template.description_sale or "",
            "url_path": f"/shop/{slug}",
            "category": self._category_summary(category),
            "primary_media": media[0] if media else None,
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
                "media": self._media_list(template),
                "specification_groups": self._specification_groups(template),
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
