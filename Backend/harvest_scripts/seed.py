"""
    This file is going to do some seeding.. we are going to fill up the Product table in the database.
    There is currently nothing in it, so we need to make the sneakers.json data usable.
"""
import asyncio
import json # so python can interact with the JSON
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR)) # so database/models are importable regardless of cwd

from sqlalchemy import select, func

from database import AsyncSessionLocal, engine, Base # the stuff we need from the database
from models import Product # the actual table we need to work with

async def seedDB (): # async only because the database engine is async now, it still runs once, separate from the main application
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all) # will check the database and create anything that hasn't been created yet

    with open(BACKEND_DIR / 'sneakers.json', 'r', encoding='utf-8') as file:
        sneaker_data = json.load(file) # the data exists outside of this block (I'm too Java brained, scope is different in python)

    print("Beginning the seeding, stand by... 🌱")

    async with AsyncSessionLocal() as db: # closes the session for us when the block ends
        # running the seed twice would add every sneaker again, so only seed an empty table
        existing = await db.scalar(select(func.count()).select_from(Product))
        if existing:
            print(f"Products table already has {existing} rows, skipping seed 🛑")
            await engine.dispose()
            return

        for sneaker in sneaker_data:
            product = Product(
                name=sneaker.get("title"),
                brand=sneaker.get("brand"),
                price=float(sneaker.get("lowest_ask") or sneaker.get("avg_price") or 0), # lowest_ask is the current lowest StockX price (as of the harvest), the api sends prices as strings
                image_url=sneaker.get("image_url"),
                gender=sneaker.get("gender") or "unisex",
                description=sneaker.get("description") or "", # some products have no description, the column can't be null
                link=sneaker.get("link")
            )
            db.add(product)
            print(f"Successfully added {sneaker.get("title")} to the DB ✅")
        await db.commit()

    await engine.dispose() # close the connection before asyncio.run shuts the event loop down

if __name__ == "__main__":
    asyncio.run(seedDB())
