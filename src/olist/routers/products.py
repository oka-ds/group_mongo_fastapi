from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from olist.database import get_database
from olist.schemas import Product, ProductPage
from olist.utils import strip_id

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductPage)
def list_products(
    category: str | None = Query(default=None, description="Filter by product_category_name (Portuguese slug)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_database),
) -> ProductPage:
    query = {"category": category} if category else {}
    total = db.products.count_documents(query)
    docs = db.products.find(query).skip(skip).limit(limit)
    results = [Product(**strip_id(doc)) for doc in docs]
    return ProductPage(total=total, skip=skip, limit=limit, results=results)


@router.get("/{product_id}", response_model=Product)
def get_product(product_id: str, db: Database = Depends(get_database)) -> Product:
    doc = db.products.find_one({"_id": product_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
    return Product(**strip_id(doc))
