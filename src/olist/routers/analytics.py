from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from olist.database import get_database
from olist.schemas import CategoryRevenue, MonthlyStats, SellerRevenue

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/revenue-by-category", response_model=list[CategoryRevenue])
def revenue_by_category(
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_database),
) -> list[CategoryRevenue]:
    pipeline = [
        {"$unwind": "$items"},
        {"$lookup": {"from": "products", "localField": "items.product_id", "foreignField": "_id", "as": "product"}},
        {"$unwind": "$product"},
        {
            "$group": {
                "_id": {"category": "$product.category", "category_english": "$product.category_english"},
                "orders": {"$addToSet": "$_id"},
                "items_count": {"$sum": 1},
                "revenue": {"$sum": "$items.price"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "category": "$_id.category",
                "category_english": "$_id.category_english",
                "orders_count": {"$size": "$orders"},
                "items_count": 1,
                "revenue": 1,
            }
        },
        {"$sort": {"revenue": -1}},
        {"$limit": limit},
    ]
    return list(db.orders.aggregate(pipeline))


@router.get("/top-sellers", response_model=list[SellerRevenue])
def top_sellers(
    limit: int = Query(default=10, ge=1, le=100),
    db: Database = Depends(get_database),
) -> list[SellerRevenue]:
    pipeline = [
        {"$unwind": "$items"},
        {
            "$group": {
                "_id": "$items.seller_id",
                "orders": {"$addToSet": "$_id"},
                "items_count": {"$sum": 1},
                "revenue": {"$sum": "$items.price"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "seller_id": "$_id",
                "orders_count": {"$size": "$orders"},
                "items_count": 1,
                "revenue": 1,
            }
        },
        {"$sort": {"revenue": -1}},
        {"$limit": limit},
    ]
    return list(db.orders.aggregate(pipeline))


@router.get("/orders-per-month", response_model=list[MonthlyStats])
def orders_per_month(db: Database = Depends(get_database)) -> list[MonthlyStats]:
    pipeline = [
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": "$purchase_timestamp"}},
                "orders_count": {"$sum": 1},
                "revenue": {"$sum": "$total_value"},
            }
        },
        {"$project": {"_id": 0, "month": "$_id", "orders_count": 1, "revenue": 1}},
        {"$sort": {"month": 1}},
    ]
    return list(db.orders.aggregate(pipeline))
