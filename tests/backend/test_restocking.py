"""
Tests for restocking order API endpoints.
"""
from datetime import datetime, timedelta

import pytest

import mock_data


@pytest.fixture(autouse=True)
def reset_restocking_orders():
    """Clear in-memory restocking orders around each test.

    The list lives at module level and survives across TestClient instances,
    so without this, orders created in one test would leak into the next.
    """
    mock_data.restocking_orders.clear()
    yield
    mock_data.restocking_orders.clear()


def get_forecasts_by_sku(client):
    """Helper to index demand forecasts by SKU."""
    response = client.get("/api/demand")
    return {f["item_sku"]: f for f in response.json()}


class TestDemandForecastRestockFields:
    """Test the cost and lead time fields that restocking relies on."""

    def test_demand_forecast_restock_field_types(self, client):
        """Test every forecast has a positive unit cost and lead time."""
        response = client.get("/api/demand")
        assert response.status_code == 200

        for forecast in response.json():
            assert isinstance(forecast["unit_cost"], (int, float))
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["unit_cost"] > 0
            assert forecast["lead_time_days"] >= 1


class TestRestockingOrderEndpoints:
    """Test suite for restocking order endpoints."""

    def test_get_restocking_orders_initially_empty(self, client):
        """Test that no restocking orders exist before any are placed."""
        response = client.get("/api/restocking-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restocking_order(self, client):
        """Test placing a restocking order returns the created order."""
        payload = {
            "items": [
                {"item_sku": "FLT-405", "quantity": 150},
                {"item_sku": "WDG-001", "quantity": 87},
            ],
            "budget": 2050,
        }
        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        for field in ["id", "order_number", "items", "total_cost", "budget",
                      "status", "submitted_date", "lead_time_days", "expected_delivery"]:
            assert field in order
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("RST-")
        assert order["budget"] == 2050
        assert len(order["items"]) == 2

    def test_restocking_order_total_calculation(self, client):
        """Test that line totals and order total use server-side unit costs."""
        forecasts = get_forecasts_by_sku(client)
        payload = {
            "items": [
                {"item_sku": "FLT-405", "quantity": 150},
                {"item_sku": "WDG-001", "quantity": 87},
            ],
            "budget": 2050,
        }
        order = client.post("/api/restocking-orders", json=payload).json()

        for item in order["items"]:
            expected_line = forecasts[item["item_sku"]]["unit_cost"] * item["quantity"]
            assert abs(item["line_total"] - expected_line) < 0.01
            assert item["item_name"] == forecasts[item["item_sku"]]["item_name"]

        # 150 * 6.40 + 87 * 12.50
        assert abs(order["total_cost"] - 2047.50) < 0.01

    def test_restocking_order_lead_time_calculation(self, client):
        """Test order lead time is the slowest item and drives expected delivery."""
        forecasts = get_forecasts_by_sku(client)
        payload = {
            "items": [
                {"item_sku": "FLT-405", "quantity": 1},
                {"item_sku": "CTL-330", "quantity": 1},
            ],
            "budget": 1000,
        }
        order = client.post("/api/restocking-orders", json=payload).json()

        expected_lead = max(forecasts["FLT-405"]["lead_time_days"],
                            forecasts["CTL-330"]["lead_time_days"])
        assert order["lead_time_days"] == expected_lead

        submitted = datetime.fromisoformat(order["submitted_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        assert expected_delivery - submitted == timedelta(days=expected_lead)

    def test_restocking_order_ignores_client_prices(self, client):
        """Test that prices sent by the client are not used."""
        payload = {
            "items": [{"item_sku": "MTR-304", "quantity": 1, "unit_cost": 0.01}],
            "budget": 1000,
        }
        order = client.post("/api/restocking-orders", json=payload).json()
        assert order["items"][0]["unit_cost"] == 320.00
        assert abs(order["total_cost"] - 320.00) < 0.01

    def test_get_restocking_orders_after_create(self, client):
        """Test that placed orders are listed newest first."""
        first = client.post("/api/restocking-orders", json={
            "items": [{"item_sku": "FLT-405", "quantity": 1}], "budget": 100,
        }).json()
        second = client.post("/api/restocking-orders", json={
            "items": [{"item_sku": "GSK-203", "quantity": 1}], "budget": 100,
        }).json()

        response = client.get("/api/restocking-orders")
        assert response.status_code == 200
        data = response.json()
        assert [o["id"] for o in data] == [second["id"], first["id"]]

    def test_create_restocking_order_unknown_sku(self, client):
        """Test ordering an item not in the demand forecast."""
        response = client.post("/api/restocking-orders", json={
            "items": [{"item_sku": "NOPE-999", "quantity": 1}], "budget": 100,
        })
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.parametrize("payload", [
        {"items": [], "budget": 100},
        {"items": [{"item_sku": "FLT-405", "quantity": 0}], "budget": 100},
        {"items": [{"item_sku": "FLT-405", "quantity": -5}], "budget": 100},
        {"items": [{"item_sku": "FLT-405", "quantity": 1}], "budget": -1},
        {"items": [{"item_sku": "FLT-405", "quantity": 1},
                   {"item_sku": "FLT-405", "quantity": 2}], "budget": 100},
    ], ids=["empty-items", "zero-qty", "negative-qty", "negative-budget", "duplicate-sku"])
    def test_create_restocking_order_invalid_input(self, client, payload):
        """Test that invalid orders are rejected with 400."""
        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 400
        assert "detail" in response.json()
        assert mock_data.restocking_orders == []

    def test_create_restocking_order_over_budget(self, client):
        """Test that an order costing more than the budget is rejected."""
        response = client.post("/api/restocking-orders", json={
            "items": [{"item_sku": "MTR-304", "quantity": 2}], "budget": 500,
        })
        assert response.status_code == 400
        assert "exceeds budget" in response.json()["detail"]

    def test_create_restocking_order_exactly_at_budget(self, client):
        """Test that an order costing exactly the budget is accepted."""
        response = client.post("/api/restocking-orders", json={
            "items": [{"item_sku": "MTR-304", "quantity": 2}], "budget": 640,
        })
        assert response.status_code == 201

    def test_create_restocking_order_missing_fields(self, client):
        """Test that a malformed body fails Pydantic validation."""
        response = client.post("/api/restocking-orders", json={"items": []})
        assert response.status_code == 422

    def test_create_restocking_order_does_not_mutate_forecasts(self, client):
        """Test that placing an order leaves demand forecast data unchanged."""
        before = client.get("/api/demand").json()
        client.post("/api/restocking-orders", json={
            "items": [{"item_sku": "FLT-405", "quantity": 10}], "budget": 100,
        })
        after = client.get("/api/demand").json()
        assert before == after
