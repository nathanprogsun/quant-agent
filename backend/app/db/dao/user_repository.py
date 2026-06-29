"""User ORM repository."""
from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception.exception import ConflictResourceError
from app.db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_email(self, email: str) -> User | None:
        return cast(
            User | None,
            await self.session.scalar(select(User).where(User.email == email)),
        )

    async def find_by_id(self, user_id: UUID) -> User | None:
        return cast(User | None, await self.session.get(User, user_id))

    async def create(self, user: User) -> User:
        try:
            self.session.add(user)
            await self.session.flush()
            await self.session.refresh(user)
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictResourceError("User already exists") from exc
        return user

    async def update(self, user: User) -> User:
        """Update an existing user.

        Caller is expected to have mutated the user instance. We exclude
        created_at to preserve audit semantics (mirrors old
        _audit_immune_columns={"created_at"}).
        """
        data = user.__dict__.copy()
        data.pop("created_at", None)
        data.pop("_sa_instance_state", None)
        try:
            await self.session.execute(
                update(User).where(User.id == user.id).values(**data)
            )
            await self.session.refresh(user)
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictResourceError("User update conflicts with existing data") from exc
        return user

    async def delete(self, user_id: UUID, *, soft: bool = True) -> None:
        user = await self.session.get(User, user_id)
        if user is None:
            return
        if soft:
            user.is_active = False
            await self.session.flush()
        else:
            await self.session.delete(user)
            await self.session.flush()

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[User]:
        result = await self.session.execute(select(User).limit(limit).offset(offset))
        return list(result.scalars())

    async def count_all(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(User)) or 0

    async def count_active(self) -> int:
        return await self.session.scalar(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        ) or 0

    async def bump_token_version(self, user_id: UUID) -> bool:
        result = await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(token_version=User.token_version + 1)
            .returning(User.id)
        )
        return result.scalar_one_or_none() is not None
