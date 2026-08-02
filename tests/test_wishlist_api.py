import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "varsco_content")
class TestWishlistApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = "Test1234!"

        cls.template = cls.env["product.template"].create(
            {"name": "Wishlistable Product", "list_price": 18.0, "is_published": True}
        )
        cls.variant = cls.template.product_variant_id

        cls.buyer = cls.env["res.partner"].create(
            {"name": "Wishlist Buyer", "email": "wishlist.buyer@example.com"}
        )
        cls.env["res.users"].create(
            {
                "name": "Wishlist Buyer",
                "login": "wishlist.buyer@example.com",
                "password": cls.password,
                "partner_id": cls.buyer.id,
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )

        cls.other_buyer = cls.env["res.partner"].create(
            {"name": "Other Buyer", "email": "other.buyer@example.com"}
        )
        cls.env["res.users"].create(
            {
                "name": "Other Buyer",
                "login": "other.buyer@example.com",
                "password": cls.password,
                "partner_id": cls.other_buyer.id,
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )

    def _add(self, product_id=None):
        return self.url_open(
            "/api/v1/store/wishlist",
            data=json.dumps({"product_id": product_id or self.variant.id}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def test_list_requires_authentication(self):
        response = self.url_open("/api/v1/store/wishlist")
        self.assertEqual(response.status_code, 401)

    def test_add_requires_authentication(self):
        response = self._add()
        self.assertEqual(response.status_code, 401)

    def test_add_unknown_product_is_404(self):
        self.authenticate("wishlist.buyer@example.com", self.password)
        response = self._add(product_id=999999)
        self.assertEqual(response.status_code, 404)

    def test_add_creates_wishlist_item_and_list_returns_it(self):
        self.authenticate("wishlist.buyer@example.com", self.password)
        response = self._add()
        self.assertEqual(response.status_code, 201)
        payload = json.loads(response.content)
        self.assertEqual(payload["data"]["slug"], self.env["ir.http"]._slug(self.template))

        list_response = self.url_open("/api/v1/store/wishlist")
        self.assertEqual(list_response.status_code, 200)
        list_payload = json.loads(list_response.content)
        self.assertEqual(len(list_payload["data"]), 1)
        self.assertEqual(list_payload["data"][0]["name"], "Wishlistable Product")

    def test_add_is_idempotent_for_duplicate(self):
        self.authenticate("wishlist.buyer@example.com", self.password)
        first = self._add()
        self.assertEqual(first.status_code, 201)
        second = self._add()
        self.assertEqual(second.status_code, 200)
        count = self.env["product.wishlist"].search_count(
            [("partner_id", "=", self.buyer.id), ("product_id", "=", self.variant.id)]
        )
        self.assertEqual(count, 1)

    def test_remove_requires_authentication(self):
        response = self.url_open(f"/api/v1/store/wishlist/{self.variant.id}", method="DELETE")
        self.assertEqual(response.status_code, 401)

    def test_remove_deletes_own_item(self):
        self.authenticate("wishlist.buyer@example.com", self.password)
        self._add()
        response = self.url_open(f"/api/v1/store/wishlist/{self.variant.id}", method="DELETE")
        self.assertEqual(response.status_code, 200)
        count = self.env["product.wishlist"].search_count(
            [("partner_id", "=", self.buyer.id), ("product_id", "=", self.variant.id)]
        )
        self.assertEqual(count, 0)

    def test_remove_does_not_affect_other_partners_item(self):
        self.authenticate("wishlist.buyer@example.com", self.password)
        self._add()
        self.authenticate("other.buyer@example.com", self.password)
        response = self.url_open(f"/api/v1/store/wishlist/{self.variant.id}", method="DELETE")
        self.assertEqual(response.status_code, 200)
        count = self.env["product.wishlist"].search_count(
            [("partner_id", "=", self.buyer.id), ("product_id", "=", self.variant.id)]
        )
        self.assertEqual(count, 1)
