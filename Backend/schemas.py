from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Pagination
class PaginatedResponse(BaseModel):
    # shared by every paginated list below, each subclass adds that page's items under its own key
    total: int # matching rows across every page, not just this one
    skip: int
    limit: int
    has_more: bool # true when another page exists after this one

class SneakerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True) # lets model_validate read a models.Product directly

    product_id: int
    name: str
    price: float
    image_url: str
    gender: str
    link: str
    brand: str
    description: str

class PaginatedProductsResponse(PaginatedResponse):
    products: list[SneakerResponse]

# letters, digits, _ and - only: usernames end up in frontend urls (/:username/cart),
# and soft-deleted users get "[deleted-<id>]", which this pattern can never produce, so a real user can't take it first
USERNAME_PATTERN = r"^[A-Za-z0-9_-]+$"

class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=50, pattern=USERNAME_PATTERN)
    email: EmailStr

class UserCreate(UserBase):
    password: str = Field(min_length=8)

class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    username: str
    image_file: str | None
    image_path: str # read from the User.image_path property

class UserPrivate(UserPublic):
    email: EmailStr

class UserUpdate(BaseModel):
    # password isn't here, it's changed through PATCH /me/password (ChangePasswordRequest)
    username: str | None = Field(default=None, min_length=1, max_length=50, pattern=USERNAME_PATTERN)
    email: EmailStr | None = Field(default=None)
    current_password: str | None = Field(default=None) # required to change email

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8) # same rule as UserCreate.password

class Token(BaseModel):
    access_token: str
    token_type: str

# Password reset
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str # the token from the emailed link's ?token= query param
    new_password: str = Field(min_length=8) # same rule as UserCreate.password

class MessageResponse(BaseModel):
    message: str

class CartItemBase(BaseModel):
    product_id: int

class CartItemCreate(CartItemBase):
    pass

class CartItemUpdate(BaseModel):
    quantity: int = Field(gt=0)

class CartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cart_item_id: int
    quantity: int
    product: SneakerResponse

class PaginatedCartItemsResponse(PaginatedResponse):
    cart_items: list[CartItemResponse]

class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_item_id: int
    product_id: int
    item_name: str
    fixed_price: float # price per item at time of purchase
    quantity: int

class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    status: str
    total: float # matches Order.total Numeric(10, 2), an int would reject totals with cents
    created_date: datetime
    items: list[OrderItemResponse]
    user: UserPublic

class PaginatedOrdersResponse(PaginatedResponse):
    orders: list[OrderResponse]

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
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    username: str
    email: EmailStr
    is_admin: bool
    deleted_at: datetime | None # set for soft-deleted users, see delete_user

class PaginatedAdminUsersResponse(PaginatedResponse):
    users: list[AdminUserResponse]

class AdminUserDetail(AdminUserResponse):
    orders: list[OrderResponse]
