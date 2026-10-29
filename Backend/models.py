from sqlalchemy import ForeignKey, Integer, String, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, UTC
from database import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String)

    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False) # only set with harvest_scripts/make_admin.py, never through the api
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None) # set when a user with orders is "deleted", see delete_user
    image_file: Mapped[str | None] = mapped_column(String(200), default=None) # filename in media/profile_pics/, None means the default picture
    orders: Mapped[list["Order"]] = relationship(back_populates="user") # intentionally no cascade: orders are records to keep, users with orders are soft-deleted
    cart_items: Mapped[list["CartItem"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def image_path(self) -> str:
        # url the frontend can use as an <img> src, both folders are mounted in main.py
        if self.image_file:
            return f"/media/profile_pics/{self.image_file}"
        return "/static/profile_pics/default.jpg"


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String)
    price: Mapped[float] = mapped_column(Numeric(10, 2)) # active price (not fixed)
    image_url: Mapped[str] = mapped_column(String)
    gender: Mapped[str] = mapped_column(String)
    link: Mapped[str] = mapped_column(String) # the stockx link
    brand: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)


class OrderItem(Base):
    # table represents item that is ordered at time of purchase
    __tablename__ = "order_items"

    order_item_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fixed_price: Mapped[float] = mapped_column(Numeric(10, 2))
    item_name: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id")) # orders being the name of the table its from and not the name of the class it's from :(
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id")) # tying the item to where the product originally comes from

    order: Mapped["Order"] = relationship(back_populates="items") # incomplete
    product: Mapped["Product"] = relationship()


class CartItem(Base):
    # table represents a mutable queue before any order is made
    __tablename__ = "cart_items"

    cart_item_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    user: Mapped["User"] = relationship(back_populates="cart_items")
    product: Mapped["Product"] = relationship() # no point in having cart_items in product, but product will never actually hold
                                                # cart items... cart items just happen to be stored inside of product...


class Order(Base):
    __tablename__ = "orders"
    order_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    status: Mapped[str] = mapped_column(String, default="pending")
    total: Mapped[float] = mapped_column(Numeric(10, 2))
    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order") # sqlalchemy handles the list wrapper as a notice to return multiple rows, its pretty cool
    user: Mapped["User"] = relationship(back_populates="orders")


class PasswordResetToken(Base):
    # one row per emailed reset link, deleted once it's used or a newer one is requested
    __tablename__ = "password_reset_tokens"

    reset_token_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False) # sha256 hex of the emailed token, the raw token is never stored
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    user: Mapped["User"] = relationship(back_populates="reset_tokens")
