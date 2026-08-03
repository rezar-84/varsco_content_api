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

        # Checkout-ability is gated purely on is_published (website_sale) --
        # no separate curation model. See docs/decisions.md's ADR on why the
        # earlier varsco.catalog.item-based gate was replaced.
        cls.template = cls.env["product.template"].create(
            {
                "name": "Artemia Cysts 500g",
                "list_price": 42.5,
                "standard_price": 10.0,
                "is_storable": True,
                "is_published": True,
            }
        )
        cls.product = cls.template.product_variant_id
        warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, warehouse.lot_stock_id, 10
        )

    def _checkout(self, headers=None, **payload_overrides):
        payload = {"items": [{"product_id": self.product.id, "qty": 1}]}
        payload.update(payload_overrides)
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        return self.url_open(
            "/api/v1/store/checkout",
            data=json.dumps(payload).encode(),
            headers=request_headers,
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

    def test_checkout_rejects_cross_origin_request(self):
        """A form/fetch-based CSRF from an unrelated site must not be able
        to place a real sale.order using a genuine erp.varsco.com session
        cookie (docs/security.md §3)."""
        self.authenticate("checkout.buyer@example.com", self.password)
        response = self._checkout(headers={"Origin": "https://evil.example.com"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.env["sale.order"].search_count([("partner_id", "=", self.partner.id)]), 0)

    def test_checkout_allows_configured_frontend_origin(self):
        self.authenticate("checkout.buyer@example.com", self.password)
        response = self._checkout(headers={"Origin": "https://varsco.com"})
        self.assertEqual(response.status_code, 200)

    def test_checkout_rejects_unpublished_product(self):
        unpublished = self.env["product.template"].create(
            {"name": "Not For Sale Yet", "list_price": 10.0, "is_published": False}
        )
        self.authenticate("checkout.buyer@example.com", self.password)
        response = self._checkout(
            items=[{"product_id": unpublished.product_variant_id.id, "qty": 1}]
        )
        self.assertEqual(response.status_code, 400)

    def test_checkout_rejects_insufficient_stock(self):
        # allow_out_of_stock_order defaults True on product.template (see
        # website_sale_stock), so this must be a dedicated non-backorderable
        # product rather than the shared self.product fixture, or the
        # backorder exemption added for the sibling test below would mask
        # the very check this test exists to exercise.
        limited = self.env["product.template"].create(
            {
                "name": "Limited Stock Product",
                "list_price": 10.0,
                "is_storable": True,
                "is_published": True,
                "allow_out_of_stock_order": False,
            }
        )
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        self.env["stock.quant"]._update_available_quantity(
            limited.product_variant_id, warehouse.lot_stock_id, 2
        )
        self.authenticate("checkout.buyer@example.com", self.password)
        response = self._checkout(
            items=[{"product_id": limited.product_variant_id.id, "qty": 999}]
        )
        self.assertEqual(response.status_code, 400)

    def test_checkout_allows_backorderable_product_despite_zero_stock(self):
        """Mirrors shop.py's _summary() availability logic (qty_available > 0
        OR sell_when_out_of_stock) — the frontend shows a backorderable
        product as available/enables Add to Cart on that same basis, so
        checkout must accept it too, not just the read-side API."""
        backorderable = self.env["product.template"].create(
            {
                "name": "Backorderable Product",
                "list_price": 10.0,
                "is_storable": True,
                "is_published": True,
                "allow_out_of_stock_order": True,
            }
        )
        self.authenticate("checkout.buyer@example.com", self.password)
        response = self._checkout(
            items=[{"product_id": backorderable.product_variant_id.id, "qty": 5}]
        )
        self.assertEqual(response.status_code, 200)

    def test_checkout_omits_payment_url_without_compatible_provider(self):
        """No payment.provider is configured in this class's setUpClass —
        the response must not claim a payment step exists."""
        self.authenticate("checkout.buyer@example.com", self.password)
        response = self._checkout()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("payment_url", json.loads(response.content))


@tagged("post_install", "-at_install", "varsco_content")
class TestCheckoutApiWithPaymentProvider(TestCheckoutApi):
    """Same buyer/catalog fixtures as TestCheckoutApi, plus a compatible
    payment provider — asserts checkout delegates correctly to
    midvex_sale_payment_link (docs/decisions.md's Iyzico-via-portal ADR)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["payment.provider"].create(
            {
                "name": "Test Provider",
                "code": "none",
                "state": "test",
                "is_published": True,
            }
        )

    def test_checkout_includes_payment_url_with_compatible_provider(self):
        self.authenticate("checkout.buyer@example.com", self.password)
        response = self._checkout()
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        order = self.env["sale.order"].browse(body["order_id"])
        self.assertIn("payment_url", body)
        self.assertTrue(body["payment_url"].startswith("http"))
        self.assertIn(f"/my/orders/{order.id}", body["payment_url"])
        self.assertIn("access_token=", body["payment_url"])
