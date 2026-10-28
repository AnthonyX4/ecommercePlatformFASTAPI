from typing import Annotated

# Fastapi
from fastapi import Depends, status, HTTPException, APIRouter, Query
# Database
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import func, select
import models

from config import settings

# Dependencies
from auth import CurrentUser

# Schemas
from schemas import OrderResponse, PaginatedOrdersResponse

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

# GET, Access one page of a user's orders, newest first
@router.get(
    "",
    response_model=PaginatedOrdersResponse,
)
async def get_orders(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=settings.max_page_size)] = settings.items_per_page,
):

    count_result = await db.execute(
        select(func.count())
        .select_from(models.Order)
        .where(models.Order.user_id == user.user_id)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(models.Order)
        .options(selectinload(models.Order.items), selectinload(models.Order.user))
        .where(models.Order.user_id == user.user_id)
        .order_by(models.Order.created_date.desc(), models.Order.order_id.desc()) # order_id breaks ties between orders made in the same instant
        .offset(skip)
        .limit(limit)
    )
    orders = result.scalars().all()

    has_more = skip + len(orders) < total

    return PaginatedOrdersResponse(
        orders=[OrderResponse.model_validate(order) for order in orders],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )

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
