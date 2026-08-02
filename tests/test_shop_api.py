import json

from odoo.fields import Command
from odoo.tests import HttpCase, tagged

# Real 1x1 red PNG, for product.image test fixtures (image.mixin fields
# validate/process real image data, a fake byte string won't pass).
_TEST_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)

LIST_KEYS = {
    "slug",
    "name",
    "summary",
    "url_path",
    "category",
    "primary_media",
    "updated_at",
    "rating_avg",
    "rating_count",
    "ribbon",
    "tags",
    "purchase",
}
DETAIL_KEYS = LIST_KEYS | {
    "eyebrow",
    "description_html",
    "media",
    "specification_groups",
    "quote_cta_enabled",
    "alternative_products",
    "accessory_products",
    "optional_products",
}
PURCHASE_KEYS = {
    "product_id",
    "amount",
    "currency",
    "available",
    "qty_available",
    "sell_when_out_of_stock",
    "show_qty",
    "out_of_stock_message",
}


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

    def test_detail_exposes_real_multi_image_gallery_and_specs(self):
        attribute = self.env["product.attribute"].create(
            {
                "name": "Pack Size",
                "value_ids": [
                    Command.create({"name": "500g"}),
                    Command.create({"name": "1kg"}),
                ],
            }
        )
        template = self.env["product.template"].create(
            {
                "name": "Gallery Test Product",
                "list_price": 15.0,
                "is_published": True,
                "image_1920": _TEST_PNG,
                "product_template_image_ids": [
                    Command.create({"name": "Angle 2", "image_1920": _TEST_PNG}),
                    Command.create({"name": "Angle 3", "image_1920": _TEST_PNG}),
                ],
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": attribute.id,
                            "value_ids": [Command.set(attribute.value_ids.ids)],
                        }
                    )
                ],
            }
        )
        slug = self.env["ir.http"]._slug(template)

        _, payload = self._get_json(f"/api/v1/store/products/en/{slug}")
        data = payload["data"]

        # Main template image + both extra product_template_image_ids entries.
        self.assertEqual(len(data["media"]), 3)
        self.assertEqual(data["primary_media"], data["media"][0])

        self.assertEqual(len(data["specification_groups"]), 1)
        group = data["specification_groups"][0]
        self.assertEqual(group["items"], [{"label": "Pack Size", "value": "500g, 1kg"}])

    def test_description_prefers_ecommerce_over_sale_description(self):
        template = self.env["product.template"].create(
            {
                "name": "Description Source Test",
                "list_price": 5.0,
                "is_published": True,
                "description_sale": "Quotation blurb, should not be used.",
                "description_ecommerce": "<p>Real storefront copy.</p>",
            }
        )
        slug = self.env["ir.http"]._slug(template)
        _, payload = self._get_json(f"/api/v1/store/products/en/{slug}")
        self.assertEqual(payload["data"]["summary"], "Real storefront copy.")
        self.assertIn("Real storefront copy.", payload["data"]["description_html"])
        self.assertNotIn("Quotation blurb", payload["data"]["summary"])

    def test_description_falls_back_to_sale_description_when_ecommerce_empty(self):
        template = self.env["product.template"].create(
            {
                "name": "Description Fallback Test",
                "list_price": 5.0,
                "is_published": True,
                "description_sale": "Only the quotation blurb exists.",
            }
        )
        slug = self.env["ir.http"]._slug(template)
        _, payload = self._get_json(f"/api/v1/store/products/en/{slug}")
        self.assertEqual(payload["data"]["summary"], "Only the quotation blurb exists.")

    def test_ribbon_and_tags_exposed(self):
        ribbon = self.env["product.ribbon"].create(
            {"name": "New!", "bg_color": "#00FF00", "text_color": "#000000"}
        )
        tag = self.env["product.tag"].create({"name": "Best Seller"})
        template = self.env["product.template"].create(
            {
                "name": "Ribbon Tag Test",
                "list_price": 5.0,
                "is_published": True,
                "website_ribbon_id": ribbon.id,
                "product_tag_ids": [Command.set([tag.id])],
            }
        )
        slug = self.env["ir.http"]._slug(template)
        _, payload = self._get_json(f"/api/v1/store/products/en/{slug}")
        self.assertEqual(payload["data"]["ribbon"]["name"], "New!")
        self.assertEqual(payload["data"]["ribbon"]["bg_color"], "#00FF00")
        self.assertEqual(payload["data"]["tags"], ["Best Seller"])

    def test_no_ribbon_is_null_not_missing(self):
        _, payload = self._get_json(f"/api/v1/store/products/en/{self.slug}")
        self.assertIsNone(payload["data"]["ribbon"])
        self.assertEqual(payload["data"]["tags"], [])

    def test_sell_when_out_of_stock_makes_zero_stock_item_available(self):
        template = self.env["product.template"].create(
            {
                "name": "Backorderable Test",
                "list_price": 5.0,
                "is_published": True,
                "is_storable": True,
                "allow_out_of_stock_order": True,
            }
        )
        slug = self.env["ir.http"]._slug(template)
        _, payload = self._get_json(f"/api/v1/store/products/en/{slug}")
        purchase = payload["data"]["purchase"]
        self.assertEqual(purchase["qty_available"], 0)
        self.assertTrue(purchase["available"])
        self.assertTrue(purchase["sell_when_out_of_stock"])

    def test_alternative_accessory_optional_products_exposed(self):
        alt = self.env["product.template"].create(
            {"name": "Alt Product", "list_price": 5.0, "is_published": True}
        )
        accessory = self.env["product.template"].create(
            {"name": "Accessory Product", "list_price": 5.0, "is_published": True}
        )
        optional = self.env["product.template"].create(
            {"name": "Optional Product", "list_price": 5.0, "is_published": True}
        )
        unpublished_alt = self.env["product.template"].create(
            {"name": "Unpublished Alt", "list_price": 5.0, "is_published": False}
        )
        template = self.env["product.template"].create(
            {
                "name": "Cross-Sell Host Product",
                "list_price": 5.0,
                "is_published": True,
                "alternative_product_ids": [Command.set([alt.id, unpublished_alt.id])],
                "accessory_product_ids": [
                    Command.set([accessory.product_variant_id.id])
                ],
                "optional_product_ids": [Command.set([optional.id])],
            }
        )
        slug = self.env["ir.http"]._slug(template)
        _, payload = self._get_json(f"/api/v1/store/products/en/{slug}")
        data = payload["data"]

        self.assertEqual([p["name"] for p in data["alternative_products"]], ["Alt Product"])
        self.assertEqual([p["name"] for p in data["accessory_products"]], ["Accessory Product"])
        self.assertEqual([p["name"] for p in data["optional_products"]], ["Optional Product"])

    def test_list_orders_by_website_sequence(self):
        self.env["product.template"].create(
            {"name": "Sequence First", "list_price": 5.0, "is_published": True, "website_sequence": 1}
        )
        self.env["product.template"].create(
            {"name": "Sequence Second", "list_price": 5.0, "is_published": True, "website_sequence": 2}
        )
        _, payload = self._get_json("/api/v1/store/products/en")
        names = [item["name"] for item in payload["data"]]
        self.assertLess(names.index("Sequence First"), names.index("Sequence Second"))

    def test_list_media_ignores_extra_images_without_actual_image_data(self):
        template = self.env["product.template"].create(
            {
                "name": "No Real Gallery Product",
                "list_price": 5.0,
                "is_published": True,
                "image_1920": _TEST_PNG,
                # A row with no image_1920 set shouldn't produce a broken
                # media entry pointing at a record with no picture.
                "product_template_image_ids": [Command.create({"name": "Placeholder"})],
            }
        )
        slug = self.env["ir.http"]._slug(template)
        _, payload = self._get_json(f"/api/v1/store/products/en/{slug}")
        self.assertEqual(len(payload["data"]["media"]), 1)
