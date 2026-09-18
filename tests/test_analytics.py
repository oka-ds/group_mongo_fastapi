from datetime import datetime


def _order(order_id, seller_id, product_id, price, month=1):
    return {
        "_id": order_id,
        "order_id": order_id,
        "customer_id": "cust-1",
        "status": "delivered",
        "purchase_timestamp": datetime(2018, month, 10),
        "approved_at": None,
        "delivered_carrier_date": None,
        "delivered_customer_date": None,
        "estimated_delivery_date": None,
        "items": [{"product_id": product_id, "seller_id": seller_id, "price": price, "freight_value": 5.0}],
        "payments": [{"payment_type": "credit_card", "installments": 1, "value": price + 5.0}],
        "review": None,
        "items_count": 1,
        "total_value": price + 5.0,
    }


def test_revenue_by_category(client, db):
    db.products.insert_many(
        [
            {"_id": "prod-1", "product_id": "prod-1", "category": "beauty", "category_english": "beauty"},
            {"_id": "prod-2", "product_id": "prod-2", "category": "toys", "category_english": "toys"},
        ]
    )
    db.orders.insert_many(
        [
            _order("order-1", "seller-1", "prod-1", 100.0),
            _order("order-2", "seller-2", "prod-1", 50.0),
            _order("order-3", "seller-1", "prod-2", 20.0),
        ]
    )

    response = client.get("/analytics/revenue-by-category")

    body = {row["category"]: row for row in response.json()}
    assert body["beauty"]["revenue"] == 150.0
    assert body["beauty"]["orders_count"] == 2
    assert body["toys"]["revenue"] == 20.0


def test_top_sellers(client, db):
    db.orders.insert_many(
        [
            _order("order-1", "seller-1", "prod-1", 100.0),
            _order("order-2", "seller-2", "prod-1", 50.0),
            _order("order-3", "seller-1", "prod-2", 20.0),
        ]
    )

    response = client.get("/analytics/top-sellers")

    body = {row["seller_id"]: row for row in response.json()}
    assert body["seller-1"]["revenue"] == 120.0
    assert body["seller-1"]["orders_count"] == 2
    assert body["seller-2"]["revenue"] == 50.0


def test_orders_per_month(client, db):
    db.orders.insert_many(
        [
            _order("order-1", "seller-1", "prod-1", 100.0, month=1),
            _order("order-2", "seller-2", "prod-1", 50.0, month=2),
        ]
    )

    response = client.get("/analytics/orders-per-month")

    body = {row["month"]: row for row in response.json()}
    assert body["2018-01"]["orders_count"] == 1
    assert body["2018-02"]["revenue"] == 55.0
