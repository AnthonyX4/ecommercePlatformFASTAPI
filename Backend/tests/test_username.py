import pytest

from conftest import PASSWORD, place_order, register_and_login


def register(client, username, email="new@example.com"):
    return client.post("/api/users", json={"username": username, "email": email, "password": PASSWORD})


def me(client, headers) -> dict:
    return client.get("/api/users/me", headers=headers).json()


def rename(client, headers, username):
    return client.patch(f"/api/users/{me(client, headers)['user_id']}", json={"username": username}, headers=headers)


def test_register_stores_username_as_typed(client, db):
    response = register(client, "Sneaker_Head-1")
    assert response.status_code == 201
    assert response.json()["username"] == "Sneaker_Head-1"


def test_username_is_required(client, db):
    response = client.post("/api/users", json={"email": "new@example.com", "password": PASSWORD})
    assert response.status_code == 422


@pytest.mark.parametrize("username", ["", "a" * 51, "has space", "[deleted-1]", "me@home"])
def test_invalid_usernames_are_rejected(client, db, username):
    assert register(client, username).status_code == 422


def test_duplicate_username_is_rejected_ignoring_case(client, user_headers):
    # user_headers registered "customer"
    response = register(client, "CUSTOMER")
    assert response.status_code == 409
    assert response.json()["detail"] == "Username already exists"


def test_username_is_public(client, user_headers):
    user_id = me(client, user_headers)["user_id"]
    assert client.get(f"/api/users/{user_id}").json()["username"] == "customer"


def test_change_username(client, user_headers):
    response = rename(client, user_headers, "newname")
    assert response.status_code == 200 # no current_password needed, it isn't a credential
    assert response.json()["username"] == "newname"


def test_change_only_the_case_of_your_own_username(client, user_headers):
    response = rename(client, user_headers, "Customer")
    assert response.status_code == 200
    assert response.json()["username"] == "Customer"


def test_cannot_take_another_users_username(client, user_headers):
    register_and_login(client, "other@example.com") # registers as "other"
    response = rename(client, user_headers, "Other")
    assert response.status_code == 409
    assert me(client, user_headers)["username"] == "customer"


def test_soft_delete_frees_the_username(client, user_headers, product):
    user_id = me(client, user_headers)["user_id"]
    place_order(client, user_headers, product.product_id) # having orders makes the delete a soft delete
    assert client.delete(f"/api/users/{user_id}", headers=user_headers).status_code == 204

    # the old row was anonymized, so the name can be registered again
    assert register(client, "customer").status_code == 201


def test_reset_email_greets_the_user_by_username(client, user_headers, outbox):
    client.post("/api/users/forgot-password", json={"email": "customer@example.com"})
    assert "Hi customer," in outbox[0]["plain_text"]
    assert "Hi customer," in outbox[0]["html_content"]
