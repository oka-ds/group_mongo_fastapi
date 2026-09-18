CUSTOMER = {
    "_id": "cust-1",
    "customer_id": "cust-1",
    "customer_unique_id": "unique-1",
    "customer_zip_code_prefix": "01037",
    "customer_city": "sao paulo",
    "customer_state": "SP",
}


def test_get_customer_found(client, db):
    db.customers.insert_one(CUSTOMER)

    response = client.get("/customers/cust-1")

    assert response.status_code == 200
    assert response.json()["customer_city"] == "sao paulo"


def test_get_customer_not_found(client):
    response = client.get("/customers/does-not-exist")
    assert response.status_code == 404


def test_list_customers_filters_by_state(client, db):
    db.customers.insert_many(
        [
            CUSTOMER,
            {**CUSTOMER, "_id": "cust-2", "customer_id": "cust-2", "customer_state": "RJ"},
        ]
    )

    response = client.get("/customers", params={"state": "sp"})

    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["customer_id"] == "cust-1"


def test_list_customers_rejects_limit_above_max(client):
    response = client.get("/customers", params={"limit": 500})
    assert response.status_code == 422
