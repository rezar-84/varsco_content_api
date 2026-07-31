from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("varsco_content")
class TestCatalog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.locale_en = cls.env.ref("varsco_content_api.locale_en")
        cls.locale_tr = cls.env.ref("varsco_content_api.locale_tr")

    def _category(self, **values):
        return self.env["varsco.catalog.category"].create(
            {
                "slug": "seafood",
                "url_path": "products/seafood",
                "published": True,
                **values,
            }
        )

    def _category_translation(self, category, locale=None, **values):
        return self.env["varsco.catalog.category.i18n"].create(
            {
                "category_id": category.id,
                "locale_id": (locale or self.locale_en).id,
                "name": "Seafood",
                "meta_title": "Seafood | VARS",
                "meta_description": "Seafood catalog.",
                "review_status": "reviewed",
                **values,
            }
        )

    def _item(self, category, **values):
        return self.env["varsco.catalog.item"].create(
            {
                "slug": "shrimp",
                "url_path": "products/seafood/shrimp",
                "category_id": category.id,
                "published": True,
                **values,
            }
        )

    def _item_translation(self, item, locale=None, **values):
        return self.env["varsco.catalog.item.i18n"].create(
            {
                "item_id": item.id,
                "locale_id": (locale or self.locale_en).id,
                "name": "Shrimp",
                "summary": "Curated seafood portfolio entry.",
                "description_html": "<p>Handled with <strong>care</strong>.</p>",
                "media": [{"url": "/web/image/42", "alt": "Fresh shrimp"}],
                "specification_groups": [
                    {
                        "heading": "Composition",
                        "items": [{"label": "Protein", "value": "48%"}],
                    }
                ],
                "meta_title": "Shrimp | VARS",
                "meta_description": "Shrimp from VARS Aquaculture.",
                "review_status": "reviewed",
                **values,
            }
        )

    def test_reviewed_category_and_item_are_servable(self):
        category = self._category()
        self._category_translation(category)
        item = self._item(category)
        self._item_translation(item)
        self.assertTrue(category._is_servable(self.locale_en))
        self.assertTrue(item._is_servable(self.locale_en))

    def test_item_requires_reviewed_category_and_translation(self):
        category = self._category()
        self._category_translation(category, review_status="ai_draft")
        item = self._item(category)
        self._item_translation(item)
        self.assertFalse(item._is_servable(self.locale_en))
        self.assertFalse(item._is_servable(self.locale_tr))

    @mute_logger("odoo.sql_db")
    def test_item_url_path_is_unique(self):
        category = self._category()
        self._item(category)
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self._item(category, slug="second")

    def test_item_can_link_products_without_copying_business_data(self):
        category = self._category()
        product = self.env["product.template"].create({"name": "ERP Shrimp"})
        item = self._item(category, product_template_ids=[(4, product.id)])
        self.assertEqual(item.product_template_ids, product)

    def test_description_rejects_layout_html(self):
        category = self._category()
        item = self._item(category)
        with self.assertRaises(ValidationError):
            self._item_translation(
                item,
                description_html='<section class="s_banner"><p>Copy</p></section>',
            )

    def test_media_requires_url_and_alt(self):
        category = self._category()
        item = self._item(category)
        with self.assertRaises(ValidationError):
            self._item_translation(item, media=[{"url": "/web/image/42"}])

    def test_specifications_require_label_value_pairs(self):
        category = self._category()
        item = self._item(category)
        with self.assertRaises(ValidationError):
            self._item_translation(
                item,
                specification_groups=[{"items": [{"label": "Protein"}]}],
            )
