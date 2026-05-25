"""Lifespan service dependency injection helpers.

Provides functions to extract services from LifeSpanService
for FastAPI Depends() injection.
"""

from typing import Annotated

from fastapi import Depends
from starlette.requests import Request

from app.app_context.app_context import LifeSpanService
from app.common.exception import IllegalStateError
from app.core.user.service.user_service import UserService


def get_lifespan_service(request: Request) -> LifeSpanService:
    """Retrieves LifeSpanService instance from app context singleton."""
    _life_span_service = request.app.state.app_context.lifespan_service
    if not isinstance(_life_span_service, LifeSpanService):
        raise IllegalStateError(
            f"expected lifespan_service to be of type {LifeSpanService}, "
            f"but got {type(_life_span_service)}"
        )
    return _life_span_service


def user_service_from_lifespan(
    lifespan_service: Annotated[LifeSpanService, Depends(get_lifespan_service)],
) -> UserService:
    return lifespan_service.user_service
