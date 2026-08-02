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
PURCHASE_KEYS = {"product_id", "amount", "currency", "available", "qty_available"}


@tagged("post_install", "-at_install", "varsco_content")
class TestShopApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["product.public.category"].create({"name": "Live Feed"})
        cls.template = cls.env["product.template"].create(
            {
                "name": "Artemia Cysts 500g",
                "list_price": 42.5,
                "standard_price": 10.0,
                "description_sale": "Premium hatching-grade artemia cysts.",
                "is_storable": True,
                "is_published": True,
                "public_categ_ids": [(6, 0, [cls.category.id])],
            }
        )
        warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.env["stock.quant"]._update_available_quantity(
            cls.template.product_variant_id, warehouse.lot_stock_id, 25
        )
        cls.unpublished = cls.env["product.template"].create(
            {"name": "Not Yet For Sale", "list_price": 10.0, "is_published": False}
        )
        cls.slug = cls.env["ir.http"]._slug(cls.template)

    def _get_json(self, path):
        response = self.url_open(path)
        return response, json.loads(response.content)

    def test_list_returns_only_published_products(self):
        response, payload = self._get_json("/api/v1/store/products/en")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["slug"] for item in payload["data"]}, {self.slug})

    def test_list_item_exposes_purchase_block_with_real_price_and_stock(self):
        _, payload = self._get_json("/api/v1/store/products/en")
        item = payload["data"][0]
        self.assertEqual(set(item["purchase"]), PURCHASE_KEYS)
        self.assertEqual(item["purchase"]["amount"], 42.5)
        self.assertEqual(item["purchase"]["product_id"], self.template.product_variant_id.id)
        self.assertTrue(item["purchase"]["available"])
        self.assertEqual(item["purchase"]["qty_available"], 25.0)

    def test_list_item_exposes_real_category(self):
        _, payload = self._get_json("/api/v1/store/products/en")
        self.assertEqual(payload["data"][0]["category"]["name"], "Live Feed")

    def test_detail_by_slug(self):
        response, payload = self._get_json(f"/api/v1/store/products/en/{self.slug}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"]["name"], "Artemia Cysts 500g")
        self.assertTrue(set(payload["data"]) <= DETAIL_KEYS)

    def test_unpublished_product_absent_from_list(self):
        _, payload = self._get_json("/api/v1/store/products/en")
        self.assertNotIn(
            self.env["ir.http"]._slug(self.unpublished),
            {item["slug"] for item in payload["data"]},
        )

    def test_unpublished_product_detail_is_404(self):
        slug = self.env["ir.http"]._slug(self.unpublished)
        response, _ = self._get_json(f"/api/v1/store/products/en/{slug}")
        self.assertEqual(response.status_code, 404)

    def test_unknown_slug_is_404(self):
        response, _ = self._get_json("/api/v1/store/products/en/does-not-exist-999999")
        self.assertEqual(response.status_code, 404)

    def test_public_fields_never_expose_cost_or_margin(self):
        _, list_payload = self._get_json("/api/v1/store/products/en")
        for item in list_payload["data"]:
            self.assertTrue(set(item) <= LIST_KEYS)
        _, detail_payload = self._get_json(f"/api/v1/store/products/en/{self.slug}")
        serialized = json.dumps(detail_payload)
        for forbidden in ("standard_price", "margin"):
            self.assertNotIn(forbidden, serialized)
