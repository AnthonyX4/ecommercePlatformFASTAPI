import pytest

import models
from config import settings
from conftest import place_order, register_and_login


@pytest.fixture
def products(db):
    """Five products, enough to split across pages with a small limit."""
    shoes = [
        models.Product(
            name=f"Shoe {i}", price=100 + i, image_url="x", gender="men", link="x", brand="B", description="d"
        )
        for i in range(5)
    ]
    db.add_all(shoes)
    db.commit()
    return [shoe.product_id for shoe in shoes]


def collect_pages(client, path: str, key: str, limit: int, headers: dict | None = None) -> list[dict]:
    """Walk every page of a paginated endpoint by following has_more, returns every row in order."""
    rows, skip = [], 0
    while True:
        page = client.get(path, params={"skip": skip, "limit": limit}, headers=headers).json()
        rows += page[key]
        if not page["has_more"]:
            return rows
        skip += limit


# --- products ---

def test_products_page_reports_total_and_has_more(client, products):
    response = client.get("/api/products", params={"skip": 0, "limit": 2})
    assert response.status_code == 200
    page = response.json()
    assert [p["product_id"] for p in page["products"]] == products[:2]
    assert page["total"] == 5
    assert page["skip"] == 0
    assert page["limit"] == 2
    assert page["has_more"] is True


def test_products_last_page_has_no_more(client, products):
    page = client.get("/api/products", params={"skip": 4, "limit": 2}).json()
    assert [p["product_id"] for p in page["products"]] == products[4:]
    assert page["has_more"] is False


def test_products_pages_cover_every_product_once(client, products):
    rows = collect_pages(client, "/api/products", "products", limit=2)
    assert [p["product_id"] for p in rows] == products


def test_products_skip_past_the_end_is_an_empty_page(client, products):
    page = client.get("/api/products", params={"skip": 50}).json()
    assert page["products"] == []
    assert page["total"] == 5
    assert page["has_more"] is False


def test_products_default_limit_comes_from_settings(client, products):
    assert client.get("/api/products").json()["limit"] == settings.products_per_page


@pytest.mark.parametrize("params", [{"skip": -1}, {"limit": 0}, {"limit": settings.max_page_size + 1}])
def test_products_out_of_range_params_are_422(client, params):
    assert client.get("/api/products", params=params).status_code == 422


# --- home ---

def test_home_returns_first_page_of_products(client, products):
    response = client.get("/")
    assert response.status_code == 200
    page = response.json()
    assert page == client.get("/api/products", params={"skip": 0, "limit": settings.products_per_page}).json()


# --- cart ---

def test_cart_pages_cover_every_item_oldest_first(client, user_headers, products):
    for product_id in products:
        assert client.post("/api/cart", json={"product_id": product_id}, headers=user_headers).status_code == 201

    rows = collect_pages(client, "/api/cart", "cart_items", limit=2, headers=user_headers)
    assert [item["product"]["product_id"] for item in rows] == products


def test_cart_total_only_counts_the_callers_items(client, user_headers, products):
    other_headers = register_and_login(client, "other@example.com")
    client.post("/api/cart", json={"product_id": products[0]}, headers=user_headers)
    client.post("/api/cart", json={"product_id": products[1]}, headers=other_headers)
    client.post("/api/cart", json={"product_id": products[2]}, headers=other_headers)

    page = client.get("/api/cart", headers=user_headers).json()
    assert page["total"] == 1
    assert [item["product"]["product_id"] for item in page["cart_items"]] == [products[0]]


# --- orders ---

def test_orders_pages_cover_every_order_newest_first(client, user_headers, products):
    placed = [place_order(client, user_headers, product_id)["order_id"] for product_id in products]

    rows = collect_pages(client, "/api/orders", "orders", limit=2, headers=user_headers)
    assert [o["order_id"] for o in rows] == placed[::-1]
    assert rows[0]["items"][0]["fixed_price"] == 104 # nested items still serialize through model_validate


# --- admin ---

def test_admin_users_total_respects_include_deleted(client, admin_headers, user_headers, products):
    place_order(client, user_headers, products[0]) # having an order makes delete a soft delete
    me = client.get("/api/users/me", headers=user_headers).json()
    client.delete(f"/api/users/{me['user_id']}", headers=user_headers)

    everyone = client.get("/api/admin/users", params={"limit": 1}, headers=admin_headers).json()
    assert everyone["total"] == 2
    assert everyone["has_more"] is True

    active = client.get("/api/admin/users", params={"include_deleted": False}, headers=admin_headers).json()
    assert active["total"] == 1
    assert active["has_more"] is False


def test_admin_orders_total_respects_status_filter(client, admin_headers, user_headers, products):
    shipped = place_order(client, user_headers, products[0])
    place_order(client, user_headers, products[1])
    place_order(client, user_headers, products[2])
    client.patch(f"/api/admin/orders/{shipped['order_id']}/status", json={"status": "shipped"}, headers=admin_headers)

    page = client.get("/api/admin/orders", params={"status": "pending", "limit": 1}, headers=admin_headers).json()
    assert page["total"] == 2
    assert page["has_more"] is True
    assert len(page["orders"]) == 1
