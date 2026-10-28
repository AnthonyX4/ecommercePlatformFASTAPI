from io import BytesIO

import pytest
from PIL import Image

import image_utils
import models
from config import settings
from conftest import place_order


@pytest.fixture(autouse=True)
def pics_dir(tmp_path, monkeypatch):
    # uploads go to a temp folder, never the real media/profile_pics
    monkeypatch.setattr(image_utils, "PROFILE_PICS_DIR", tmp_path)
    return tmp_path


def make_image(mode="RGB", size=(640, 480), fmt="PNG") -> bytes:
    buffer = BytesIO()
    Image.new(mode, size, "red").save(buffer, fmt)
    return buffer.getvalue()


def me(client, headers) -> dict:
    return client.get("/api/users/me", headers=headers).json()


def upload(client, headers, user_id, content, filename="pic.png"):
    return client.patch(
        f"/api/users/{user_id}/picture",
        files={"file": (filename, content, "image/png")},
        headers=headers,
    )


def test_new_user_has_default_picture(client, user_headers):
    user = me(client, user_headers)
    assert user["image_file"] is None
    assert user["image_path"] == "/static/profile_pics/default.jpg"


def test_upload_saves_300px_jpeg(client, user_headers, pics_dir):
    user_id = me(client, user_headers)["user_id"]

    response = upload(client, user_headers, user_id, make_image(mode="RGBA")) # RGBA has to be converted for jpeg
    assert response.status_code == 200
    body = response.json()
    assert body["image_file"].endswith(".jpg")
    assert body["image_path"] == f"/media/profile_pics/{body['image_file']}"

    with Image.open(pics_dir / body["image_file"]) as saved:
        assert saved.format == "JPEG"
        assert saved.size == (300, 300)


def test_replacing_picture_deletes_old_file(client, user_headers, pics_dir):
    user_id = me(client, user_headers)["user_id"]
    first = upload(client, user_headers, user_id, make_image()).json()["image_file"]
    second = upload(client, user_headers, user_id, make_image()).json()["image_file"]

    assert first != second
    assert not (pics_dir / first).exists()
    assert (pics_dir / second).exists()


def test_upload_rejects_non_image(client, user_headers, pics_dir):
    user_id = me(client, user_headers)["user_id"]
    response = upload(client, user_headers, user_id, b"not an image", filename="notes.txt")
    assert response.status_code == 400
    assert list(pics_dir.iterdir()) == []


def test_upload_rejects_too_large(client, user_headers, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)
    user_id = me(client, user_headers)["user_id"]
    response = upload(client, user_headers, user_id, make_image())
    assert response.status_code == 400
    assert "too large" in response.json()["detail"]


def test_cannot_upload_for_another_user(client, user_headers):
    user_id = me(client, user_headers)["user_id"]
    response = upload(client, user_headers, user_id + 1, make_image())
    assert response.status_code == 403


def test_upload_requires_auth(client):
    assert upload(client, {}, 1, make_image()).status_code == 401


def test_patch_user_ignores_image_file(client, user_headers):
    # image_file is deliberately not in UserUpdate, otherwise a user could point at
    # someone else's file and get it deleted on their next upload
    user_id = me(client, user_headers)["user_id"]
    response = client.patch(f"/api/users/{user_id}", json={"image_file": "someone-else.jpg"}, headers=user_headers)
    assert response.status_code == 200
    assert response.json()["image_file"] is None


def test_delete_picture(client, user_headers, pics_dir):
    user_id = me(client, user_headers)["user_id"]
    filename = upload(client, user_headers, user_id, make_image()).json()["image_file"]

    response = client.delete(f"/api/users/{user_id}/picture", headers=user_headers)
    assert response.status_code == 200
    assert response.json()["image_path"] == "/static/profile_pics/default.jpg"
    assert not (pics_dir / filename).exists()


def test_delete_picture_when_none(client, user_headers):
    user_id = me(client, user_headers)["user_id"]
    assert client.delete(f"/api/users/{user_id}/picture", headers=user_headers).status_code == 400


def test_hard_delete_user_removes_picture(client, user_headers, pics_dir):
    user_id = me(client, user_headers)["user_id"]
    filename = upload(client, user_headers, user_id, make_image()).json()["image_file"]

    assert client.delete(f"/api/users/{user_id}", headers=user_headers).status_code == 204
    assert not (pics_dir / filename).exists()


def test_soft_delete_user_removes_picture(client, user_headers, product, pics_dir, db):
    user_id = me(client, user_headers)["user_id"]
    place_order(client, user_headers, product.product_id) # having an order makes the delete a soft delete
    filename = upload(client, user_headers, user_id, make_image()).json()["image_file"]

    assert client.delete(f"/api/users/{user_id}", headers=user_headers).status_code == 204
    assert not (pics_dir / filename).exists()
    assert db.get(models.User, user_id).image_file is None
