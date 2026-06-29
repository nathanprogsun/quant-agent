from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class AuthResponse(BaseModel):
    message: str
    user_id: str | None = None


class TokenClaims(BaseModel):
    """Claims for JWT token creation/decoding."""

    sub: UUID
    email: EmailStr
    model_config = ConfigDict(extra="allow")


class SetupStatusResponse(BaseModel):
    """Response payload for /auth/setup-status — public, no auth required."""

    needs_setup: bool


