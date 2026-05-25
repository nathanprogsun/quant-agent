"""Common lifespan utilities for FastAPI dependency injection."""

from typing import Annotated

from fastapi import Depends
from httpx import AsyncClient
from starlette.requests import Request

from app.db.dbengine.core import DatabaseEngine


def get_db_engine(request: Request) -> DatabaseEngine:
    """Retrieve DatabaseEngine from app context singleton.

    Args:
        request: FastAPI request object.

    Returns:
        DatabaseEngine instance.

    Raises:
        RuntimeError: If app context is not set up.
    """
    app_context = getattr(request.app.state, "app_context", None)
    if app_context is None:
        raise RuntimeError("App context not initialized. Call setup_app_context() first.")
    return app_context.main_db


def get_http_aclient(request: Request) -> AsyncClient:
    """Retrieve shared HTTP AsyncClient from app context singleton.

    Args:
        request: FastAPI request object.

    Returns:
        AsyncClient instance.

    Raises:
        RuntimeError: If app context is not set up.
    """
    app_context = getattr(request.app.state, "app_context", None)
    if app_context is None:
        raise RuntimeError("App context not initialized. Call setup_app_context() first.")
    return app_context.http_aclient


# Type aliases for dependency injection
DbEngineDep = Annotated[DatabaseEngine, Depends(get_db_engine)]
HttpClientDep = Annotated[AsyncClient, Depends(get_http_aclient)]
