import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR)) # so main/models/database are importable when pytest runs from anywhere

import database

# swap in a throwaway database BEFORE main is imported, main's lifespan create_all must never touch my_database.db
# it's a temp file rather than in-memory so two engines can share it:
#   - the app gets an async (aiosqlite) engine, same as production
#   - fixtures get a plain sync engine, so tests can set up and inspect data without an event loop
TEST_DB_DIR = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
TEST_DB_PATH = Path(TEST_DB_DIR.name) / "test.db"

# NullPool opens a fresh connection per session, so no connection is reused across the event loops
# TestClient and asyncio.run create (a pooled aiosqlite connection is tied to the loop that opened it)
test_async_engine = create_async_engine(
    f"sqlite+aiosqlite:///{TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
database.engine = test_async_engine
TestAsyncSession = async_sessionmaker(test_async_engine, class_=AsyncSession, expire_on_commit=False)

test_sync_engine = create_engine(f"sqlite:///{TEST_DB_PATH}", poolclass=NullPool)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_sync_engine)

import main
import models

PASSWORD = "password123"


async def get_test_db():
    async with TestAsyncSession() as db:
        yield db


@pytest.fixture
def db():
    # fresh tables for every test so tests can't leak data into each other
    database.Base.metadata.create_all(bind=test_sync_engine)
    with TestSession() as session:
        yield session
    database.Base.metadata.drop_all(bind=test_sync_engine)


@pytest.fixture
def client(db):
    main.app.dependency_overrides[database.get_db] = get_test_db
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


@pytest.fixture
def product(db):
    shoe = models.Product(
        name="Test Shoe", price=159.99, image_url="x", gender="men", link="x", brand="B", description="d"
    )
    db.add(shoe)
    db.commit()
    db.refresh(shoe)
    return shoe


def register_and_login(client, email: str) -> dict:
    """Create a user through the API and return headers carrying their token."""
    assert client.post("/api/users", json={"email": email, "password": PASSWORD}).status_code == 201
    response = client.post("/api/users/token", data={"username": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def user_headers(client):
    return register_and_login(client, "customer@example.com")


@pytest.fixture
def admin_headers(client, db):
    headers = register_and_login(client, "admin@example.com")
    # promoted directly in the db, the same way make_admin.py does, the api has no way to do this
    admin = db.execute(select(models.User).where(models.User.email == "admin@example.com")).scalars().one()
    admin.is_admin = True
    db.commit()
    return headers


def place_order(client, headers: dict, product_id: int) -> dict:
    """Add one product to the cart and check out, returns the order json."""
    assert client.post("/api/cart", json={"product_id": product_id}, headers=headers).status_code == 201
    response = client.post("/api/orders", headers=headers)
    assert response.status_code == 201
    return response.json()
