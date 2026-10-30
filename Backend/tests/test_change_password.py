from conftest import PASSWORD

EMAIL = "customer@example.com" # the user_headers fixture's user
NEW_PASSWORD = "newpassword456"


def change_password(client, headers, current_password=PASSWORD, new_password=NEW_PASSWORD):
    return client.patch(
        "/api/users/me/password",
        json={"current_password": current_password, "new_password": new_password},
        headers=headers,
    )


def login(client, password, email=EMAIL):
    return client.post("/api/users/token", data={"username": email, "password": password})


def test_change_password(client, user_headers):
    response = change_password(client, user_headers)
    assert response.status_code == 200
    assert response.json() == {"message": "Password changed successfully."}

    assert login(client, PASSWORD).status_code == 401
    assert login(client, NEW_PASSWORD).status_code == 200


def test_wrong_current_password_is_rejected(client, user_headers):
    assert change_password(client, user_headers, current_password="wrongpassword").status_code == 400
    assert login(client, PASSWORD).status_code == 200


def test_short_new_password_is_rejected(client, user_headers):
    assert change_password(client, user_headers, new_password="short").status_code == 422


def test_change_password_requires_login(client, user_headers):
    assert change_password(client, headers={}).status_code == 401


def test_profile_update_no_longer_changes_password(client, user_headers):
    user_id = client.get("/api/users/me", headers=user_headers).json()["user_id"]

    response = client.patch(
        f"/api/users/{user_id}",
        json={"password": NEW_PASSWORD, "current_password": PASSWORD},
        headers=user_headers,
    )
    assert response.status_code == 200 # unknown fields are ignored, not an error
    assert login(client, PASSWORD).status_code == 200
    assert login(client, NEW_PASSWORD).status_code == 401


def test_email_change_still_requires_current_password(client, user_headers):
    user_id = client.get("/api/users/me", headers=user_headers).json()["user_id"]

    response = client.patch(
        f"/api/users/{user_id}",
        json={"email": "new@example.com"},
        headers=user_headers,
    )
    assert response.status_code == 403
