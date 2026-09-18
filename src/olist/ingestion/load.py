"""
Import datas into MongoDB, read and clean datas (missing, types, duplicates).
Writing four collections: customers, sellers, products, orders.
order_items / order_payments / order_reviews are embedded inside their
parent order document rather than kept as separate collections, since
they are bounded in size and always consumed together with the order.

Re-running is cool: each collection is cleared before being repopulated.
"""

import argparse
from pathlib import Path

import pandas as pd
from pymongo import ASCENDING
from pymongo.database import Database

from olist.database import get_database


# On configure nos helpers pour fitrer les données pendant l'ingestion
def _num_or_none(value) -> float | None:
    return None if pd.isna(value) else float(value)


def _int_or_none(value) -> int | None:
    return None if pd.isna(value) else int(value)


def _str_or_none(value) -> str | None:
    return None if pd.isna(value) else str(value)


def _dt_or_none(value):
    return None if pd.isna(value) else value.to_pydatetime()


def load_customers(data_dir: Path) -> list[dict]:
    df = pd.read_csv(
        data_dir / "olist_customers_dataset.csv",
        dtype={"customer_id": str, "customer_unique_id": str, "customer_zip_code_prefix": str},
    )
    return [
        {
            "_id": row.customer_id,
            "customer_id": row.customer_id,
            "customer_unique_id": row.customer_unique_id,
            "customer_zip_code_prefix": row.customer_zip_code_prefix,
            "customer_city": row.customer_city,
            "customer_state": row.customer_state,
        }
        for row in df.itertuples(index=False)
    ]


def load_sellers(data_dir: Path) -> list[dict]:
    df = pd.read_csv(
        data_dir / "olist_sellers_dataset.csv",
        dtype={"seller_id": str, "seller_zip_code_prefix": str},
    )
    return [
        {
            "_id": row.seller_id,
            "seller_id": row.seller_id,
            "seller_zip_code_prefix": row.seller_zip_code_prefix,
            "seller_city": row.seller_city,
            "seller_state": row.seller_state,
        }
        for row in df.itertuples(index=False)
    ]


# On merge le nom des produits traduits avec le .csv product_category_name_translation
def load_products(data_dir: Path) -> list[dict]:
    products = pd.read_csv(
        data_dir / "olist_products_dataset.csv",
        dtype={"product_id": str, "product_category_name": str},
    )
    translation = pd.read_csv(data_dir / "product_category_name_translation.csv", dtype=str)
    merged = products.merge(translation, on="product_category_name", how="left")
    merged["product_category_name"] = merged["product_category_name"].fillna("unknown")
    merged["product_category_name_english"] = merged["product_category_name_english"].fillna("unknown")

    return [
        {
            "_id": row.product_id,
            "product_id": row.product_id,
            "category": row.product_category_name,
            "category_english": row.product_category_name_english,
            "weight_g": _num_or_none(row.product_weight_g),
            "length_cm": _num_or_none(row.product_length_cm),
            "height_cm": _num_or_none(row.product_height_cm),
            "width_cm": _num_or_none(row.product_width_cm),
            "photos_qty": _int_or_none(row.product_photos_qty),
        }
        for row in merged.itertuples(index=False)
    ]


# On groupe les items sur les commandes pour éviter de chercher un par un, stocker dans la RAM dans un dictionnaire
# les appeler demande beaucoup moins de performance. un fetch des items sur une -commande spécfique ne rescan pas tout le dataset
def _items_by_order(data_dir: Path) -> dict[str, list[dict]]:
    df = pd.read_csv(
        data_dir / "olist_order_items_dataset.csv",
        dtype={"order_id": str, "product_id": str, "seller_id": str},
    )
    df["_item"] = df.apply(
        lambda r: {
            "product_id": r.product_id,
            "seller_id": r.seller_id,
            "price": float(r.price),
            "freight_value": float(r.freight_value),
        },
        axis=1,
    )
    return df.sort_values("order_item_id").groupby("order_id")["_item"].apply(list).to_dict()


