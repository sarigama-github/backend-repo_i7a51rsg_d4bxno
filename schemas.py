"""
Database Schemas for eCommerce App

Each Pydantic model corresponds to a MongoDB collection with the lowercase
class name as the collection name.

Collections:
- category
- product
- deliverycharge
- adminsession (session tokens for admin auth)
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List

class Category(BaseModel):
    name: str = Field(..., description="Category display name")
    slug: str = Field(..., description="URL-friendly unique identifier for the category")
    description: Optional[str] = Field(None, description="Optional description for the category")
    is_active: bool = Field(True, description="Whether this category is active")

class Product(BaseModel):
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in your currency")
    category_slug: str = Field(..., description="Slug of the category this product belongs to")
    image_url: Optional[HttpUrl] = Field(None, description="Public URL to the product image")
    in_stock: bool = Field(True, description="Whether product is in stock")

class DeliveryRate(BaseModel):
    location: str = Field(..., description="Location/Zone name (e.g., Inside City, Outside City)")
    charge: float = Field(..., ge=0, description="Delivery charge for this location")

class DeliveryCharge(BaseModel):
    name: str = Field("Standard Delivery", description="Name of this delivery charge table")
    notes: Optional[str] = Field(None, description="Optional notes shown under the chart")
    rates: List[DeliveryRate] = Field(default_factory=list, description="List of delivery charges by location/zone")

# Admin session tokens stored in DB (no explicit Pydantic schema required for create/update)
