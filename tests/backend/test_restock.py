"""
Tests for restocking API endpoints.
"""
from datetime import datetime, timedelta


class TestRestockRecommendations:
    """Test suite for restock recommendations."""

    def test_total_respects_budget(self, client):
        for budget in [1000, 10000, 50000, 100000]:
            data = client.get(f"/api/restock/recommendations?budget={budget}").json()
            assert data["total_cost"] <= budget
            assert abs(sum(i["line_total"] for i in data["items"]) - data["total_cost"]) < 0.01

    def test_zero_budget_returns_empty(self, client):
        data = client.get("/api/restock/recommendations?budget=0").json()
        assert data["items"] == []
        assert data["total_cost"] == 0

    def test_decreasing_trends_excluded(self, client):
        data = client.get("/api/restock/recommendations?budget=100000").json()
        assert len(data["items"]) > 0
        assert all(i["trend"] != "decreasing" for i in data["items"])
        assert "MTR-304" not in [i["item_sku"] for i in data["items"]]

    def test_ordered_by_growth(self, client):
        demand = {d["item_sku"]: d for d in client.get("/api/demand").json()}
        items = client.get("/api/restock/recommendations?budget=100000").json()["items"]
        growth = [demand[i["item_sku"]]["forecasted_demand"] - demand[i["item_sku"]]["current_demand"]
                  for i in items]
        assert growth == sorted(growth, reverse=True)

    def test_on_hand_reduces_quantity(self, client):
        items = client.get("/api/restock/recommendations?budget=100000").json()["items"]
        for i in items:
            assert i["quantity"] <= max(i["forecasted_demand"] - i["on_hand"], 0)

    def test_larger_budget_spends_more(self, client):
        small = client.get("/api/restock/recommendations?budget=5000").json()["total_cost"]
        large = client.get("/api/restock/recommendations?budget=100000").json()["total_cost"]
        assert large > small


class TestRestockPartialFill:
    """Partial-fill rule: buy as many whole units as the remaining budget allows."""

    def test_partial_fill_uses_whole_units(self, client):
        data = client.get("/api/restock/recommendations?budget=1000").json()
        assert data["total_cost"] <= 1000
        for i in data["items"]:
            assert isinstance(i["quantity"], int) and i["quantity"] >= 1
            assert abs(i["line_total"] - i["quantity"] * i["unit_cost"]) < 0.01


class TestRestockOrders:
    """Test suite for submitted restock orders."""

    def _post(self, client, items):
        return client.post("/api/restock-orders", json={"items": items})

    def test_create_order(self, client):
        # WDG-001 @ 85.00 (14d), FLT-405 @ 42.00 (7d)
        response = self._post(client, [
            {"item_sku": "WDG-001", "quantity": 10},
            {"item_sku": "FLT-405", "quantity": 5},
        ])
        assert response.status_code == 201
        order = response.json()
        assert order["status"] == "Submitted"
        assert abs(order["total_cost"] - (850 + 210)) < 0.01
        assert order["lead_time_days"] == 14
        order_date = datetime.fromisoformat(order["order_date"])
        assert datetime.fromisoformat(order["expected_delivery"]) == order_date + timedelta(days=14)

    def test_server_reprices_items(self, client):
        response = client.post("/api/restock-orders", json={
            "items": [{"item_sku": "WDG-001", "quantity": 1, "unit_cost": 0.01}]
        })
        assert response.status_code == 201
        assert response.json()["items"][0]["unit_cost"] == 85.0

    def test_unknown_sku_rejected(self, client):
        assert self._post(client, [{"item_sku": "NOPE-1", "quantity": 1}]).status_code == 400

    def test_empty_order_rejected(self, client):
        assert self._post(client, []).status_code == 400

    def test_invalid_quantity_rejected(self, client):
        assert self._post(client, [{"item_sku": "WDG-001", "quantity": 0}]).status_code == 400

    def test_list_orders_newest_first(self, client):
        assert client.get("/api/restock-orders").json() == []
        first = self._post(client, [{"item_sku": "WDG-001", "quantity": 1}]).json()
        second = self._post(client, [{"item_sku": "FLT-405", "quantity": 1}]).json()
        data = client.get("/api/restock-orders").json()
        assert [o["id"] for o in data] == [second["id"], first["id"]]

    def test_duplicate_skus_rejected(self, client):
        response = self._post(client, [
            {"item_sku": "WDG-001", "quantity": 1},
            {"item_sku": "WDG-001", "quantity": 2},
        ])
        assert response.status_code == 400

    def test_over_budget_rejected(self, client):
        response = client.post("/api/restock-orders", json={
            "items": [{"item_sku": "WDG-001", "quantity": 10}], "budget": 849.99
        })
        assert response.status_code == 400
        assert client.get("/api/restock-orders").json() == []

    def test_within_budget_accepted(self, client):
        response = client.post("/api/restock-orders", json={
            "items": [{"item_sku": "WDG-001", "quantity": 10}], "budget": 850
        })
        assert response.status_code == 201
