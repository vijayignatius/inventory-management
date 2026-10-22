from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders, restocking_orders

app = FastAPI(title="Factory Inventory Management System")

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

# Warehouse letter codes used in transactions.json
TRANSACTION_WAREHOUSE_CODES = {
    'San Francisco': 'A',
    'London': 'B',
    'Tokyo': 'C'
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

def filter_orders(warehouse: Optional[str] = None, category: Optional[str] = None,
                  status: Optional[str] = None, month: Optional[str] = None) -> list:
    """Apply all four dashboard filters to orders"""
    return filter_by_month(apply_filters(orders, warehouse, category, status), month)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str
    unit_cost: float
    lead_time_days: int
    warehouse: str
    category: str

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    warehouse: str
    category: str
    has_purchase_order: Optional[bool] = False

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    notes: Optional[str] = None

class RestockingOrderItemRequest(BaseModel):
    item_sku: str
    quantity: int

class CreateRestockingOrderRequest(BaseModel):
    items: List[RestockingOrderItemRequest]
    budget: float

class RestockingOrderItem(BaseModel):
    item_sku: str
    item_name: str
    quantity: int
    unit_cost: float
    line_total: float
    lead_time_days: int

class RestockingOrder(BaseModel):
    id: str
    order_number: str
    items: List[RestockingOrderItem]
    total_cost: float
    budget: float
    status: str
    submitted_date: str
    lead_time_days: int
    expected_delivery: str

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get demand forecasts with optional filtering"""
    return apply_filters(demand_forecasts, warehouse, category)

@app.get("/api/restocking-orders", response_model=List[RestockingOrder])
def get_restocking_orders():
    """Get submitted restocking orders, newest first"""
    return list(reversed(restocking_orders))

@app.post("/api/restocking-orders", response_model=RestockingOrder, status_code=201)
def create_restocking_order(request: CreateRestockingOrderRequest):
    """Submit a restocking order for items from the demand forecast"""
    if not request.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")
    if request.budget < 0:
        raise HTTPException(status_code=400, detail="Budget cannot be negative")

    forecasts_by_sku = {f["item_sku"]: f for f in demand_forecasts}
    seen_skus = set()
    items = []
    total_cents = 0
    for req_item in request.items:
        if req_item.quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Quantity for {req_item.item_sku} must be positive")
        if req_item.item_sku in seen_skus:
            raise HTTPException(status_code=400, detail=f"Duplicate item {req_item.item_sku}")
        seen_skus.add(req_item.item_sku)
        forecast = forecasts_by_sku.get(req_item.item_sku)
        if not forecast:
            raise HTTPException(status_code=404, detail=f"Item {req_item.item_sku} not found in demand forecast")

        # Price and lead time come from server data, never the client, so a
        # client can't under-report cost to slip past the budget check.
        # Sum in integer cents to avoid float drift (e.g. 0.1 + 0.2).
        line_cents = round(forecast["unit_cost"] * 100) * req_item.quantity
        total_cents += line_cents
        items.append({
            "item_sku": forecast["item_sku"],
            "item_name": forecast["item_name"],
            "quantity": req_item.quantity,
            "unit_cost": forecast["unit_cost"],
            "line_total": line_cents / 100,
            "lead_time_days": forecast["lead_time_days"],
        })

    if total_cents > round(request.budget * 100):
        raise HTTPException(
            status_code=400,
            detail=f"Order total {total_cents / 100:.2f} exceeds budget {request.budget:.2f}"
        )

    # The order arrives when its slowest item does.
    lead_time_days = max(item["lead_time_days"] for item in items)
    submitted = datetime.now().replace(microsecond=0)
    order_id = str(len(restocking_orders) + 1)
    order = {
        "id": order_id,
        "order_number": f"RST-{submitted.year}-{int(order_id):04d}",
        "items": items,
        "total_cost": total_cents / 100,
        "budget": request.budget,
        "status": "Submitted",
        "submitted_date": submitted.isoformat(),
        "lead_time_days": lead_time_days,
        "expected_delivery": (submitted + timedelta(days=lead_time_days)).isoformat(),
    }
    restocking_orders.append(order)
    return order

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get backlog items with purchase order status and optional filtering"""
    # Add has_purchase_order flag to each backlog item
    result = []
    for item in apply_filters(backlog_items, warehouse, category):
        item_dict = dict(item)
        # Check if this backlog item has a purchase order
        has_po = any(po["backlog_item_id"] == item["id"] for po in purchase_orders)
        item_dict["has_purchase_order"] = has_po
        result.append(item_dict)
    return result

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(apply_filters(backlog_items, warehouse, category))

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions(warehouse: Optional[str] = None):
    """Get recent transactions with optional warehouse filtering"""
    if not warehouse or warehouse == 'all':
        return recent_transactions
    # Transactions record warehouses by letter code. The mapping matches the
    # inventory location prefixes ("Warehouse A-12" is San Francisco, etc).
    code = TRANSACTION_WAREHOUSE_CODES.get(warehouse)
    return [t for t in recent_transactions if t.get('warehouse') == code]

@app.get("/api/reports/quarterly")
def get_quarterly_reports(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get quarterly performance reports with optional filtering"""
    # Calculate quarterly statistics from orders
    quarters = {}

    for order in filter_orders(warehouse, category, status, month):
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get month-over-month trends with optional filtering"""
    months = {}

    for order in filter_orders(warehouse, category, status, month):
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
