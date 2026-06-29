"""Create an admin user in the database.

Usage:
    uv run python scripts/create_admin_user.py
    uv run python scripts/create_admin_user.py --email admin@example.com
    uv run python scripts/create_admin_user.py --password my-secret
    uv run python scripts/create_admin_user.py --email admin@example.com --password my-secret
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from passlib.context import CryptContext

from app.core.user.service.user_service import UserService
from app.core.user.types import UserCreateWithHashDTO
from app.db.models import Base
from app.db.session import make_engine, make_session_factory
from app.settings import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEFAULT_EMAIL = "admin@test.com"
DEFAULT_PASSWORD = "admin123"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an admin user")
    parser.add_argument(
        "--email",
        default=DEFAULT_EMAIL,
        help=f"Admin email (default: {DEFAULT_EMAIL})",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help=f"Admin password (default: {DEFAULT_PASSWORD})",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    cfg = get_settings()

    # Build engine and session factory
    engine = make_engine(url=str(cfg.database_url), echo=False)
    session_factory = make_session_factory(engine)

    # Ensure schema exists
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Hash password and create admin user
    hashed = pwd_context.hash(args.password)
    dto = UserCreateWithHashDTO(
        email=args.email,
        hashed_password=hashed,
        full_name="Admin",
    )

    async with session_factory() as session:
        service = UserService(session=session)
        try:
            user = await service.create_admin_user(dto)
            await session.commit()
            print("Admin user created successfully:")
            print(f"  ID:       {user.id}")
            print(f"  Email:    {user.email}")
            print(f"  Name:     {user.full_name}")
            print(f"  Superuser: {user.is_superuser}")
            print(f"  Active:   {user.is_active}")
        except Exception as exc:
            print(f"Failed to create admin user: {exc}")
            sys.exit(1)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
