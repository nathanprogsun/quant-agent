"""User repository with domain-specific operations.

Extends GenericRepository with user-specific queries
and business-oriented create/update/delete methods.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from app.common.exception import ConflictResourceError, ResourceNotFoundError
from app.db.dao.generic_repository import GenericRepository
from app.db.dbengine.core import DatabaseEngine
from app.db.models.user import User


class UserRepository(GenericRepository):
    """Repository for user operations.

    Provides both generic CRUD via GenericRepository and
    domain-specific operations like find_by_email.
    """

    def __init__(self, engine: DatabaseEngine) -> None:
        """Initialize UserRepository.

        Args:
            engine: DatabaseEngine for query execution.
        """
        super().__init__(engine=engine)

    # ── Domain-specific find methods ──────────────────────────────────────────

    async def find_by_email(self, email: str) -> User | None:
        """Find user by email address.

        Args:
            email: Email address to search for.

        Returns:
            User if found, None otherwise.
        """
        stmt = text("""
            SELECT * FROM "users"
            WHERE email = :email
        """).bindparams(email=email)
        row = await self.engine.at_most_one(stmt)
        return User.from_row(row) if row else None

    async def find_by_id(self, user_id: UUID) -> User | None:
        """Find user by ID.

        Args:
            user_id: User UUID.

        Returns:
            User if found, None otherwise.
        """
        stmt = text("""
            SELECT * FROM "users"
            WHERE id = :id
        """).bindparams(id=str(user_id))
        row = await self.engine.at_most_one(stmt)
        return User.from_row(row) if row else None

    # ── Business-oriented CRUD wrappers ────────────────────────────────────────

    async def create(self, user: User) -> User:
        """Create a new user.

        Checks for email uniqueness before inserting.

        Args:
            user: User object to create.

        Returns:
            Created User object.

        Raises:
            ConflictResourceError: If email already exists.
        """
        # Check for duplicate email
        existing = await self.find_by_email(user.email)
        if existing:
            raise ConflictResourceError(f"Email already registered: {user.email}")

        # Use generic insert
        return await self.insert(user)

    async def update(self, user: User) -> User:
        """Update an existing user.

        Args:
            user: User object with updated values.

        Returns:
            Updated User object.

        Raises:
            ResourceNotFoundError: If user not found.
        """
        result = await self.update_instance(user)
        if result is None:
            raise ResourceNotFoundError(f"User {user.id} not found")
        return result

    async def delete(self, user_id: UUID, *, soft: bool = True) -> None:
        """Delete a user.

        Args:
            user_id: ID of user to delete.
            soft: If True, set is_active = False.
                  If False, permanently remove the record.
        """
        if soft:
            stmt = text("""
                UPDATE "users"
                SET is_active = :is_active
                WHERE id = :id
            """).bindparams(id=user_id, is_active=False)
            await self.engine.execute(stmt)
        else:
            stmt = text('DELETE FROM "users" WHERE id = :id').bindparams(id=user_id)
            await self.engine.execute(stmt)

    # ── Count methods ──────────────────────────────────────────────────────────

    async def count_all(self) -> int:
        """Count total users.

        Returns:
            Total user count.
        """
        stmt = text('SELECT COUNT(*) FROM "users"')
        row = await self.engine.one(stmt)
        return row[0] if row else 0

    async def count_active(self) -> int:
        """Count active users.

        Returns:
            Active user count.
        """
        stmt = text('SELECT COUNT(*) FROM "users" WHERE is_active = true')
        row = await self.engine.one(stmt)
        return row[0] if row else 0
