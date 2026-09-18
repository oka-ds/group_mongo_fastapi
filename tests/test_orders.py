from datetime import datetime

ORDER = {
    "_id": "order-1",
    "order_id": "order-1",
    "customer_id": "cust-1",
    "status": "delivered",
    "purchase_timestamp": datetime(2018, 1, 15),
    "approved_at": datetime(2018, 1, 15, 1, 0),
    "delivered_carrier_date": datetime(2018, 1, 16),
    "delivered_customer_date": datetime(2018, 1, 20),
    "estimated_delivery_date": datetime(2018, 1, 25),
    "items": [{"product_id": "prod-1", "seller_id": "seller-1", "price": 50.0, "freight_value": 10.0}],
    "payments": [{"payment_type": "credit_card", "installments": 1, "value": 60.0}],
    "review": {
        "score": 5,
        "comment_title": None,
        "comment_message": None,
        "creation_date": None,
        "answer_timestamp": None,
    },
    "items_count": 1,
    "total_value": 60.0,
}


def test_get_order_found(client, db):
    db.orders.insert_one(ORDER)

    response = client.get("/orders/order-1")

    assert response.status_code == 200
    body = response.json()
    assert body["total_value"] == 60.0
    assert body["items"][0]["product_id"] == "prod-1"


def test_get_order_not_found(client):
    response = client.get("/orders/does-not-exist")
    assert response.status_code == 404


def test_list_orders_filters_by_status(client, db):
    db.orders.insert_many(
        [
            ORDER,
            {**ORDER, "_id": "order-2", "order_id": "order-2", "status": "canceled"},
        ]
    )

    response = client.get("/orders", params={"status": "delivered"})

    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["order_id"] == "order-1"


def test_list_orders_rejects_invalid_status(client):
    response = client.get("/orders", params={"status": "not-a-status"})
    assert response.status_code == 422


def test_list_orders_rejects_inverted_date_range(client):
    response = client.get("/orders", params={"date_from": "2018-02-01", "date_to": "2018-01-01"})
    assert response.status_code == 400
