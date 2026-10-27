from typing import Annotated

# Fastapi
from fastapi import Depends, status, HTTPException, APIRouter
# Database
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import models

# Schemas
from schemas import SneakerResponse

router = APIRouter()

# GET, Access all sneakers
@router.get(
    "",
    response_model=list[SneakerResponse]
)
async def get_sneakers(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.Product))
    sneakers = result.scalars().all()
    return sneakers

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
