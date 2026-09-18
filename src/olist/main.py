from fastapi import FastAPI

from olist.routers import analytics, customers, orders, products, sellers

app = FastAPI(
    title="Olist API",
    description="REST API exposing the Brazilian E-Commerce Public Dataset by Olist, stored in MongoDB.",
    version="0.1.0",
)

app.include_router(customers.router)
app.include_router(sellers.router)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(analytics.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
