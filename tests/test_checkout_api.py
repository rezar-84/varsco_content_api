import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "varsco_content")
class TestCheckoutApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = "Test1234!"
        cls.partner = cls.env["res.partner"].create(
            {"name": "Checkout Buyer", "email": "checkout.buyer@example.com"}
        )
        cls.child_contact = cls.env["res.partner"].create(
            {
                "name": "Checkout Buyer — Warehouse",
                "parent_id": cls.partner.id,
                "type": "delivery",
            }
        )
        cls.stranger = cls.env["res.partner"].create(
            {"name": "Unrelated Customer", "email": "stranger@example.com"}
        )
        cls.env["res.users"].create(
            {
                "name": "Checkout Buyer",
                "login": "checkout.buyer@example.com",
                "password": cls.password,
                "partner_id": cls.partner.id,
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )

        category = cls.env["varsco.catalog.category"].create(
            {"slug": "checkout-cat", "url_path": "products/checkout-cat", "published": True}
        )
        cls.template = cls.env["product.template"].create(
            {
                "name": "Artemia Cysts 500g",
                "list_price": 42.5,
                "standard_price": 10.0,
                "is_storable": True,
            }
        )
        cls.env["varsco.catalog.item"].create(
            {
                "slug": "artemia-cysts",
                "url_path": "products/checkout-cat/artemia-cysts",
                "category_id": category.id,
                "published": True,
                "item_type": "purchasable_now",
                "product_template_ids": [(6, 0, [cls.template.id])],
            }
        )
        cls.product = cls.template.product_variant_id
        warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, warehouse.lot_stock_id, 10
        )

    def _checkout(self, **payload_overrides):
        payload = {"items": [{"product_id": self.product.id, "qty": 1}]}
        payload.update(payload_overrides)
        return self.url_open(
            "/api/v1/store/checkout",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )

    def test_checkout_requires_authentication(self):
        response = self._checkout()
        self.assertEqual(response.status_code, 401)

    def test_checkout_defaults_to_own_partner(self):
        self.authenticate("checkout.buyer@example.com", self.password)
        response = self._checkout()
        self.assertEqual(response.status_code, 200)
        order_id = json.loads(response.content)["order_id"]
        order = self.env["sale.order"].browse(order_id)
        self.assertEqual(order.partner_shipping_id, self.partner)
        self.assertEqual(order.partner_invoice_id, self.partner)

    def test_checkout_allows_own_child_contact_as_shipping(self):
        self.authenticate("checkout.buyer@example.com", self.password)
        response = self._checkout(shipping_partner_id=self.child_contact.id)
        self.assertEqual(response.status_code, 200)

    def test_checkout_rejects_shipping_partner_not_owned_by_buyer(self):
        self.authenticate("checkout.buyer@example.com", self.password)
        response = self._checkout(shipping_partner_id=self.stranger.id)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.env["sale.order"].search_count([("partner_id", "=", self.partner.id)]), 0)

    def test_checkout_rejects_billing_partner_not_owned_by_buyer(self):
        self.authenticate("checkout.buyer@example.com", self.password)
        response = self._checkout(billing_partner_id=self.stranger.id)
        self.assertEqual(response.status_code, 400)
