import hashlib
import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .content_validators import (
    _validate_media,
    _validate_plain_text,
    _validate_semantic_html,
)


class VarscoCatalogCategory(models.Model):
    """Curated public catalog taxonomy, independent of ERP categories."""

    _name = "varsco.catalog.category"
    _description = "Public Catalog Category"
    _order = "sequence, id"

    slug = fields.Char(required=True, index=True)
    url_path = fields.Char(required=True, index=True)
    parent_id = fields.Many2one(
        "varsco.catalog.category", ondelete="restrict", index=True
    )
    sequence = fields.Integer(default=10)
    published = fields.Boolean(default=False)
    translation_ids = fields.One2many(
        "varsco.catalog.category.i18n", "category_id"
    )

    _slug_uniq = models.Constraint("UNIQUE (slug)", "Category slug must be unique.")
    _url_path_uniq = models.Constraint(
        "UNIQUE (url_path)", "Category URL path must be unique."
    )

    def _translation_for(self, locale):
        self.ensure_one()
        return self.translation_ids.filtered(lambda value: value.locale_id == locale)[:1]

    def _is_servable(self, locale):
        self.ensure_one()
        translation = self._translation_for(locale)
        return bool(
            self.published
            and translation
            and translation.review_status == "reviewed"
            and translation.name
            and translation.meta_title
            and translation.meta_description
        )


class VarscoCatalogCategoryI18n(models.Model):
    _name = "varsco.catalog.category.i18n"
    _description = "Public Catalog Category Translation"

    category_id = fields.Many2one(
        "varsco.catalog.category", required=True, ondelete="cascade", index=True
    )
    locale_id = fields.Many2one(
        "varsco.content.locale", required=True, ondelete="restrict"
    )
    name = fields.Char()
    summary = fields.Text()
    meta_title = fields.Char()
    meta_description = fields.Char()
    review_status = fields.Selection(
        [("ai_draft", "AI draft"), ("reviewed", "Reviewed")],
        default="ai_draft",
        required=True,
    )
    source_hash = fields.Char()

    _category_locale_uniq = models.Constraint(
        "UNIQUE (category_id, locale_id)", "One translation per locale per category."
    )

    @api.constrains("name", "summary", "meta_title", "meta_description")
    def _check_plain_text(self):
        for translation in self:
            for field_name in ("name", "summary", "meta_title", "meta_description"):
                _validate_plain_text(
                    translation[field_name], f"catalog category {field_name}"
                )


