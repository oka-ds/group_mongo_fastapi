from datetime import datetime

from pydantic import BaseModel


class Customer(BaseModel):
    customer_id: str
    customer_unique_id: str
    customer_zip_code_prefix: str
    customer_city: str
    customer_state: str


class CustomerPage(BaseModel):
    total: int
    skip: int
    limit: int
    results: list[Customer]


class Seller(BaseModel):
    seller_id: str
    seller_zip_code_prefix: str
    seller_city: str
    seller_state: str


class SellerPage(BaseModel):
    total: int
    skip: int
    limit: int
    results: list[Seller]


class Product(BaseModel):
    product_id: str
    category: str
    category_english: str
    weight_g: float | None
    length_cm: float | None
    height_cm: float | None
    width_cm: float | None
    photos_qty: int | None


class ProductPage(BaseModel):
    total: int
    skip: int
    limit: int
    results: list[Product]


class OrderItem(BaseModel):
    product_id: str
    seller_id: str
    price: float
    freight_value: float


class Payment(BaseModel):
    payment_type: str
    installments: int
    value: float


class Review(BaseModel):
    score: int
    comment_title: str | None
    comment_message: str | None
    creation_date: datetime | None
    answer_timestamp: datetime | None


class Order(BaseModel):
    order_id: str
    customer_id: str
    status: str
    purchase_timestamp: datetime
    approved_at: datetime | None
    delivered_carrier_date: datetime | None
    delivered_customer_date: datetime | None
    estimated_delivery_date: datetime | None
    items: list[OrderItem]
    payments: list[Payment]
    review: Review | None
    items_count: int
    total_value: float


class OrderSummary(BaseModel):
    order_id: str
    customer_id: str
    status: str
    purchase_timestamp: datetime
    items_count: int
    total_value: float


class OrderSummaryPage(BaseModel):
    total: int
    skip: int
    limit: int
    results: list[OrderSummary]


class CategoryRevenue(BaseModel):
    category: str
    category_english: str
    orders_count: int
    items_count: int
    revenue: float


class SellerRevenue(BaseModel):
    seller_id: str
    orders_count: int
    items_count: int
    revenue: float


class MonthlyStats(BaseModel):
    month: str
    orders_count: int
    revenue: float
