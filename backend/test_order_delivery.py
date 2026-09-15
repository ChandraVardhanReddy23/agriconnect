import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import db
from backend.main import app


class OrderDeliveryTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = patch.object(db, "DB_PATH", Path(directory.name) / "test.db")
        database.start()
        self.addCleanup(database.stop)
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.users = {}
        for role in ("farmer", "buyer", "transporter"):
            response = self.client.post("/api/signup", json={
                "name": role, "email": f"{role}@example.test",
                "password": "test-only", "role": role, "location": "Nashik",
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.users[role] = response.json()["id"]
        self.order_ids = []
        for _ in range(2):
            response = self.client.post("/api/listings", json={
                "farmer_id": self.users["farmer"], "crop": "Tomato",
                "quantity": 100, "price": 2200, "location": "Nashik",
            })
            self.assertEqual(response.status_code, 200, response.text)
            listing_id = response.json()["id"]
            response = self.client.post("/api/orders", json={
                "listing_id": listing_id, "buyer_id": self.users["buyer"],
                "quantity": 10, "agreed_price": 2200,
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.order_ids.append(response.json()["id"])

    def post_order(self, order_id, action, payload=None):
        return self.client.post(f"/api/orders/{order_id}/{action}", json=payload)

    def get_order(self, order_id):
        response = self.client.get(f"/api/orders/{order_id}")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def confirm_and_pay(self, order_id):
        self.assertEqual(self.post_order(order_id, "accept").status_code, 200)
        response = self.post_order(order_id, "pay", {})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["order_status"], "CONFIRMED")

    def claim_route(self):
        routes = self.client.get("/api/routes/available").json()
        self.assertEqual(len(routes), 1)
        self.assertCountEqual(routes[0]["order_ids"], self.order_ids)
        response = self.client.post(f"/api/routes/{routes[0]['route_id']}/claim", json={
            "transporter_id": self.users["transporter"],
        })
        self.assertEqual(response.status_code, 200, response.text)

    def photo_action(self, order_id, action):
        response = self.post_order(order_id, action, {
            "transporter_id": self.users["transporter"],
            "photo_url": f"https://example.test/{action}.jpg",
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def assert_advance_rejected(self, order_id, guidance=False):
        before = self.get_order(order_id)
        response = self.post_order(order_id, "advance")
        self.assertEqual(response.status_code, 400, response.text)
        if guidance:
            self.assertIn("/pickup", response.json()["detail"])
            self.assertIn("/deliver", response.json()["detail"])
        self.assertEqual(self.get_order(order_id), before)

    def test_advance_preserves_confirmation_and_escrow_requirements(self):
        order_id = self.order_ids[0]
        self.assert_advance_rejected(order_id)
        self.assertEqual(self.post_order(order_id, "counter", {
            "counter_price": 2100, "by": "farmer",
        }).status_code, 200)
        self.assert_advance_rejected(order_id)
        self.assertEqual(self.post_order(order_id, "accept").status_code, 200)
        self.assert_advance_rejected(order_id)
        self.assertEqual(self.post_order(order_id, "pay", {}).status_code, 200)
        response = self.post_order(order_id, "advance")
        self.assertEqual(response.status_code, 200, response.text)
        order = response.json()
        self.assertEqual(order["order_status"], "PICKUP_SCHEDULED")
        self.assertEqual(order["delivery_status"], "pickup_scheduled")
        self.assertEqual(order["payment_status"], "ESCROW_HELD")
        self.assertIsNone(order["transporter_id"])
        self.assertFalse(order["pickup_photo_url"])
        self.assert_advance_rejected(order_id, guidance=True)

    def test_delivery_requires_claimed_route_and_photo_endpoints(self):
        for order_id in self.order_ids:
            self.confirm_and_pay(order_id)
        self.claim_route()
        scheduled, confirmed = self.order_ids
        self.assertEqual(self.post_order(scheduled, "advance").status_code, 200)
        self.assert_advance_rejected(scheduled, guidance=True)
        for order_id in (scheduled, confirmed):
            with self.subTest(order_id=order_id):
                response = self.post_order(order_id, "deliver", {
                    "transporter_id": self.users["transporter"],
                    "photo_url": "https://example.test/deliver.jpg",
                })
                self.assertEqual(response.status_code, 400)
                order = self.photo_action(order_id, "pickup")
                self.assertEqual(order["order_status"], "IN_TRANSIT")
                self.assertEqual(order["delivery_status"], "in_transit")
                self.assertEqual(order["transporter_id"], self.users["transporter"])
                self.assertTrue(order["route_id"])
                self.assertTrue(order["actual_pickup_at"])
                self.assertEqual(order["pickup_photo_url"], "https://example.test/pickup.jpg")
                self.assert_advance_rejected(order_id, guidance=True)
        for order_id in self.order_ids:
            order = self.photo_action(order_id, "deliver")
            self.assertEqual(order["order_status"], "DELIVERED")
            self.assertEqual(order["delivery_status"], "delivered")
            self.assertEqual(order["transporter_delivery_photo_url"], "https://example.test/deliver.jpg")
            self.assert_advance_rejected(order_id)
        for order_id, action in zip(self.order_ids, ("confirm-quality", "reject-quality")):
            self.assertEqual(self.post_order(order_id, action).status_code, 200)
            self.assert_advance_rejected(order_id)

    def test_transport_actions_reject_missing_or_blank_photos_and_transporter_id(self):
        order_id = self.order_ids[0]
        self.confirm_and_pay(order_id)
        self.claim_route()
        invalid_payloads = [
            {"transporter_id": self.users["transporter"]},
            {"photo_url": "https://example.test/photo.jpg"},
            *({"transporter_id": self.users["transporter"], "photo_url": photo}
              for photo in ("", " \t\n", None)),
        ]
        for action in ("pickup", "deliver"):
            for payload in invalid_payloads:
                with self.subTest(action=action, payload=payload):
                    before = self.get_order(order_id)
                    response = self.post_order(order_id, action, payload)
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(self.get_order(order_id), before)
            self.photo_action(order_id, action)

    def test_only_assigned_transporter_can_pick_up_or_deliver(self):
        order_id = self.order_ids[0]
        self.confirm_and_pay(order_id)
        response = self.post_order(order_id, "pickup", {
            "transporter_id": self.users["transporter"],
            "photo_url": "https://example.test/pickup.jpg",
        })
        self.assertEqual(response.status_code, 403)
        route = self.client.get("/api/routes/available").json()[0]
        response = self.client.post(f"/api/routes/{route['route_id']}/claim", json={
            "transporter_id": self.users["farmer"],
        })
        self.assertEqual(response.status_code, 400)
        self.claim_route()
        for action in ("pickup", "deliver"):
            for user_id in (self.users["farmer"], self.users["buyer"], 999999):
                before = self.get_order(order_id)
                response = self.post_order(order_id, action, {
                    "transporter_id": user_id,
                    "photo_url": "https://example.test/photo.jpg",
                })
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(self.get_order(order_id), before)
            self.photo_action(order_id, action)

    def test_pickup_still_requires_escrow(self):
        order_id = self.order_ids[0]
        self.assertEqual(self.post_order(order_id, "accept").status_code, 200)
        self.claim_route()
        response = self.post_order(order_id, "pickup", {
            "transporter_id": self.users["transporter"],
            "photo_url": "https://example.test/pickup.jpg",
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.get_order(order_id)["delivery_status"], "placed")

    def test_advance_unknown_order_returns_not_found(self):
        self.assertEqual(self.post_order(999999, "advance").status_code, 404)


if __name__ == "__main__":
    unittest.main()
