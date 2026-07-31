import json

from odoo.tests import HttpCase, tagged

LIST_KEYS = {
    "slug",
    "name",
    "summary",
    "url_path",
    "category",
    "primary_media",
    "updated_at",
    "purchase",
}
DETAIL_KEYS = LIST_KEYS | {
    "eyebrow",
    "description_html",
    "media",
    "specification_groups",
    "quote_cta_enabled",
}
CATEGORY_KEYS = {"slug", "name", "url_path"}
PURCHASE_KEYS = {"product_id", "amount", "currency", "available", "qty_available"}


@tagged("post_install", "-at_install", "varsco_content")
class TestProductsApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.locale_en = cls.env.ref("varsco_content_api.locale_en")
        cls.locale_tr = cls.env.ref("varsco_content_api.locale_tr")
        category = cls.env["varsco.catalog.category"].create(
            {"slug": "seafood", "url_path": "products/seafood", "published": True}
        )
        CategoryI18n = cls.env["varsco.catalog.category.i18n"]
        for locale, name in ((cls.locale_en, "Seafood"), (cls.locale_tr, "Deniz Ürünleri")):
            CategoryI18n.create(
                {
                    "category_id": category.id,
                    "locale_id": locale.id,
                    "name": name,
                    "meta_title": f"{name} | VARS",
                    "meta_description": f"{name} catalog.",
                    "review_status": "reviewed",
                }
            )
        cls.item = cls.env["varsco.catalog.item"].create(
            {
                "slug": "shrimp",
                "url_path": "products/seafood/shrimp",
                "category_id": category.id,
                "published": True,
                "quote_cta_enabled": True,
            }
        )
        ItemI18n = cls.env["varsco.catalog.item.i18n"]
        for locale, name in ((cls.locale_en, "Shrimp"), (cls.locale_tr, "Karides")):
            ItemI18n.create(
                {
                    "item_id": cls.item.id,
                    "locale_id": locale.id,
                    "name": name,
                    "eyebrow": "Seafood",
                    "summary": "Curated catalog copy.",
                    "description_html": "<p>Approved description.</p>",
                    "media": [{"url": "/web/image/42", "alt": name}],
                    "specification_groups": [],
                    "meta_title": f"{name} | VARS",
                    "meta_description": f"{name} from VARS Aquaculture.",
                    "review_status": "reviewed",
                }
            )
        cls.env["varsco.catalog.item"].create(
            {
                "slug": "draft",
                "url_path": "products/seafood/draft",
                "category_id": category.id,
                "published": False,
            }
        )

        cls.template = cls.env["product.template"].create(
            {"name": "Artemia Cysts 500g", "list_price": 42.5, "standard_price": 10.0}
        )
        cls.direct_item = cls.env["varsco.catalog.item"].create(
            {
                "slug": "artemia-cysts",
                "url_path": "products/live-feed/artemia-cysts",
                "category_id": category.id,
                "published": True,
                "item_type": "purchasable_now",
                "product_template_ids": [(6, 0, [cls.template.id])],
            }
        )
        for locale, name in ((cls.locale_en, "Artemia Cysts"), (cls.locale_tr, "Artemia Kistleri")):
            ItemI18n.create(
                {
                    "item_id": cls.direct_item.id,
                    "locale_id": locale.id,
                    "name": name,
                    "eyebrow": "Live Feed",
                    "summary": "Direct-checkout live feed.",
                    "description_html": "<p>Approved description.</p>",
                    "media": [],
                    "specification_groups": [],
                    "meta_title": f"{name} | VARS",
                    "meta_description": f"{name} from VARS Aquaculture.",
                    "review_status": "reviewed",
                }
            )

    def _get_json(self, path):
        response = self.url_open(path)
        return response, json.loads(response.content)

    def test_list_returns_only_servable_curated_items(self):
        response, payload = self._get_json("/api/v1/products/en")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["slug"] for item in payload["data"]}, {"shrimp", "artemia-cysts"}
        )
        self.assertEqual(payload["data"][0]["category"]["name"], "Seafood")

    def test_quote_only_item_exposes_no_purchase_block(self):
        _, payload = self._get_json("/api/v1/products/en/products/seafood/shrimp")
        self.assertIsNone(payload["data"]["purchase"])

    def test_purchasable_now_item_exposes_price_and_stock_only(self):
        response, payload = self._get_json(
            "/api/v1/products/en/products/live-feed/artemia-cysts"
        )
        self.assertEqual(response.status_code, 200)
        purchase = payload["data"]["purchase"]
        self.assertEqual(set(purchase), PURCHASE_KEYS)
        self.assertEqual(purchase["product_id"], self.template.id)
        self.assertEqual(purchase["amount"], 42.5)
        serialized = json.dumps(payload)
        for forbidden in ("standard_price", "margin", "product_template_ids"):
            self.assertNotIn(forbidden, serialized)

    def test_detail_supports_nested_catalog_path_and_seo(self):
        response, payload = self._get_json("/api/v1/products/en/products/seafood/shrimp")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"]["name"], "Shrimp")
        self.assertEqual(payload["data"]["specification_groups"], [])
        self.assertTrue(payload["seo"]["canonical"].endswith("/products/seafood/shrimp"))
        self.assertIn("tr", payload["seo"]["hreflang"])

    def test_detail_localizes_public_url(self):
        _, payload = self._get_json("/api/v1/products/tr/products/seafood/shrimp")
        self.assertEqual(payload["data"]["name"], "Karides")
        self.assertEqual(payload["data"]["url_path"], "/tr/products/seafood/shrimp")

    def test_unknown_or_unpublished_item_is_404(self):
        response, _ = self._get_json("/api/v1/products/en/products/seafood/draft")
        self.assertEqual(response.status_code, 404)

    def test_public_fields_never_expose_erp_relationships(self):
        _, list_payload = self._get_json("/api/v1/products/en")
        for item in list_payload["data"]:
            self.assertTrue(set(item) <= LIST_KEYS)
            self.assertTrue(set(item["category"]) <= CATEGORY_KEYS)
        _, detail_payload = self._get_json("/api/v1/products/en/products/seafood/shrimp")
        self.assertTrue(set(detail_payload["data"]) <= DETAIL_KEYS)
        serialized = json.dumps(detail_payload)
        for forbidden in ("product_template_ids", "standard_price", "list_price", "margin"):
            self.assertNotIn(forbidden, serialized)

