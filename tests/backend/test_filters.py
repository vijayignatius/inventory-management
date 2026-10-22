"""
Tests for warehouse/category/status/month filters on demand, backlog,
transactions and report endpoints, plus the order data consistency they rely on.
"""
import pytest


class TestDemandFilters:
    """Test filtering demand forecasts."""

    def test_demand_forecast_location_fields(self, client):
        """Test every forecast has a warehouse and category."""
        data = client.get("/api/demand").json()
        for forecast in data:
            assert forecast["warehouse"] in ["San Francisco", "London", "Tokyo"]
            assert isinstance(forecast["category"], str)

    def test_get_demand_by_warehouse(self, client):
        """Test filtering forecasts by warehouse."""
        response = client.get("/api/demand?warehouse=Tokyo")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        for forecast in data:
            assert forecast["warehouse"] == "Tokyo"

    def test_get_demand_by_category_case_insensitive(self, client):
        """Test filtering forecasts by lowercase category, as the filter bar sends it."""
        data = client.get("/api/demand?category=actuators").json()
        assert len(data) > 0
        for forecast in data:
            assert forecast["category"].lower() == "actuators"

    def test_get_demand_multiple_filters(self, client):
        """Test combining warehouse and category filters on forecasts."""
        data = client.get("/api/demand?warehouse=San Francisco&category=power supplies").json()
        assert [f["item_sku"] for f in data] == ["PSU-501"]

    def test_get_demand_all_filter_returns_everything(self, client):
        """Test that 'all' disables filtering."""
        everything = client.get("/api/demand").json()
        filtered = client.get("/api/demand?warehouse=all&category=all").json()
        assert filtered == everything


class TestBacklogFilters:
    """Test filtering backlog items."""

    def test_get_backlog_by_warehouse(self, client):
        """Test filtering backlog by warehouse."""
        data = client.get("/api/backlog?warehouse=Tokyo").json()
        assert len(data) > 0
        for item in data:
            assert item["warehouse"] == "Tokyo"

    def test_get_backlog_by_category(self, client):
        """Test filtering backlog by category."""
        data = client.get("/api/backlog?category=Actuators").json()
        for item in data:
            assert item["category"] == "Actuators"

    def test_dashboard_backlog_count_respects_filters(self, client):
        """Test the dashboard backlog count matches the filtered backlog endpoint."""
        for query in ["", "warehouse=London", "warehouse=Tokyo&category=Actuators", "category=Sensors"]:
            backlog = client.get(f"/api/backlog?{query}").json()
            summary = client.get(f"/api/dashboard/summary?{query}").json()
            assert summary["total_backlog_items"] == len(backlog), query


class TestTransactionFilters:
    """Test filtering spending transactions."""

    @pytest.mark.parametrize("warehouse,code", [
        ("San Francisco", "A"), ("London", "B"), ("Tokyo", "C"),
    ])
    def test_get_transactions_by_warehouse(self, client, warehouse, code):
        """Test warehouse names map to the transaction letter codes."""
        data = client.get(f"/api/spending/transactions?warehouse={warehouse}").json()
        assert len(data) > 0
        for txn in data:
            assert txn["warehouse"] == code

    def test_transactions_warehouse_filters_partition_all(self, client):
        """Test the three warehouse filters together cover every transaction."""
        total = len(client.get("/api/spending/transactions").json())
        split = sum(
            len(client.get(f"/api/spending/transactions?warehouse={w}").json())
            for w in ["San Francisco", "London", "Tokyo"]
        )
        assert split == total


class TestReportFilters:
    """Test that report endpoints aggregate only the filtered orders."""

    @pytest.mark.parametrize("query", [
        "",
        "warehouse=Tokyo",
        "category=sensors",
        "status=delivered",
        "month=Q2-2025",
        "warehouse=London&category=controllers&status=shipped",
    ])
    def test_quarterly_report_matches_filtered_orders(self, client, query):
        """Test quarterly order counts and revenue sum to the filtered orders."""
        orders = client.get(f"/api/orders?{query}").json()
        quarters = client.get(f"/api/reports/quarterly?{query}").json()

        assert sum(q["total_orders"] for q in quarters) == len(orders)
        revenue = sum(o["total_value"] for o in orders)
        assert abs(sum(q["total_revenue"] for q in quarters) - revenue) < 0.01

    @pytest.mark.parametrize("query", ["", "warehouse=San Francisco", "status=backordered&category=actuators"])
    def test_monthly_trends_match_filtered_orders(self, client, query):
        """Test monthly order counts sum to the filtered orders."""
        orders = client.get(f"/api/orders?{query}").json()
        months = client.get(f"/api/reports/monthly-trends?{query}").json()
        assert sum(m["order_count"] for m in months) == len(orders)

    def test_monthly_trends_single_month(self, client):
        """Test the month filter narrows trends to that month."""
        months = client.get("/api/reports/monthly-trends?month=2025-03").json()
        assert [m["month"] for m in months] == ["2025-03"]


class TestOrderDataConsistency:
    """Test that order-level warehouse/category agree with their line items."""

    def test_order_items_match_order_warehouse_and_category(self, client):
        """Test every line item is stocked in the order's warehouse and category."""
        inventory = {i["sku"]: i for i in client.get("/api/inventory").json()}
        for order in client.get("/api/orders").json():
            for item in order["items"]:
                assert item["sku"] in inventory, (order["id"], item["sku"])
                stock = inventory[item["sku"]]
                assert stock["warehouse"] == order["warehouse"], (order["id"], item["sku"])
                assert stock["category"] == order["category"], (order["id"], item["sku"])

    def test_order_total_matches_line_items(self, client):
        """Test order totals still equal the sum of their line items."""
        for order in client.get("/api/orders").json():
            calculated = sum(i["quantity"] * i["unit_price"] for i in order["items"])
            assert abs(order["total_value"] - calculated) < 0.01, order["id"]
