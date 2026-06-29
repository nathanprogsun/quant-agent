"""Exception classes."""

from abc import ABC, abstractmethod
from http import HTTPStatus
from typing import Any

from pydantic import BaseModel
from starlette.responses import JSONResponse

from app.app_logging import get_logger

logger = get_logger()


class ErrorDetails(BaseModel):
    """Placeholder exception details, such that in the future we can
    pass along a set of predefined backend error code to enrich
    beyond vanilla http status code.
    """

    code: str
    details: str = ""
    reference_id: str | None = None


class ApplicationError(Exception, ABC):
    """Base application error."""

    error_code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred"

    def __init__(
        self,
        *args: Any,
        additional_error_details: ErrorDetails | None = None,
    ):
        super().__init__(*args)
        self.additional_error_details = additional_error_details

    @abstractmethod
    def http_code(self) -> int: ...

    def to_json_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.http_code(),
            content={
                "error": {
                    "code": self.error_code,
                    "message": str(self),
                    "details": self.additional_error_details.model_dump(mode="json")
                    if self.additional_error_details
                    else None,
                }
            },
        )


class DatabaseError(ApplicationError):
    error_code = "DB_ERROR"

    def http_code(self) -> int:
        return HTTPStatus.INTERNAL_SERVER_ERROR


class ConcurrentModificationError(ApplicationError):
    error_code = "CONCURRENT_MODIFICATION"

    def http_code(self) -> int:
        return HTTPStatus.CONFLICT


class ResourceNotFoundError(ApplicationError):
    error_code = "RESOURCE_NOT_FOUND"

    def http_code(self) -> int:
        return HTTPStatus.NOT_FOUND


class InvalidArgumentError(ApplicationError):
    error_code = "INVALID_ARGUMENT"

    def http_code(self) -> int:
        return HTTPStatus.BAD_REQUEST


class ConflictResourceError(ApplicationError):
    error_code = "CONFLICT"

    def http_code(self) -> int:
        return HTTPStatus.CONFLICT


class IllegalStateError(ApplicationError):
    error_code = "ILLEGAL_STATE"

    def http_code(self) -> int:
        return HTTPStatus.INTERNAL_SERVER_ERROR


class ServiceError(ApplicationError):
    error_code = "SERVICE_ERROR"

    def http_code(self) -> int:
        return HTTPStatus.INTERNAL_SERVER_ERROR


class UnauthorizedError(ApplicationError):
    error_code = "UNAUTHORIZED"

    def http_code(self) -> int:
        return HTTPStatus.UNAUTHORIZED


class ForbiddenError(ApplicationError):
    error_code = "FORBIDDEN"

    def http_code(self) -> int:
        return HTTPStatus.FORBIDDEN


class ClientError(ApplicationError):
    error_code = "CLIENT_ERROR"

    def http_code(self) -> int:
        return HTTPStatus.BAD_REQUEST


class ExternalServiceError(ApplicationError):
    """External service error with original error preservation.

    This exception wraps errors from external services (APIs, databases, etc.)
    and preserves the original HTTP status code and error code for debugging.

    Prevents leaking vendor information to clients.
    """

    error_code = "EXTERNAL_SERVICE_ERROR"

    def __init__(
        self,
        *args: Any,
        original_http_code: int | None = None,
        original_error_code: str | None = None,
        additional_error_details: ErrorDetails | None = None,
    ):
        """Initialize ExternalServiceError.

        Args:
            *args: Positional arguments passed to Exception.
            original_http_code: The original HTTP status code from the external service.
            original_error_code: The original error code from the external service.
            additional_error_details: Additional error details for enriched responses.
        """
        # NOTE: We want to preserve/translate the original http code in some cases
        #   but if the callsite does not specify a http code, the default is 500
        self._original_http_code = original_http_code or HTTPStatus.INTERNAL_SERVER_ERROR
        self._original_error_code = original_error_code

        # Extract original error code from additional_error_details if not provided
        if not self._original_error_code and additional_error_details:
            self._original_error_code = additional_error_details.code

        # With our sentry loguru config, this should be sent to Sentry as well
        if self._original_http_code < HTTPStatus.INTERNAL_SERVER_ERROR:
            logger.warning(
                "External service bad request: %s",
                additional_error_details.model_dump(mode="python")
                if additional_error_details
                else {},
            )
        else:
            logger.error(
                "External service error: %s",
                additional_error_details.model_dump(mode="python")
                if additional_error_details
                else {},
            )

        # Provide user-friendly error message to the client
        # This prevents leaking internal vendor information
        user_friendly_error_details = None
        if additional_error_details:
            user_friendly_error_details = ErrorDetails(
                code="SERVICE_ERROR",
                details="An error occurred. Please try again later.",
                reference_id=additional_error_details.reference_id,
            )

        super().__init__(*args, additional_error_details=user_friendly_error_details)

    def http_code(self) -> int:
        """Return HTTP status code for this error.

        Returns the original HTTP code from the external service if available,
        otherwise defaults to INTERNAL_SERVER_ERROR (500).

        Always returns 500 to prevent leaking vendor error codes to clients.
        """
        return HTTPStatus.INTERNAL_SERVER_ERROR

    def get_original_http_code(self) -> int | None:
        """Get the original HTTP status code from the external service.

        Returns:
            The original HTTP status code, or None if not available.
        """
        return self._original_http_code

    def get_original_error_code(self) -> str | None:
        """Get the original error code from the external service.

        Returns:
            The original error code string, or None if not available.
        """
        return self._original_error_code


class RequestEntityTooLargeError(ApplicationError):
    error_code = "REQUEST_ENTITY_TOO_LARGE"

    def http_code(self) -> int:
        return HTTPStatus.REQUEST_ENTITY_TOO_LARGE


class UnprocessableEntity(ApplicationError):
    error_code = "UNPROCESSABLE_ENTITY"

    def http_code(self) -> int:
        return HTTPStatus.UNPROCESSABLE_ENTITY
