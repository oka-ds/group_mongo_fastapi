from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from olist.database import get_database
from olist.schemas import Seller, SellerPage
from olist.utils import strip_id

router = APIRouter(prefix="/sellers", tags=["sellers"])


@router.get("", response_model=SellerPage)
def list_sellers(
    state: str | None = Query(default=None, min_length=2, max_length=2, description="Filter by seller_state (e.g. SP)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_database),
) -> SellerPage:
    query = {"seller_state": state.upper()} if state else {}
    total = db.sellers.count_documents(query)
    docs = db.sellers.find(query).skip(skip).limit(limit)
    results = [Seller(**strip_id(doc)) for doc in docs]
    return SellerPage(total=total, skip=skip, limit=limit, results=results)


@router.get("/{seller_id}", response_model=Seller)
def get_seller(seller_id: str, db: Database = Depends(get_database)) -> Seller:
    doc = db.sellers.find_one({"_id": seller_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Seller '{seller_id}' not found")
    return Seller(**strip_id(doc))
