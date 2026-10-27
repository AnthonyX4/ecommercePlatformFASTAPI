import asyncio
import sys

from conftest import BACKEND_DIR, TestAsyncSession, register_and_login

sys.path.insert(0, str(BACKEND_DIR / "harvest_scripts"))
from make_admin import set_admin


def run_set_admin(email: str, is_admin: bool = True) -> bool:
    """set_admin is async now, run it on its own session the way make_admin.py's main does."""
    async def run():
        async with TestAsyncSession() as session:
            return await set_admin(session, email, is_admin=is_admin)
    return asyncio.run(run())


def test_set_admin_promotes_user_and_unlocks_admin_routes(client):
    headers = register_and_login(client, "Boss@Example.com")
    assert client.get("/api/admin/users", headers=headers).status_code == 403

    assert run_set_admin("boss@example.com") is True # email match is case-insensitive

    assert client.get("/api/admin/users", headers=headers).status_code == 200


def test_set_admin_revoke(client):
    headers = register_and_login(client, "boss@example.com")
    run_set_admin("boss@example.com")

    assert run_set_admin("boss@example.com", is_admin=False) is True

    assert client.get("/api/admin/users", headers=headers).status_code == 403


def test_set_admin_unknown_email_returns_false(db):
    assert run_set_admin("nobody@example.com") is False
