import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "varsco_content")
class TestAddressesApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = "Test1234!"

        cls.buyer = cls.env["res.partner"].create(
            {"name": "Address Buyer", "email": "address.buyer@example.com"}
        )
        cls.env["res.users"].create(
            {
                "name": "Address Buyer",
                "login": "address.buyer@example.com",
                "password": cls.password,
                "partner_id": cls.buyer.id,
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )

        cls.other_buyer = cls.env["res.partner"].create(
            {"name": "Other Address Buyer", "email": "other.address.buyer@example.com"}
        )
        cls.env["res.users"].create(
            {
                "name": "Other Address Buyer",
                "login": "other.address.buyer@example.com",
                "password": cls.password,
                "partner_id": cls.other_buyer.id,
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )

    def _create(self, **overrides):
        payload = {
            "type": "delivery",
            "name": "Warehouse A",
            "street": "123 Harbor Rd",
            "city": "Izmir",
            "country": "Türkiye",
        }
        payload.update(overrides)
        return self.url_open(
            "/api/v1/store/addresses",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def test_list_requires_authentication(self):
        response = self.url_open("/api/v1/store/addresses")
        self.assertEqual(response.status_code, 401)

    def test_create_requires_authentication(self):
        response = self._create()
        self.assertEqual(response.status_code, 401)

    def test_create_requires_type(self):
        self.authenticate("address.buyer@example.com", self.password)
        response = self._create(type="parent")
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_unknown_country(self):
        self.authenticate("address.buyer@example.com", self.password)
        response = self._create(country="0000000000")
        self.assertEqual(response.status_code, 400)

    def test_create_and_list_round_trip(self):
        self.authenticate("address.buyer@example.com", self.password)
        response = self._create()
        self.assertEqual(response.status_code, 201)
        created = json.loads(response.content)["data"]
        self.assertEqual(created["type"], "delivery")
        self.assertEqual(created["city"], "Izmir")
        self.assertEqual(created["country"], "Türkiye")

        list_response = self.url_open("/api/v1/store/addresses")
        self.assertEqual(list_response.status_code, 200)
        addresses = json.loads(list_response.content)["data"]
        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses[0]["id"], created["id"])

    def test_created_address_is_child_of_authenticated_partner(self):
        self.authenticate("address.buyer@example.com", self.password)
        response = self._create()
        created_id = json.loads(response.content)["data"]["id"]
        address = self.env["res.partner"].browse(created_id)
        self.assertEqual(address.parent_id.id, self.buyer.id)

    def test_list_only_returns_own_addresses(self):
        self.authenticate("address.buyer@example.com", self.password)
        self._create()
        self.authenticate("other.address.buyer@example.com", self.password)
        response = self.url_open("/api/v1/store/addresses")
        self.assertEqual(json.loads(response.content)["data"], [])

    def test_update_requires_authentication(self):
        self.authenticate("address.buyer@example.com", self.password)
        created_id = json.loads(self._create().content)["data"]["id"]
        self.logout()
        response = self.url_open(
            f"/api/v1/store/addresses/{created_id}",
            data=json.dumps({"city": "Ankara"}).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        self.assertEqual(response.status_code, 401)

    def test_update_own_address(self):
        self.authenticate("address.buyer@example.com", self.password)
        created_id = json.loads(self._create().content)["data"]["id"]
        response = self.url_open(
            f"/api/v1/store/addresses/{created_id}",
            data=json.dumps({"city": "Ankara"}).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["data"]["city"], "Ankara")

    def test_update_rejects_other_partners_address(self):
        self.authenticate("address.buyer@example.com", self.password)
        created_id = json.loads(self._create().content)["data"]["id"]
        self.authenticate("other.address.buyer@example.com", self.password)
        response = self.url_open(
            f"/api/v1/store/addresses/{created_id}",
            data=json.dumps({"city": "Ankara"}).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_requires_authentication(self):
        self.authenticate("address.buyer@example.com", self.password)
        created_id = json.loads(self._create().content)["data"]["id"]
        self.logout()
        response = self.url_open(f"/api/v1/store/addresses/{created_id}", method="DELETE")
        self.assertEqual(response.status_code, 401)

    def test_delete_rejects_other_partners_address(self):
        self.authenticate("address.buyer@example.com", self.password)
        created_id = json.loads(self._create().content)["data"]["id"]
        self.authenticate("other.address.buyer@example.com", self.password)
        response = self.url_open(f"/api/v1/store/addresses/{created_id}", method="DELETE")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(self.env["res.partner"].browse(created_id).exists())

    def test_delete_own_address(self):
        self.authenticate("address.buyer@example.com", self.password)
        created_id = json.loads(self._create().content)["data"]["id"]
        response = self.url_open(f"/api/v1/store/addresses/{created_id}", method="DELETE")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.env["res.partner"].browse(created_id).exists())

    def test_delete_address_referenced_by_sale_order_is_conflict(self):
        self.authenticate("address.buyer@example.com", self.password)
        created_id = json.loads(self._create().content)["data"]["id"]
        address = self.env["res.partner"].browse(created_id)
        self.env["sale.order"].create(
            {
                "partner_id": self.buyer.id,
                "partner_shipping_id": address.id,
                "partner_invoice_id": self.buyer.id,
            }
        )
        response = self.url_open(f"/api/v1/store/addresses/{created_id}", method="DELETE")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(address.exists())

    def test_checkout_accepts_saved_address_as_shipping_partner(self):
        # Confirms addresses.py's created contacts satisfy checkout.py's
        # existing _owned_by_partner ownership check unchanged — no
        # checkout.py code was touched for this feature.
        self.authenticate("address.buyer@example.com", self.password)
        created_id = json.loads(self._create().content)["data"]["id"]
        product = self.env["product.template"].create(
            {"name": "Address Test Product", "list_price": 5.0, "is_published": True}
        )
        response = self.url_open(
            "/api/v1/store/checkout",
            data=json.dumps(
                {
                    "items": [{"product_id": product.product_variant_id.id, "qty": 1}],
                    "shipping_partner_id": created_id,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        self.assertEqual(response.status_code, 200)
