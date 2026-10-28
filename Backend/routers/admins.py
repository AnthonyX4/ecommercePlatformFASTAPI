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
from auth import get_current_admin

# Schemas
from schemas import (
    AdminUserDetail,
    AdminUserResponse,
    OrderResponse,
    OrderStatus,
    OrderStatusUpdate,
    PaginatedAdminUsersResponse,
    PaginatedOrdersResponse,
)

# the dependency on the router itself protects every route below, a new route can't forget the admin check
router = APIRouter(dependencies=[Depends(get_current_admin)])

# which status an order may move to from its current one, anything not listed is rejected
ALLOWED_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}

# GET, Access one page of users (soft-deleted users included unless filtered out)
@router.get(
    "/users",
    response_model=PaginatedAdminUsersResponse,
)
async def get_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    include_deleted: bool = True,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=settings.max_page_size)] = settings.items_per_page,
):

    query = select(models.User)
    count_query = select(func.count()).select_from(models.User)
    if not include_deleted:
        query = query.where(models.User.deleted_at.is_(None))
        count_query = count_query.where(models.User.deleted_at.is_(None)) # total must use the same filter as the page

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    result = await db.execute(query.order_by(models.User.user_id).offset(skip).limit(limit))
    users = result.scalars().all()

    has_more = skip + len(users) < total

    return PaginatedAdminUsersResponse(
        users=[AdminUserResponse.model_validate(user) for user in users],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )

# GET, Access a single user and all of their orders
@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetail,
)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(
        select(models.User)
        .options(
            selectinload(models.User.orders).options( # each order in OrderResponse also needs its items and user
                selectinload(models.Order.items),
                selectinload(models.Order.user),
            )
        )
        .where(models.User.user_id == user_id)
    )
    existing_user = result.scalars().first()

    if not existing_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return existing_user

# GET, Access one page of every user's orders, newest first, optionally only one status
@router.get(
    "/orders",
    response_model=PaginatedOrdersResponse,
)
async def get_orders(
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[OrderStatus | None, Query(alias="status")] = None, # still ?status= in the url, renamed so it doesn't shadow fastapi's status module
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=settings.max_page_size)] = settings.items_per_page,
):

    query = (
        select(models.Order)
        .options(selectinload(models.Order.items), selectinload(models.Order.user))
        .order_by(models.Order.created_date.desc(), models.Order.order_id.desc()) # order_id breaks ties between orders made in the same instant
    )
    count_query = select(func.count()).select_from(models.Order)
    if status_filter is not None:
        query = query.where(models.Order.status == status_filter)
        count_query = count_query.where(models.Order.status == status_filter) # total must use the same filter as the page

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    result = await db.execute(query.offset(skip).limit(limit))
    orders = result.scalars().all()

    has_more = skip + len(orders) < total

    return PaginatedOrdersResponse(
        orders=[OrderResponse.model_validate(order) for order in orders],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )

# PATCH, Move an order to its next status
@router.patch(
    "/orders/{order_id}/status",
    response_model=OrderResponse,
)
async def update_order_status(order_id: int, update: OrderStatusUpdate, db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(
        select(models.Order)
        .options(selectinload(models.Order.items), selectinload(models.Order.user))
        .where(models.Order.order_id == order_id)
    )
    existing_order = result.scalars().first()

    if not existing_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    current_status = OrderStatus(existing_order.status)
    if update.status not in ALLOWED_TRANSITIONS[current_status]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change order from {current_status} to {update.status}",
        )

    existing_order.status = update.status
    await db.commit()
    await db.refresh(existing_order, attribute_names=["items", "user"])

    return existing_order
