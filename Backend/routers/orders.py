from typing import Annotated

# Fastapi
from fastapi import Depends, status, HTTPException, APIRouter
# Database
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
import models

# Dependencies
from auth import CurrentUser

# Schemas
from schemas import OrderResponse

router = APIRouter()

# POST, Checkout cart items (creates an order from the user's cart)
@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def checkout_cart(user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):

    # if cart_items is empty, dont checkout
    result = await db.execute(
        select(models.CartItem)
        .options(selectinload(models.CartItem.product))
        .where(models.CartItem.user_id == user.user_id)
    )
    cart_items = result.scalars().all()

    if not cart_items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")

    total = sum(cart_item.product.price * cart_item.quantity for cart_item in cart_items)

    # add order to database
    new_order = models.Order(
        user_id=user.user_id,
        total=total,
    )
    db.add(new_order)
    await db.flush()  # populate new_order.order_id for the order items below

    # add order items to database, delete cart items from database
    for cart_item in cart_items:
        db.add(models.OrderItem(
            order_id=new_order.order_id,
            product_id=cart_item.product_id,
            item_name=cart_item.product.name,
            fixed_price=cart_item.product.price,
            quantity=cart_item.quantity,
        ))
        await db.delete(cart_item)

    await db.commit()
    await db.refresh(new_order, attribute_names=["items", "user"])

    return new_order

# GET, Access all of a user's orders
@router.get(
    "",
    response_model=list[OrderResponse],
)
async def get_orders(user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(
        select(models.Order)
        .options(selectinload(models.Order.items), selectinload(models.Order.user))
        .where(models.Order.user_id == user.user_id)
    )
    orders = result.scalars().all()

    return orders

# GET, Access a single order
@router.get(
    "/{order_id}",
    response_model=OrderResponse,
)
async def get_order(order_id: int, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(
        select(models.Order)
        .options(selectinload(models.Order.items), selectinload(models.Order.user))
        .where(models.Order.order_id == order_id)
        .where(models.Order.user_id == user.user_id)
    )
    existing_order = result.scalars().first()

    if not existing_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return existing_order
