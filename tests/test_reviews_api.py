import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "varsco_content")
class TestReviewsApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = "Test1234!"

        cls.template = cls.env["product.template"].create(
            {"name": "Reviewable Product", "list_price": 25.0, "is_published": True}
        )
        cls.slug = cls.env["ir.http"]._slug(cls.template)

        cls.unpublished = cls.env["product.template"].create(
            {"name": "Not Published", "list_price": 10.0, "is_published": False}
        )

        cls.buyer = cls.env["res.partner"].create(
            {"name": "Verified Buyer", "email": "verified.buyer@example.com"}
        )
        cls.env["res.users"].create(
            {
                "name": "Verified Buyer",
                "login": "verified.buyer@example.com",
                "password": cls.password,
                "partner_id": cls.buyer.id,
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )
        cls.env["sale.order"].create(
            {
                "partner_id": cls.buyer.id,
                "state": "sale",
                "order_line": [
                    (0, 0, {"product_id": cls.template.product_variant_id.id, "product_uom_qty": 1})
                ],
            }
        )

        cls.non_buyer = cls.env["res.partner"].create(
            {"name": "Never Bought", "email": "never.bought@example.com"}
        )
        cls.env["res.users"].create(
            {
                "name": "Never Bought",
                "login": "never.bought@example.com",
                "password": cls.password,
                "partner_id": cls.non_buyer.id,
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )

    def _reviews_url(self, slug=None):
        return f"/api/v1/store/products/en/{slug or self.slug}/reviews"

    def _submit(self, rating=5, feedback="Great product, arrived fast."):
        return self.url_open(
            self._reviews_url(),
            data=json.dumps({"rating": rating, "feedback": feedback}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def test_list_unknown_slug_is_404(self):
        response = self.url_open(self._reviews_url("does-not-exist-999999"))
        self.assertEqual(response.status_code, 404)

    def test_list_returns_only_consumed_ratings(self):
        self.env["rating.rating"].create(
            {
                "res_model_id": self.env["ir.model"]._get("product.template").id,
                "res_id": self.template.id,
                "partner_id": self.buyer.id,
                "rating": 4,
                "feedback": "Solid quality.",
                "consumed": True,
            }
        )
        self.env["rating.rating"].create(
            {
                "res_model_id": self.env["ir.model"]._get("product.template").id,
                "res_id": self.template.id,
                "partner_id": self.non_buyer.id,
                "rating": 2,
                "consumed": False,
            }
        )
        response = self.url_open(self._reviews_url())
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(len(payload["data"]), 1)
        self.assertEqual(payload["data"][0]["author_name"], "Verified Buyer")
        self.assertEqual(payload["data"][0]["rating"], 4)
        self.assertEqual(payload["meta"]["rating_count"], 1)
        self.assertEqual(payload["meta"]["rating_avg"], 4.0)

    def test_submit_requires_authentication(self):
        response = self._submit()
        self.assertEqual(response.status_code, 401)

    def test_submit_requires_verified_purchase(self):
        self.authenticate("never.bought@example.com", self.password)
        response = self._submit()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(json.loads(response.content)["error"], "purchase_required")

    def test_submit_rejects_invalid_rating(self):
        self.authenticate("verified.buyer@example.com", self.password)
        response = self._submit(rating=0)
        self.assertEqual(response.status_code, 400)
        response = self._submit(rating=6)
        self.assertEqual(response.status_code, 400)

    def test_submit_rejects_unpublished_product(self):
        self.authenticate("verified.buyer@example.com", self.password)
        response = self.url_open(
            self._reviews_url(self.env["ir.http"]._slug(self.unpublished)),
            data=json.dumps({"rating": 5}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        self.assertEqual(response.status_code, 404)

    def test_submit_succeeds_for_verified_purchase(self):
        self.authenticate("verified.buyer@example.com", self.password)
        response = self._submit(rating=5, feedback="Excellent.")
        self.assertEqual(response.status_code, 201)
        payload = json.loads(response.content)
        self.assertEqual(payload["data"]["rating"], 5)
        self.assertEqual(payload["data"]["feedback"], "Excellent.")

        list_response = self.url_open(self._reviews_url())
        list_payload = json.loads(list_response.content)
        self.assertEqual(list_payload["meta"]["rating_count"], 1)
        self.assertEqual(list_payload["meta"]["rating_avg"], 5.0)

    def test_submit_rejects_duplicate_review(self):
        self.authenticate("verified.buyer@example.com", self.password)
        first = self._submit(rating=5)
        self.assertEqual(first.status_code, 201)
        second = self._submit(rating=3)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(json.loads(second.content)["error"], "already_reviewed")
