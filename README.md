# Olist API — MongoDB + FastAPI

REST API exposing the [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
from MongoDB, built with FastAPI.

## 1. Installation

Requirements: Python 3.14, Docker (for MongoDB & fast API).

```bash
python -m venv venv
venv/bin/python -m pip install -e ".[dev]"
cp .env.example .env   # defaults already point at localhost:27017
```

Start MongoDB:

```bash
docker compose up -d mongo
```

## 2. Import datas

Place the Olist CSV files in `datas/`, then run:

```bash
venv/bin/python -m olist.ingestion.load --data-dir datas
```

The script is idempotent: it clears each collection before repopulating it, so it can be re-run safely. It prints a summary:

```
customers: 99441 documents imported
sellers: 3095 documents imported
products: 32951 documents imported
orders: 99441 documents imported
indexes created
```

## 3. Run the API

```bash
venv/bin/python -m fastapi dev src/olist/main.py
```

Interactive docs: http://localhost:8000/docs (Swagger UI) or http://localhost:8000/redoc.

Run everything (Mongo + API) with Docker:

```bash
docker compose up -d
docker compose run --rm api olist-import --data-dir /app/datas
```

## 4. Run the tests

Tests run against a real MongoDB (`olist_test` database, dropped after the session), so start Mongo first:

```bash
docker compose up -d mongo
venv/bin/python -m pytest
```

## 5. Data modeling

Four collections:

| Collection  | Source file(s)                                     |   Key        |
|-------------|----------------------------------------------------|  ----------  |
| `customers` | `olist_customers_dataset.csv`                      | `customer_id`|
| `sellers`   | `olist_sellers_dataset.csv`                        | `seller_id`  |
| `products`  | `olist_products_dataset.csv` +                     |              |
|             |   `product_category_name_translation.csv`          | `product_id` |
| `orders`    | `olist_orders_dataset.csv` +                       |              |
|             |  `olist_order_items_dataset.csv` +                 |              |
|             |  `olist_order_payments_dataset.csv` +              |              |
|             |  `olist_order_reviews_dataset.csv`                 | `order_id`   |

We're using 7 out of the 9 CSV. 

**Embed vs. reference:**
- `customers`, `sellers`, `products` are kept as **separate collections**, referenced by id from `orders`. They are looked up on their own (e.g. "find seller X"), reused across many orders, and updated on a different lifecycle than an order.
- `order_items`, `order_payments`, `order_reviews` are **embedded inside their parent `orders` document** (as `items`, `payments`, `review`). They have no independent existence outside their order, are bounded in size and are always read together with the order. Embedding avoids a join for the single most common read: "give me everything about order X".
- `product_category_name_translation` is merged into `products` at import time (`category` / `category_english`), datas always consumed with products.
- `items_count` and `total_value` are **precomputed** on the order document at import time, so listing/sorting orders doesn't require re-aggregating the embedded arrays on every request.

**Excluded on purpose:** `olist_geolocation_dataset.csv` (~1M rows of zip/lat/lng) isn't used.

**Data cleaning decisions made in `src/olist/ingestion/load.py`:**
- Zip code prefixes are read as strings to preserve leading zeros (e.g. `"01037"`).
- 610 products have a missing/unmapped category → normalized to `"unknown"` for both `category` and `category_english`.
- 551 orders have more than one review row in the source data → only the most recently answered review is kept.
- Missing timestamps (e.g. `order_approved_at` for orders never approved) are stored as `null`.
- `total_value` is the sum of the order's payments, falling back to `sum(item price + freight)` for the rare order with no recorded payment.


## 6. API overview

Read-only consultation + aggregation API (no write endpoints — the dataset is a historical snapshot).

| Method & path | Purpose |
|---|---|
| `GET /customers` | Paginated list, optional `state` filter |
| `GET /customers/{customer_id}` | Customer detail |
| `GET /customers/{customer_id}/orders` | Order history of one customer |
| `GET /sellers` | Paginated list, optional `state` filter |
| `GET /sellers/{seller_id}` | Seller detail |
| `GET /products` | Paginated list, optional `category` filter |
| `GET /products/{product_id}` | Product detail |
| `GET /orders` | Paginated list, filter by `status`, `date_from`, `date_to` |
| `GET /orders/{order_id}` | Full order detail (items, payments, review) |
| `GET /analytics/revenue-by-category` | Revenue, order count and item count per product category |
| `GET /analytics/top-sellers` | Sellers ranked by revenue |
| `GET /analytics/orders-per-month` | Monthly order count and revenue |

**Robustness:**
- All pagination endpoints validate `skip`/`limit` (`limit` capped at 100) → responses stay bounded regardless of collection size (99k orders, 99k customers).
- `status` is validated against the known enum of order statuses; unknown values return `422`.
- An inverted date range (`date_from > date_to`) returns `400` with an explicit message.
- Unknown ids return `404`.

## 7. Performance: explain() and indexing

`GET /orders?status=&date_from=&date_to=` is the query analyzed, since it's the most common way to browse orders (e.g. "delivered orders in January 2018") and runs against the full 99,441-document `orders` collection.

`scripts/explain_demo.py` measures it before and after adding a compound index on `(status, purchase_timestamp)`:

```
Before index (COLLSCAN):
  docs_examined: 99441   execution_time_ms: 91

After index on (status, purchase_timestamp) (IXSCAN via FETCH):
  docs_examined: 7069    execution_time_ms: 16
```

The index lets MongoDB jump directly to the ~7k matching documents instead of scanning the whole collection — roughly a 5-6x reduction in execution time and a 14x reduction in documents examined. This index (plus `customers.customer_state`, `sellers.seller_state`, `products.category`, `orders.customer_id`) is created automatically by the ingestion script (`create_indexes()` in `src/olist/ingestion/load.py`).

## 8. Project structure

```
src/olist/
  main.py            FastAPI app + router registration
  config.py          Settings loaded from .env (MONGO_URI, MONGO_DB)
  database.py        MongoDB client / FastAPI dependency
  schemas.py          Pydantic response models
  routers/            One module per resource (customers, sellers, products, orders, analytics)
  ingestion/load.py   CSV -> MongoDB import script (entry point: `olist-import`)
scripts/explain_demo.py   Index/explain() performance demonstration
tests/                     pytest test suite (FastAPI TestClient + real test MongoDB)
```
