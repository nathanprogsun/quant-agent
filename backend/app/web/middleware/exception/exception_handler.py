"""Exception handlers for FastAPI application."""

import logging
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

from app.app_logging import get_logger
from app.common.exception import ApplicationError, ConflictResourceError

logger = get_logger(__name__)

# Pattern to extract column name from SQLite UNIQUE constraint error
UNIQUE_CONSTRAINT_PATTERN = re.compile(r"UNIQUE constraint failed: (\w+)\.(\w+)")


async def application_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle ApplicationError and its subclasses.

    Logs the error at ERROR level if 5xx, WARNING if 4xx.
    Returns JSON response with error details.

    Args:
        request: FastAPI request object.
        exc: ApplicationError instance.

    Returns:
        JSONResponse with error payload.
    """
    assert isinstance(exc, ApplicationError)
    level = (
        logging.ERROR
        if exc.http_code() >= HTTPStatus.INTERNAL_SERVER_ERROR
        else logging.WARNING
    )
    error_response = exc.to_json_response()
    logger.log(
        level,
        "application error path=%s method=%s status=%s",
        request.url.path,
        request.method,
        exc.http_code(),
        exc_info=exc,
    )
    return error_response


async def request_validation_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle RequestValidationError from FastAPI.

    Returns 422 with validation error details. Signature accepts
    `Exception` to match Starlette's `add_exception_handler` protocol;
    `isinstance` narrows the type at runtime.

    Args:
        request: FastAPI request object.
        exc: RequestValidationError instance.

    Returns:
        JSONResponse with validation error details.
    """
    assert isinstance(exc, RequestValidationError)
    error_response = await request_validation_exception_handler(request=request, exc=exc)
    logger.warning(
        "request validation error path=%s method=%s",
        request.url.path,
        request.method,
        exc_info=exc,
    )
    return error_response


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    """Handle Starlette HTTPException.

    Logs at ERROR level for 5xx, WARNING for 4xx. Signature accepts
    `Exception` to match Starlette's `add_exception_handler` protocol;
    `isinstance` narrows the type at runtime.

    Args:
        request: FastAPI request object.
        exc: Starlette HTTPException instance.

    Returns:
        Response (usually JSONResponse).
    """
    assert isinstance(exc, StarletteHTTPException)
    level = (
        logging.ERROR
        if exc.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
        else logging.WARNING
    )
    error_response = JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )
    logger.log(
        level,
        "http exception path=%s method=%s status=%s",
        request.url.path,
        request.method,
        exc.status_code,
        exc_info=exc,
    )
    return error_response


async def integrity_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle SQLAlchemy IntegrityError from database constraints.

    Converts database unique constraint violations to user-friendly
    application errors without exposing internal details. Signature
    accepts `Exception` to match Starlette's `add_exception_handler`
    protocol; `isinstance` narrows the type at runtime.

    Args:
        request: FastAPI request object.
        exc: SQLAlchemy IntegrityError instance.

    Returns:
        JSONResponse with appropriate error payload.
    """
    assert isinstance(exc, IntegrityError)
    logger.warning(
        "database integrity error path=%s method=%s",
        request.url.path,
        request.method,
        exc_info=exc,
    )

    error_message = str(exc)

    match = UNIQUE_CONSTRAINT_PATTERN.search(error_message)
    if match:
        _, column = match.groups()
        if column == "email":
            app_error = ConflictResourceError("Email already exists")
        else:
            app_error = ConflictResourceError(f"Duplicate value for column: {column}")
    else:
        app_error = ConflictResourceError("A resource with the same unique value already exists")

    return app_error.to_json_response()
