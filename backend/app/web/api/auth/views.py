from fastapi import APIRouter, Depends, Request, Response, status

from app.core.auth.service.auth_service import AuthService
from app.core.auth.types import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenClaims,
)
from app.core.user.types import UserDTO
from app.web.api.deps import get_current_user
from app.web.lifespan_service import auth_service_from_request

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])



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
    auth_service: AuthService = Depends(auth_service_from_request),
) -> AuthResponse:
    user = await auth_service.register_user(req.email, req.password, req.full_name)

    access_token = auth_service.create_access_token(
        data=TokenClaims(sub=user.id, email=user.email),
        token_version=user.token_version,
    )
    # Set httponly access_token cookie on the response
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=86400 * 7,
    )

    return AuthResponse(message="Registration successful", user_id=str(user.id))


@router.post("/login", response_model=AuthResponse)
async def login(
    request: Request,
    response: Response,
    req: LoginRequest,
    auth_service: AuthService = Depends(auth_service_from_request),
) -> AuthResponse:
    user = await auth_service.authenticate_user(req.email, req.password)

    access_token = auth_service.create_access_token(
        data=TokenClaims(sub=user.id, email=user.email),
        token_version=user.token_version,
    )
    # Set httponly access_token cookie on the response
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=86400 * 7,
    )


    return AuthResponse(message="Login successful", user_id=str(user.id))


@router.get("/signout", response_model=AuthResponse)
async def signout(request: Request, response: Response) -> AuthResponse:
    """Signs out user, clears session."""
    response.delete_cookie(key="access_token", secure=request.url.scheme == "https", samesite="lax")
    return AuthResponse(message="Logout successful")


@router.post("/change-password", response_model=AuthResponse)
async def change_password(
    request: Request,
    response: Response,
    req: ChangePasswordRequest,
    auth_service: AuthService = Depends(auth_service_from_request),
    current_user: UserDTO = Depends(get_current_user),
) -> AuthResponse:
    """Change password for authenticated user."""
    claims, new_token_version = await auth_service.change_password_and_emit_claims(
        current_user.id, req.old_password, req.new_password
    )

    # Refresh token after password change with new (bumped) token_version
    access_token = auth_service.create_access_token(
        data=claims,
        token_version=new_token_version,
    )
    # Set httponly access_token cookie on the response
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=86400 * 7,
    )


    return AuthResponse(
        message="Password changed successfully", user_id=str(current_user.id)
    )


