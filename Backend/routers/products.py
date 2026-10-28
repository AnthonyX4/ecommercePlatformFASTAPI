from typing import Annotated

# Fastapi
from fastapi import Depends, status, HTTPException, APIRouter, Query
# Database
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
import models

from config import settings

# Schemas
from schemas import PaginatedProductsResponse, SneakerResponse

router = APIRouter()

# GET, Access one page of sneakers (?skip= rows to skip, ?limit= rows to return)
@router.get(
    "",
    response_model=PaginatedProductsResponse
)
async def get_sneakers(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=settings.max_page_size)] = settings.products_per_page,
):
    count_result = await db.execute(select(func.count()).select_from(models.Product))
    total = count_result.scalar() or 0

    result = await db.execute(
        select(models.Product)
        .order_by(models.Product.product_id) # offset needs a fixed order, otherwise pages can repeat or miss rows
        .offset(skip)
        .limit(limit)
    )
    sneakers = result.scalars().all()

    has_more = skip + len(sneakers) < total

    return PaginatedProductsResponse(
        products=[SneakerResponse.model_validate(sneaker) for sneaker in sneakers],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )

# GET, Access a single sneaker
@router.get(
    "/{product_id}",
    response_model=SneakerResponse
)
async def get_sneaker(product_id: int, db: Annotated[AsyncSession, Depends(get_db)]):

    result = await db.execute(
        select(models.Product).where(models.Product.product_id == product_id)
    )
    existing_product = result.scalars().first()

    if not existing_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return existing_product
