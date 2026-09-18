from datetime import date, datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from olist.database import get_database
from olist.schemas import Order, OrderSummary, OrderSummaryPage
from olist.utils import strip_id

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderStatus(str, Enum):
    delivered = "delivered"
    shipped = "shipped"
    canceled = "canceled"
    unavailable = "unavailable"
    invoiced = "invoiced"
    processing = "processing"
    created = "created"
    approved = "approved"


@router.get("", response_model=OrderSummaryPage)
def list_orders(
    status: OrderStatus | None = Query(default=None, description="Filter by order status"),
    date_from: date | None = Query(default=None, description="Filter orders purchased on/after this date"),
    date_to: date | None = Query(default=None, description="Filter orders purchased on/before this date"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_database),
) -> OrderSummaryPage:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be before date_to")

    query: dict = {}
    if status is not None:
        query["status"] = status.value
    if date_from or date_to:
        bounds = {}
        if date_from:
            bounds["$gte"] = datetime.combine(date_from, datetime.min.time())
        if date_to:
            bounds["$lte"] = datetime.combine(date_to, datetime.max.time())
        query["purchase_timestamp"] = bounds

    projection = {"items": 0, "payments": 0, "review": 0}
    total = db.orders.count_documents(query)
    docs = db.orders.find(query, projection).sort("purchase_timestamp", -1).skip(skip).limit(limit)
    results = [OrderSummary(**strip_id(doc)) for doc in docs]
    return OrderSummaryPage(total=total, skip=skip, limit=limit, results=results)


@router.get("/{order_id}", response_model=Order)
def get_order(order_id: str, db: Database = Depends(get_database)) -> Order:
    doc = db.orders.find_one({"_id": order_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found")
    return Order(**strip_id(doc))
