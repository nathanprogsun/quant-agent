"""User types."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserDTO(BaseModel):
    """User data transfer object."""

    id: UUID
    email: str
    username: str | None = None
    full_name: str | None = None
    is_active: bool = True
    is_superuser: bool = False
    created_at: datetime
    updated_at: datetime | None = None

    @property
    def display_name(self) -> str:
        return self.full_name or self.username or self.email

    model_config = {"from_attributes": True}


class UserCreateDTO(BaseModel):
    """User creation data transfer object."""

    email: EmailStr
    username: str | None = None
    full_name: str | None = None
    password: str


class UserUpdateDTO(BaseModel):
    """User update data transfer object."""

    email: EmailStr | None = None
    username: str | None = None
    full_name: str | None = None
    is_active: bool | None = None