def _payments_by_order(data_dir: Path) -> dict[str, list[dict]]:
    df = pd.read_csv(data_dir / "olist_order_payments_dataset.csv", dtype={"order_id": str})
    df["_payment"] = df.apply(
        lambda r: {
            "payment_type": r.payment_type,
            "installments": int(r.payment_installments),
            "value": float(r.payment_value),
        },
        axis=1,
    )
    return df.sort_values("payment_sequential").groupby("order_id")["_payment"].apply(list).to_dict()


def _reviews_by_order(data_dir: Path) -> dict[str, dict]:
    df = pd.read_csv(data_dir / "olist_order_reviews_dataset.csv", dtype={"order_id": str})
    df["review_creation_date"] = pd.to_datetime(df["review_creation_date"], errors="coerce")
    df["review_answer_timestamp"] = pd.to_datetime(df["review_answer_timestamp"], errors="coerce")
    # A handful of orders have more than one review row: keep the most recent one.
    df = df.sort_values("review_answer_timestamp").drop_duplicates(subset="order_id", keep="last")

    return {
        row.order_id: {
            "score": int(row.review_score),
            "comment_title": _str_or_none(row.review_comment_title),
            "comment_message": _str_or_none(row.review_comment_message),
            "creation_date": _dt_or_none(row.review_creation_date),
            "answer_timestamp": _dt_or_none(row.review_answer_timestamp),
        }
        for row in df.itertuples(index=False)
    }


# Mongo créé automatiquement un index sur _id qyu est vu par Pydantic comme une variable privée
# il permet à son tour de ne pas avoir de possibilité d'insertion d'un même ID
# et on répond aux critères de sécurité d'id interne et externe, sur l'API REST
# un client qui requête ne verra pas le _id
def load_orders(data_dir: Path) -> list[dict]:
    df = pd.read_csv(data_dir / "olist_orders_dataset.csv", dtype={"order_id": str, "customer_id": str})
    for column in (
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ):
        df[column] = pd.to_datetime(df[column], errors="coerce")

    items_by_order = _items_by_order(data_dir)
    payments_by_order = _payments_by_order(data_dir)
    reviews_by_order = _reviews_by_order(data_dir)

    # On créé des données agrégées directement pendant l'ingestion
    docs = []
    for row in df.itertuples(index=False):
        items = items_by_order.get(row.order_id, [])
        payments = payments_by_order.get(row.order_id, [])
        if payments:
            total_value = float(sum(p["value"] for p in payments))
        else:
            total_value = float(sum(i["price"] + i["freight_value"] for i in items))

        docs.append(
            {
                "_id": row.order_id,
                "order_id": row.order_id,
                "customer_id": row.customer_id,
                "status": row.order_status,
                "purchase_timestamp": _dt_or_none(row.order_purchase_timestamp),
                "approved_at": _dt_or_none(row.order_approved_at),
                "delivered_carrier_date": _dt_or_none(row.order_delivered_carrier_date),
                "delivered_customer_date": _dt_or_none(row.order_delivered_customer_date),
                "estimated_delivery_date": _dt_or_none(row.order_estimated_delivery_date),
                "items": items,
                "payments": payments,
                "review": reviews_by_order.get(row.order_id),
                "items_count": len(items),
                "total_value": total_value,
            }
        )
    return docs


# On prebuild des index sur des éléments que l'on va requêter souvent
def create_indexes(db: Database) -> None:
    db.customers.create_index("customer_state")
    db.sellers.create_index("seller_state")
    db.products.create_index("category")
    db.orders.create_index("customer_id")
    db.orders.create_index([("status", ASCENDING), ("purchase_timestamp", ASCENDING)])


# On assure la reproductibilité avec le delete_many pour la réexécution et on insert_many
def import_all(data_dir: Path, db: Database) -> None:
    loaders = {
        "customers": load_customers,
        "sellers": load_sellers,
        "products": load_products,
        "orders": load_orders,
    }
    for name, loader in loaders.items():
        docs = loader(data_dir)
        db[name].delete_many({})
        if docs:
            db[name].insert_many(docs)
        print(f"{name}: {len(docs)} documents imported")

    create_indexes(db)
    print("indexes created")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("datas"), help="Directory containing the Olist CSV files")
    args = parser.parse_args()

    db = get_database()
    import_all(args.data_dir, db)


if __name__ == "__main__":
    main()
