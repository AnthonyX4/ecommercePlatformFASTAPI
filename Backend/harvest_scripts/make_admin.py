"""
    Promotes an existing user to admin (or takes it away with --revoke).
    The api has no endpoint for this on purpose, otherwise anyone could make themselves an admin.

    usage (from Backend/):
        uv run python harvest_scripts/make_admin.py <email>
        uv run python harvest_scripts/make_admin.py <email> --revoke
"""
import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR)) # so database/models are importable regardless of cwd

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal, engine
import models


async def set_admin(db: AsyncSession, email: str, is_admin: bool = True) -> bool:
    """Set is_admin on the active user with this email, returns False if there is no such user."""
    result = await db.execute(
        select(models.User)
        .where(func.lower(models.User.email) == email.lower())
        .where(models.User.deleted_at.is_(None))
    )
    user = result.scalars().first()

    if not user:
        return False

    user.is_admin = is_admin
    await db.commit()
    return True


async def main(email: str, is_admin: bool) -> bool:
    async with AsyncSessionLocal() as db:
        found = await set_admin(db, email, is_admin=is_admin)
    await engine.dispose() # close the connection before asyncio.run shuts the event loop down
    return found


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grant or revoke admin access for a user.")
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true", help="remove admin access instead of granting it")
    args = parser.parse_args()

    if not asyncio.run(main(args.email, is_admin=not args.revoke)):
        sys.exit(f"No active user with email {args.email}, register them first ❌")

    print(f"{args.email} is {'no longer' if args.revoke else 'now'} an admin ✅")
