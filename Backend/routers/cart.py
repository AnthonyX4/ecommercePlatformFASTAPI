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
from schemas import CartItemResponse, CartItemCreate, CartItemUpdate

router = APIRouter()

# lookup shared by PATCH and DELETE: the cart item must exist and belong to the caller
async def get_cart_item_or_404(cart_item_id: int, user: models.User, db: AsyncSession) -> models.CartItem:
    result = await db.execute(
        select(models.CartItem)
        .where(models.CartItem.cart_item_id == cart_item_id)
        .where(models.CartItem.user_id == user.user_id)
    )
    existing_cart_item = result.scalars().first()

    if not existing_cart_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

    return existing_cart_item

# GET, Access items in cart
@router.get(
    "",
    response_model=list[CartItemResponse],
)
async def get_cart_items(user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(
        select(models.CartItem)
        .options(selectinload(models.CartItem.product))
        .where(models.CartItem.user_id == user.user_id)
    )
    cart_items = result.scalars().all()

    return cart_items

# POST, Add item to cart
@router.post(
    "",
    response_model=CartItemResponse,
    status_code=status.HTTP_201_CREATED
)
async def add_item_to_cart(item: CartItemCreate, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):

    # verify item.product_id is an actual product (not sure if necessary)
    result = await db.execute(
        select(models.Product)
        .where(models.Product.product_id == item.product_id)
    )
    existing_product = result.scalars().first()

    if not existing_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # if item exists in cart, increase quantity by 1
    result = await db.execute(
        select(models.CartItem)
        .where(models.CartItem.user_id == user.user_id)
        .where(models.CartItem.product_id == item.product_id)
    )
    existing_cart_item = result.scalars().first()

    if existing_cart_item:
        existing_cart_item.quantity += 1
        await db.commit()
        await db.refresh(existing_cart_item, attribute_names=["product"]) # the response only needs product, user was never returned
        return existing_cart_item

    # add item to database
    new_item = models.CartItem(
        user_id=user.user_id,
        product_id=item.product_id,
        quantity=1
    )

    db.add(new_item) # add only stages the object, it doesn't touch the database so it isn't awaited
    await db.commit()
    await db.refresh(new_item, attribute_names=["product"])

    return new_item

# PATCH, Edit item in cart
@router.patch(
    "/{cart_item_id}",
    response_model=CartItemResponse,
)
async def update_cart_item(cart_item_id: int, item: CartItemUpdate, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):

    existing_cart_item = await get_cart_item_or_404(cart_item_id, user, db)

    existing_cart_item.quantity = item.quantity
    await db.commit()
    await db.refresh(existing_cart_item, attribute_names=["product"])

    return existing_cart_item

# DELETE, Delete item in cart
@router.delete(
    "/{cart_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_cart_item(cart_item_id: int, user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):

    existing_cart_item = await get_cart_item_or_404(cart_item_id, user, db)

    await db.delete(existing_cart_item)
    await db.commit()

# DELETE, Delete all items in cart
@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_all_cart_items(user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(
        select(models.CartItem).where(models.CartItem.user_id == user.user_id)
    )
    cart_items = result.scalars().all()

    for cart_item in cart_items:
        await db.delete(cart_item)

    await db.commit()