class VarscoCatalogItem(models.Model):
    """Reviewed public merchandising data with optional internal ERP links."""

    _name = "varsco.catalog.item"
    _description = "Public Catalog Item"
    _order = "sequence, id"

    slug = fields.Char(required=True, index=True)
    url_path = fields.Char(required=True, index=True)
    category_id = fields.Many2one(
        "varsco.catalog.category", required=True, ondelete="restrict", index=True
    )
    item_type = fields.Selection(
        [
            ("informational", "Informational"),
            ("purchasable_later", "Purchasable later"),
            ("purchasable_now", "Purchasable now"),
        ],
        default="informational",
        required=True,
        help=(
            "Controls storefront checkout capability. 'purchasable_now' items "
            "expose live price/stock via the public API and accept direct "
            "checkout; all other types remain quote-only (RFQ CTA, no price "
            "or stock exposed publicly)."
        ),
    )
    product_template_ids = fields.Many2many(
        "product.template",
        "varsco_catalog_item_product_template_rel",
        "catalog_item_id",
        "product_template_id",
        help="Internal commerce relationship; never exposed by the public API.",
    )
    sequence = fields.Integer(default=10)
    published = fields.Boolean(default=False)
    quote_cta_enabled = fields.Boolean(default=True)
    translation_ids = fields.One2many("varsco.catalog.item.i18n", "item_id")

    def _sellable_template(self):
        """The single product.template used for direct checkout, if any.

        Only meaningful for item_type == 'purchasable_now'; catalog items are
        otherwise a 1:1 marketing wrapper around at most one ERP product, per
        the existing convention this addon already follows elsewhere.
        """
        self.ensure_one()
        if self.item_type != "purchasable_now":
            return self.env["product.template"]
        return self.product_template_ids[:1]

    def _public_commerce_fields(self):
        """Price/stock block for the public API — empty unless purchasable_now.

        Deliberately returns only list_price (the customer-facing sale price)
        and available quantity, never standard_price/margin — those must
        never leave this method (field discipline, see products.py tests).
        """
        self.ensure_one()
        template = self._sellable_template()
        if not template:
            return None
        return {
            # Needed by the storefront to submit POST /api/v1/store/checkout
            # {product_id, qty} — the only place a raw ERP id is exposed
            # publicly, and only for items that can actually be checked out.
            "product_id": template.id,
            "amount": template.list_price,
            "currency": template.currency_id.name,
            "available": template.qty_available > 0,
            "qty_available": template.qty_available,
        }

    _url_path_uniq = models.Constraint(
        "UNIQUE (url_path)", "Catalog item URL path must be unique."
    )

    def _translation_for(self, locale):
        self.ensure_one()
        return self.translation_ids.filtered(lambda value: value.locale_id == locale)[:1]

    def _is_servable(self, locale):
        self.ensure_one()
        translation = self._translation_for(locale)
        return bool(
            self.published
            and self.category_id._is_servable(locale)
            and translation
            and translation.review_status == "reviewed"
            and translation.name
            and translation.meta_title
            and translation.meta_description
        )

    def _source_hash(self):
        self.ensure_one()
        default_locale = self.env["varsco.content.locale"].sudo().search(
            [("is_default", "=", True)], limit=1
        )
        source = self._translation_for(default_locale)
        payload = {
            "name": source.name or "",
            "eyebrow": source.eyebrow or "",
            "summary": source.summary or "",
            "description_html": source.description_html or "",
            "media": source.media or [],
            "specification_groups": source.specification_groups or [],
            "meta_title": source.meta_title or "",
            "meta_description": source.meta_description or "",
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()


class VarscoCatalogItemI18n(models.Model):
    _name = "varsco.catalog.item.i18n"
    _description = "Public Catalog Item Translation"

    item_id = fields.Many2one(
        "varsco.catalog.item", required=True, ondelete="cascade", index=True
    )
    locale_id = fields.Many2one(
        "varsco.content.locale", required=True, ondelete="restrict"
    )
    name = fields.Char()
    eyebrow = fields.Char()
    summary = fields.Text()
    description_html = fields.Text()
    media = fields.Json()
    specification_groups = fields.Json()
    meta_title = fields.Char()
    meta_description = fields.Char()
    review_status = fields.Selection(
        [("ai_draft", "AI draft"), ("reviewed", "Reviewed")],
        default="ai_draft",
        required=True,
    )
    source_hash = fields.Char()

    _item_locale_uniq = models.Constraint(
        "UNIQUE (item_id, locale_id)", "One translation per locale per catalog item."
    )

    @api.constrains(
        "name",
        "eyebrow",
        "summary",
        "description_html",
        "media",
        "specification_groups",
        "meta_title",
        "meta_description",
    )
    def _check_public_content(self):
        for translation in self:
            for field_name in (
                "name",
                "eyebrow",
                "summary",
                "meta_title",
                "meta_description",
            ):
                _validate_plain_text(
                    translation[field_name], f"catalog item {field_name}"
                )
            if translation.description_html:
                _validate_semantic_html(
                    translation.description_html, "catalog item description_html"
                )
            media = translation.media or []
            if not isinstance(media, list):
                raise ValidationError("Catalog item media must be a list.")
            for index, item_media in enumerate(media):
                _validate_media(item_media, f"catalog item media[{index}]")
            self._validate_specification_groups(
                translation.specification_groups or []
            )

    @staticmethod
    def _validate_specification_groups(groups):
        if not isinstance(groups, list):
            raise ValidationError("Specification groups must be a list.")
        for group in groups:
            if not isinstance(group, dict) or set(group) - {"heading", "items"}:
                raise ValidationError("Specification groups contain unsupported fields.")
            if group.get("heading"):
                _validate_plain_text(group["heading"], "specification group heading")
            items = group.get("items")
            if not isinstance(items, list):
                raise ValidationError("Specification groups require an items list.")
            for item in items:
                if (
                    not isinstance(item, dict)
                    or set(item) != {"label", "value"}
                    or not item.get("label")
                    or not item.get("value")
                ):
                    raise ValidationError(
                        "Specification items require label and value."
                    )
                _validate_plain_text(item["label"], "specification label")
                _validate_plain_text(item["value"], "specification value")

    def _is_stale(self):
        self.ensure_one()
        return not self.source_hash or self.source_hash != self.item_id._source_hash()
