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
