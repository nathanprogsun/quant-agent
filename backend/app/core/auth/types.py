from pydantic import BaseModel, EmailStr


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
    csrf_token: str


class AuthResponse(BaseModel):
    message: str
    user_id: str | None = None


class CSRFResponse(BaseModel):
    csrf_token: str
