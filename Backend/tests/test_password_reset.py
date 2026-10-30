import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

import models
from auth import hash_reset_token
from config import settings
from conftest import PASSWORD, place_order

EMAIL = "customer@example.com" # the user_headers fixture's user
NEW_PASSWORD = "newpassword456"


def request_reset(client, email=EMAIL):
    return client.post("/api/users/forgot-password", json={"email": email})


def token_from(email: dict) -> str:
    # reads the raw token back out of the emailed link, the same way the react page reads it from the url
    match = re.search(r"/reset-password\?token=([\w-]+)", email["plain_text"])
    assert match
    return match.group(1)


def reset(client, token, new_password=NEW_PASSWORD):
    return client.post("/api/users/reset-password", json={"token": token, "new_password": new_password})


def login(client, password, email=EMAIL):
    return client.post("/api/users/token", data={"username": email, "password": password})


def me(client, headers) -> dict:
    return client.get("/api/users/me", headers=headers).json()


def reset_tokens(db) -> list:
    return db.execute(select(models.PasswordResetToken)).scalars().all()


def test_forgot_password_emails_a_reset_link(client, user_headers, outbox):
    response = request_reset(client)
    assert response.status_code == 202

    assert len(outbox) == 1
    sent = outbox[0]
    assert sent["to_email"] == EMAIL
    link = f"{settings.frontend_url}/reset-password?token={token_from(sent)}"
    assert link in sent["plain_text"]
    assert link in sent["html_content"] # the jinja template rendered
    assert f"{settings.reset_token_expire_minutes} minutes" in sent["html_content"]


def test_only_the_token_hash_is_stored(client, user_headers, outbox, db):
    request_reset(client)
    token = token_from(outbox[0])

    row = reset_tokens(db)[0]
    assert row.token_hash == hash_reset_token(token)
    assert row.token_hash != token


def test_unknown_email_gets_the_same_response_and_no_email(client, user_headers, outbox):
    known = request_reset(client)
    unknown = request_reset(client, "nobody@example.com")

    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
    assert len(outbox) == 1 # only the registered address got one


def test_email_lookup_is_case_insensitive(client, user_headers, outbox):
    request_reset(client, EMAIL.upper())
    assert [sent["to_email"] for sent in outbox] == [EMAIL]


def test_reset_changes_the_password(client, user_headers, outbox):
    request_reset(client)

    response = reset(client, token_from(outbox[0]))
    assert response.status_code == 200

    assert login(client, NEW_PASSWORD).status_code == 200
    assert login(client, PASSWORD).status_code == 401


def test_token_is_single_use(client, user_headers, outbox):
    request_reset(client)
    token = token_from(outbox[0])

    assert reset(client, token).status_code == 200
    assert reset(client, token, "anotherpassword").status_code == 400


def test_new_request_invalidates_the_old_link(client, user_headers, outbox):
    request_reset(client)
    request_reset(client)
    old_token, new_token = token_from(outbox[0]), token_from(outbox[1])

    assert reset(client, old_token).status_code == 400
    assert reset(client, new_token).status_code == 200


def test_expired_token_is_rejected_and_deleted(client, user_headers, outbox, db):
    request_reset(client)
    db.execute(update(models.PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    db.commit()

    response = reset(client, token_from(outbox[0]))
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired reset token"
    assert reset_tokens(db) == []
    assert login(client, PASSWORD).status_code == 200 # password unchanged


def test_unknown_token_is_rejected(client, user_headers):
    assert reset(client, "not-a-real-token").status_code == 400


def test_short_new_password_is_rejected(client, user_headers, outbox):
    request_reset(client)
    assert reset(client, token_from(outbox[0]), "short").status_code == 422


def test_changing_password_kills_a_pending_link(client, user_headers, outbox):
    request_reset(client)

    response = client.patch(
        "/api/users/me/password",
        json={"current_password": PASSWORD, "new_password": "changedpass789"},
        headers=user_headers,
    )
    assert response.status_code == 200

    assert reset(client, token_from(outbox[0])).status_code == 400
    assert login(client, "changedpass789").status_code == 200


def test_soft_deleted_user_cannot_reset(client, user_headers, product, outbox, db):
    user_id = me(client, user_headers)["user_id"]
    place_order(client, user_headers, product.product_id) # having orders makes the delete a soft delete
    request_reset(client) # a link that's still pending when the account is deleted

    assert client.delete(f"/api/users/{user_id}", headers=user_headers).status_code == 204
    assert reset_tokens(db) == []
    assert reset(client, token_from(outbox[0])).status_code == 400

    # neither the old address nor the anonymized one gets a new link
    request_reset(client, EMAIL)
    request_reset(client, f"deleted-{user_id}@invalid.example")
    assert len(outbox) == 1


def test_hard_delete_removes_pending_tokens(client, user_headers, outbox, db):
    user_id = me(client, user_headers)["user_id"]
    request_reset(client)

    assert client.delete(f"/api/users/{user_id}", headers=user_headers).status_code == 204
    assert reset_tokens(db) == []
