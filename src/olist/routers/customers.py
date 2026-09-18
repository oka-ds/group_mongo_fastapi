from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from olist.database import get_database
from olist.schemas import Customer, CustomerPage, OrderSummary, OrderSummaryPage
from olist.utils import strip_id

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=CustomerPage)
def list_customers(
    state: str | None = Query(default=None, min_length=2, max_length=2, description="Filter by customer_state (e.g. SP)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_database),
) -> CustomerPage:
    query = {"customer_state": state.upper()} if state else {}
    total = db.customers.count_documents(query)
    docs = db.customers.find(query).skip(skip).limit(limit)
    results = [Customer(**strip_id(doc)) for doc in docs]
    return CustomerPage(total=total, skip=skip, limit=limit, results=results)


@router.get("/{customer_id}", response_model=Customer)
def get_customer(customer_id: str, db: Database = Depends(get_database)) -> Customer:
    doc = db.customers.find_one({"_id": customer_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Customer '{customer_id}' not found")
    return Customer(**strip_id(doc))


@router.get("/{customer_id}/orders", response_model=OrderSummaryPage)
def get_customer_orders(
    customer_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_database),
) -> OrderSummaryPage:
    if db.customers.find_one({"_id": customer_id}) is None:
        raise HTTPException(status_code=404, detail=f"Customer '{customer_id}' not found")

    query = {"customer_id": customer_id}
    projection = {"items": 0, "payments": 0, "review": 0}
    total = db.orders.count_documents(query)
    docs = db.orders.find(query, projection).sort("purchase_timestamp", -1).skip(skip).limit(limit)
    results = [OrderSummary(**strip_id(doc)) for doc in docs]
    return OrderSummaryPage(total=total, skip=skip, limit=limit, results=results)
