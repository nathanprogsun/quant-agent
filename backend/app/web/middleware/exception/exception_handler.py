"""Exception handlers for FastAPI application."""

import re
from http import HTTPStatus

from fastapi.exception_handlers import (
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.app_logging import Level, get_logger
from app.common.exception import ApplicationError, ConflictResourceError

logger = get_logger()

# Pattern to extract column name from SQLite UNIQUE constraint error
UNIQUE_CONSTRAINT_PATTERN = re.compile(r"UNIQUE constraint failed: (\w+)\.(\w+)")


async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
    """Handle ApplicationError and its subclasses.

    Logs the error at ERROR level if 5xx, WARNING if 4xx.
    Returns JSON response with error details.

    Args:
        request: FastAPI request object.
        exc: ApplicationError instance.

    Returns:
        JSONResponse with error payload.
    """
    level = Level.ERROR if exc.http_code() >= HTTPStatus.INTERNAL_SERVER_ERROR else Level.WARNING
    error_response = exc.to_json_response()
    logger.opt(exception=exc).log(
        level,
        "application error",
        http_path=request.url.path,
        http_method=request.method,
        http_status=exc.http_code(),
        error_response_body=error_response.body,
        error_response_headers=error_response.headers,
    )
    return error_response


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle RequestValidationError from FastAPI.

    Returns 422 with validation error details.

    Args:
        request: FastAPI request object.
        exc: RequestValidationError instance.

    Returns:
        JSONResponse with validation error details.
    """
    error_response = await request_validation_exception_handler(request=request, exc=exc)
    logger.opt(exception=exc).warning(
        "request validation error",
        http_path=request.url.path,
        http_method=request.method,
        error_response_body=error_response.body,
        error_response_headers=error_response.headers,
    )
    return error_response


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    """Handle Starlette HTTPException.

    Logs at ERROR level for 5xx, WARNING for 4xx.

    Args:
        request: FastAPI request object.
        exc: StarletteHTTPException instance.

    Returns:
        Response (usually JSONResponse).
    """
    level = Level.ERROR if exc.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR else Level.WARNING
    error_response = JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )
    logger.opt(exception=exc).log(
        level,
        "http exception",
        http_path=request.url.path,
        http_method=request.method,
        http_status=exc.status_code,
        error_response_body=error_response.body,
        error_response_headers=error_response.headers,
    )
    return error_response


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Handle SQLAlchemy IntegrityError from database constraints.

    Converts database unique constraint violations to user-friendly
    application errors without exposing internal details.

    Args:
        request: FastAPI request object.
        exc: SQLAlchemy IntegrityError instance.

    Returns:
        JSONResponse with appropriate error payload.
    """
    logger.opt(exception=exc).warning(
        "database integrity error",
        http_path=request.url.path,
        http_method=request.method,
    )

    # Extract error message to determine the type of constraint violation
    error_message = str(exc)

    # Check for email uniqueness constraint
    if "users.email" in error_message or "email" in error_message.lower():
        app_error = ConflictResourceError("Email already exists")
    else:
        # Generic conflict error for other unique constraints
        app_error = ConflictResourceError("A resource with the same unique value already exists")

    return app_error.to_json_response()
