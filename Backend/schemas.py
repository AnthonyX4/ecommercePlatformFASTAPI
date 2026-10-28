from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field

class SneakerResponse(BaseModel):
    product_id: int
    name: str
    price: float
    image_url: str
    gender: str
    link: str
    brand: str
    description: str

class UserBase(BaseModel):
    email: EmailStr
    # add username attribute

class UserCreate(UserBase):
    password: str = Field(min_length=8)

class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    image_file: str | None
    image_path: str # read from the User.image_path property

class UserPrivate(UserPublic):
    email: EmailStr

class UserUpdate(BaseModel):
    email: EmailStr | None = Field(default=None)
    password: str | None = Field(default=None, min_length=8)
    current_password: str | None = Field(default=None) # required to change email or password

class Token(BaseModel):
    access_token: str
    token_type: str

class CartItemBase(BaseModel):
    product_id: int

class CartItemCreate(CartItemBase):
    pass

class CartItemUpdate(BaseModel):
    quantity: int = Field(gt=0)

class CartItemResponse(BaseModel):
    cart_item_id: int
    quantity: int
    product: SneakerResponse

class OrderItemResponse(BaseModel):
    order_item_id: int
    product_id: int
    item_name: str
    fixed_price: float # price per item at time of purchase
    quantity: int

class OrderResponse(BaseModel):
    order_id: int
    status: str
    total: float # matches Order.total Numeric(10, 2), an int would reject totals with cents
    created_date: datetime
    items: list[OrderItemResponse]
    user: UserPublic

# Admin
class OrderStatus(StrEnum):
    # stored as plain strings in Order.status, the allowed changes between them live in routers/admins.py
    PENDING = "pending"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class OrderStatusUpdate(BaseModel):
    status: OrderStatus # anything else is rejected with a 422

class AdminUserResponse(BaseModel):
    user_id: int
    email: EmailStr
    is_admin: bool
    deleted_at: datetime | None # set for soft-deleted users, see delete_user

class AdminUserDetail(AdminUserResponse):
    orders: list[OrderResponse]
