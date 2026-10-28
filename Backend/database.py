from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DB_PATH = Path(__file__).resolve().parent / "my_database.db" # anchored to Backend/ so the db resolves the same regardless of cwd
SQLITE_ALCHEMY_LINK = f"sqlite+aiosqlite:///{DB_PATH}" # aiosqlite is the async driver for sqlite

# connect sqlalchemy to database
engine = create_async_engine(
    SQLITE_ALCHEMY_LINK,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False, # keep attributes loaded after commit, an expired attribute would need a lazy load (not allowed in async)
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db

"""
uuid is used to generate unique file names
BytesIO is used for working wit image bytes in memory (without saving to disk)
Path for file operations
Image is used for main image 
Image OPS for image operations

JPEG require standard RGB mode, so convert to RGB if the image is in a different mode (like RGBA or P)


useful design pattern:

if we deleted profile picture first and database update fails, we have no way to restore the old image path and the user will have no profile picture

alternative is to delete the old image after the database update is successful, but then we have a temporary duplicate image on disk until the next time the user updates their profile picture

"""