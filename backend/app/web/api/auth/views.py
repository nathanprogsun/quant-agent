from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.auth.service.auth_service import AuthService
from app.core.auth.types import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
)
from app.core.user.types import UserDTO
from app.web.api.deps import get_current_user
from app.web.lifespan_service import auth_service_from_lifespan

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def is_https(request: Request) -> bool:
    return request.url.scheme == "https"


def validate_csrf(request: Request, csrf_token: str) -> bool:
    """Validate CSRF token from cookie matches provided token."""
    cookie_token = request.cookies.get("csrf_token")
    return cookie_token == csrf_token


@router.get("/me")
async def get_me(current_user: UserDTO = Depends(get_current_user)) -> dict[str, str | None]:
    """Returns current user's JWT claims."""
    return {
        "sub": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
    }


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    response: Response,
    req: RegisterRequest,
    auth_service: AuthService = Depends(auth_service_from_lifespan),
) -> AuthResponse:
    user = await auth_service.register_user(req.email, req.password, req.full_name)

    access_token = auth_service.create_access_token(data={"sub": str(user.id), "email": user.email})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_https(request),
        samesite="lax",
        max_age=86400 * 7,  # 7 days
    )

    csrf_token = auth_service.create_csrf_token()
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=is_https(request),
        samesite="lax",
    )

    return AuthResponse(message="Registration successful", user_id=str(user.id))


@router.post("/login", response_model=AuthResponse)
async def login(
    request: Request,
    response: Response,
    req: LoginRequest,
    auth_service: AuthService = Depends(auth_service_from_lifespan),
) -> AuthResponse:
    user = await auth_service.authenticate_user(req.email, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = auth_service.create_access_token(data={"sub": str(user.id), "email": user.email})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_https(request),
        samesite="lax",
        max_age=86400 * 7,  # 7 days
    )

    csrf_token = auth_service.create_csrf_token()
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=is_https(request),
        samesite="lax",
    )

    return AuthResponse(message="Login successful", user_id=str(user.id))


@router.get("/signout", response_model=AuthResponse)
async def signout(request: Request, response: Response) -> AuthResponse:
    """Signs out user, clears session."""
    response.delete_cookie(key="access_token", secure=is_https(request), samesite="lax")
    response.delete_cookie(key="csrf_token", secure=is_https(request), samesite="lax")
    return AuthResponse(message="Logout successful")


@router.post("/change-password", response_model=AuthResponse)
async def change_password(
    request: Request,
    response: Response,
    req: ChangePasswordRequest,
    auth_service: AuthService = Depends(auth_service_from_lifespan),
    current_user: UserDTO = Depends(get_current_user),
) -> AuthResponse:
    """Change password for authenticated user."""
    # Validate CSRF
    if not validate_csrf(request, req.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    success = await auth_service.change_password(
        current_user.id, req.old_password, req.new_password
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid old password")

    # Refresh token after password change
    access_token = auth_service.create_access_token(
        data={"sub": str(current_user.id), "email": current_user.email}
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_https(request),
        samesite="lax",
        max_age=86400 * 7,
    )

    return AuthResponse(message="Password changed successfully", user_id=str(current_user.id))


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(auth_service_from_lifespan),
) -> dict[str, str]:
    """Refresh access token."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = auth_service.decode_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    email = payload.get("email")

    new_token = auth_service.create_access_token(data={"sub": user_id, "email": email})
    response.set_cookie(
        key="access_token",
        value=new_token,
        httponly=True,
        secure=is_https(request),
        samesite="lax",
        max_age=86400 * 7,
    )

    return {"access_token": new_token, "token_type": "bearer"}
