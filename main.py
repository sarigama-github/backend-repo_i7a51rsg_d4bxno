import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Category, Product, DeliveryCharge

app = FastAPI(title="eCommerce Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Utilities
# -------------------------

class ObjectIdStr(str):
    pass


def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def serialize_doc(doc: dict) -> dict:
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    # Convert datetimes to isoformat
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


# -------------------------
# Auth (Admin)
# -------------------------

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password123")
SESSION_TTL_HOURS = int(os.getenv("ADMIN_SESSION_TTL_HOURS", "24"))

class LoginInput(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str
    expires_at: datetime


def require_admin(x_admin_token: Optional[str] = Header(None)):
    if not x_admin_token:
        raise HTTPException(status_code=401, detail="Missing admin token")
    session = db["adminsession"].find_one({"token": x_admin_token})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")
    if session.get("expires_at") and session["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    return True


@app.post("/api/admin/login", response_model=LoginResponse)
def admin_login(payload: LoginInput):
    if payload.username != ADMIN_USERNAME or payload.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = uuid4().hex
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=SESSION_TTL_HOURS)
    db["adminsession"].insert_one({
        "token": token,
        "created_at": now,
        "expires_at": expires_at,
    })
    return LoginResponse(token=token, expires_at=expires_at)


# -------------------------
# Health & test
# -------------------------

@app.get("/")
def read_root():
    return {"message": "eCommerce Backend Running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response


# -------------------------
# Categories (public list, admin manage)
# -------------------------

@app.get("/api/categories")
def list_categories():
    items = get_documents("category")
    return [serialize_doc(it) for it in items]

class CategoryCreate(Category):
    pass

@app.post("/api/admin/categories")
def create_category(payload: CategoryCreate, authorized: bool = Depends(require_admin)):
    # Ensure slug uniqueness
    existing = db["category"].find_one({"slug": payload.slug})
    if existing:
        raise HTTPException(status_code=400, detail="Slug already exists")
    new_id = create_document("category", payload)
    doc = db["category"].find_one({"_id": ObjectId(new_id)})
    return serialize_doc(doc)

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

@app.put("/api/admin/categories/{id}")
def update_category(id: str, payload: CategoryUpdate, authorized: bool = Depends(require_admin)):
    data = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "slug" in data:
        existing = db["category"].find_one({"slug": data["slug"], "_id": {"$ne": to_object_id(id)}})
        if existing:
            raise HTTPException(status_code=400, detail="Slug already exists")
    res = db["category"].update_one({"_id": to_object_id(id)}, {"$set": data, "$currentDate": {"updated_at": True}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    doc = db["category"].find_one({"_id": to_object_id(id)})
    return serialize_doc(doc)

@app.delete("/api/admin/categories/{id}")
def delete_category(id: str, authorized: bool = Depends(require_admin)):
    res = db["category"].delete_one({"_id": to_object_id(id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"success": True}


# -------------------------
# Products (public list/detail, admin manage)
# -------------------------

@app.get("/api/products")
def list_products(category_slug: Optional[str] = None):
    query = {"in_stock": {"$ne": False}}
    if category_slug:
        query["category_slug"] = category_slug
    items = list(db["product"].find(query).sort("created_at", -1))
    return [serialize_doc(it) for it in items]

@app.get("/api/products/{id}")
def get_product(id: str):
    doc = db["product"].find_one({"_id": to_object_id(id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return serialize_doc(doc)

class ProductCreate(Product):
    pass

@app.post("/api/admin/products")
def create_product(payload: ProductCreate, authorized: bool = Depends(require_admin)):
    # Ensure category exists
    cat = db["category"].find_one({"slug": payload.category_slug})
    if not cat:
        raise HTTPException(status_code=400, detail="Category does not exist")
    new_id = create_document("product", payload)
    doc = db["product"].find_one({"_id": ObjectId(new_id)})
    return serialize_doc(doc)

class ProductUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category_slug: Optional[str] = None
    image_url: Optional[str] = None
    in_stock: Optional[bool] = None

@app.put("/api/admin/products/{id}")
def update_product(id: str, payload: ProductUpdate, authorized: bool = Depends(require_admin)):
    data = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "category_slug" in data:
        cat = db["category"].find_one({"slug": data["category_slug"]})
        if not cat:
            raise HTTPException(status_code=400, detail="Category does not exist")
    res = db["product"].update_one({"_id": to_object_id(id)}, {"$set": data, "$currentDate": {"updated_at": True}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    doc = db["product"].find_one({"_id": to_object_id(id)})
    return serialize_doc(doc)

@app.delete("/api/admin/products/{id}")
def delete_product(id: str, authorized: bool = Depends(require_admin)):
    res = db["product"].delete_one({"_id": to_object_id(id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"success": True}


# -------------------------
# Delivery charges (public get, admin set)
# -------------------------

@app.get("/api/delivery")
def get_delivery():
    doc = db["deliverycharge"].find_one(sort=[("created_at", -1)])
    if not doc:
        return None
    return serialize_doc(doc)

class DeliveryUpsert(DeliveryCharge):
    pass

@app.post("/api/admin/delivery")
def set_delivery(payload: DeliveryUpsert, authorized: bool = Depends(require_admin)):
    # Insert a new chart; latest created wins
    new_id = create_document("deliverycharge", payload)
    doc = db["deliverycharge"].find_one({"_id": ObjectId(new_id)})
    return serialize_doc(doc)
