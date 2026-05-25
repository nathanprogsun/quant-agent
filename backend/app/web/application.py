"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError

from app.settings import get_settings
from app.web.api.auth.views import router as auth_router
from app.web.lifespan import lifespan
from app.web.middleware.auth_middleware import AuthMiddleware
from app.web.middleware.exception.exception_handler import (
    integrity_error_handler,
)


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    cfg = get_settings()

    app = FastAPI(
        title=cfg.app_name,
        description="app API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_allow_origins,
        allow_credentials=cfg.cors_allow_credentials,
        allow_methods=cfg.cors_allow_methods,
        allow_headers=cfg.cors_allow_headers,
    )

    # Add auth middleware
    app.add_middleware(AuthMiddleware)

    # Register exception handlers
    app.add_exception_handler(IntegrityError, integrity_error_handler)

    # Include routers
    app.include_router(auth_router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


def get_app() -> FastAPI:
    """Get FastAPI application instance.

    Returns:
        FastAPI application instance.
    """
    return create_app()


# Create global app instance for uvicorn
app = get_app()
