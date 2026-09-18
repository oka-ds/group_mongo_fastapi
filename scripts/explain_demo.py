"""One-off demo: show the effect of the (status, purchase_timestamp) index
on the query used by GET /orders?status=&date_from=&date_to=.

Usage: venv/bin/python scripts/explain_demo.py
Requires MongoDB running and the dataset already imported (README).
"""

from datetime import datetime

from olist.database import get_database

QUERY = {
    "status": "delivered",
    "purchase_timestamp": {
        "$gte": datetime(2018, 1, 1),
        "$lte": datetime(2018, 1, 31, 23, 59, 59),
    },
}
INDEX = [("status", 1), ("purchase_timestamp", 1)]


def summarize(explain_output: dict) -> dict:
    stats = explain_output["executionStats"]
    return {
        "stage": stats["executionStages"]["stage"],
        "docs_examined": stats["totalDocsExamined"],
        "keys_examined": stats["totalKeysExamined"],
        "docs_returned": stats["nReturned"],
        "execution_time_ms": stats["executionTimeMillis"],
    }


def main() -> None:
    db = get_database()

    for name, info in db.orders.index_information().items():
        if info["key"] == INDEX:
            db.orders.drop_index(name)

    before = db.orders.find(QUERY).explain()
    print("Before index (expect COLLSCAN):")
    print(summarize(before))

    db.orders.create_index(INDEX)

    after = db.orders.find(QUERY).explain()
    print("\nAfter index on (status, purchase_timestamp) (expect IXSCAN):")
    print(summarize(after))


if __name__ == "__main__":
    main()
