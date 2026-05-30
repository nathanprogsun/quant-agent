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


@router.get("/me")
async def get_me(
    current_user: UserDTO = Depends(get_current_user),
) -> UserDTO:
    """Returns current authenticated user."""
    return current_user


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    request: Request,
    response: Response,
    req: RegisterRequest,
    auth_service: AuthService = Depends(auth_service_from_lifespan),
) -> AuthResponse:
    user = await auth_service.register_user(req.email, req.password, req.full_name)

    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "email": user.email},
        token_version=user.token_version,
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_https(request),
        samesite="lax",
        max_age=86400 * 7,  # 7 days
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

    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "email": user.email},
        token_version=user.token_version,
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_https(request),
        samesite="lax",
        max_age=86400 * 7,  # 7 days
    )

    return AuthResponse(message="Login successful", user_id=str(user.id))


@router.get("/signout", response_model=AuthResponse)
async def signout(request: Request, response: Response) -> AuthResponse:
    """Signs out user, clears session."""
    response.delete_cookie(key="access_token", secure=is_https(request), samesite="lax")
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
    success = await auth_service.change_password(
        current_user.id, req.old_password, req.new_password
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid old password"
        )

    # Increment token_version to invalidate old tokens
    await auth_service.user_service.update_token_version(current_user.id)

    # Refresh token after password change with new token_version
    access_token = auth_service.create_access_token(
        data={"sub": str(current_user.id), "email": current_user.email},
        token_version=current_user.token_version + 1,
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_https(request),
        samesite="lax",
        max_age=86400 * 7,
    )

    return AuthResponse(
        message="Password changed successfully", user_id=str(current_user.id)
    )


@router.post(
    "/initialize", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def initialize(
    request: Request,
    response: Response,
    req: RegisterRequest,
    auth_service: AuthService = Depends(auth_service_from_lifespan),
) -> AuthResponse:
    """Initialize the system by creating the first admin user."""
    user = await auth_service.initialize_system(req.email, req.password, req.full_name)

    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "email": user.email},
        token_version=user.token_version,
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_https(request),
        samesite="lax",
        max_age=86400 * 7,
    )

    return AuthResponse(message="System initialized", user_id=str(user.id))


@router.get("/setup-status")
async def setup_status(
    auth_service: AuthService = Depends(auth_service_from_lifespan),
) -> dict[str, bool]:
    """Check if the system needs initial setup (no users exist)."""
    count = await auth_service.user_service.count_users()
    return {"needs_setup": count == 0}
