"""Application logging setup using loguru.

Provides structured logging with trace ID / span ID enrichment,
OpenTelemetry integration, and intercept handlers for standard logging.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import sys
import types
from enum import StrEnum
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast
from uuid import UUID

import orjson
from loguru import logger as _logger
from loguru._logger import Logger
from loguru._recattrs import RecordException
from opentelemetry.sdk.trace.id_generator import RandomIdGenerator
from opentelemetry.trace import INVALID_SPAN, INVALID_SPAN_CONTEXT, get_current_span
from pydantic import BaseModel

from app.util.traceback_utils import ExceptionDictTransformer

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = [
    "Level",
    "Logger",
    "get_logger",
    "log_context",
    "patch_gunicorn_logger",
    "patch_uvicorn_logger",
]


def is_in_k8s() -> bool:
    """Check if running inside Kubernetes."""
    return os.getenv("KUBERNETES_SERVICE_HOST") is not None


def is_singular_safe_serializable(v: object) -> bool:
    """Check if value is a simple JSON-safe type."""
    return isinstance(v, str | int | float | bool | types.NoneType | UUID)


def to_safe_serializable(v: object) -> Any:
    """Convert value to JSON-safe representation."""
    if isinstance(v, BaseModel):
        try:
            return v.model_dump(mode="json")
        except Exception:
            return str(v)
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        try:
            return dataclasses.asdict(v)
        except Exception:
            return v
    if is_singular_safe_serializable(v):
        return v
    if isinstance(v, (list, tuple, set)):
        return [to_safe_serializable(i) for i in v]
    if isinstance(v, dict):
        return {str(k): to_safe_serializable(v) for k, v in v.items()}
    return str(v)


EXCLUDED_PACKAGES = {"aiokafka"}


class InterceptHandler(logging.Handler):
    """Intercept standard logging and pass to loguru.

    From loguru documentation - enables compatibility with libraries
    that use standard logging instead of loguru.
    """

    def __init__(self, level: int = logging.NOTSET, _logger: Logger | None = None):
        super().__init__(level)
        self._logger = _logger or _logger

    def emit(self, record: logging.LogRecord) -> None:
        """Propagate log record to loguru."""
        if record.name.split(".")[0] in EXCLUDED_PACKAGES:
            return

        try:
            level: str | int = self._logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        self._logger.opt(depth=depth).opt(exception=record.exc_info).log(
            level,
            record.getMessage(),
            name=record.name,
            _lineno=record.lineno,
            _funcname=record.funcName,
        )


def record_dict_enricher(record: dict[str, Any]) -> None:
    """Enrich log record with trace/span IDs from OpenTelemetry."""
    span = get_current_span()
    id_generator = RandomIdGenerator()
    record["extra"]["span_id"] = str(id_generator.generate_span_id())
    record["extra"]["trace_id"] = str(id_generator.generate_trace_id())
    if span != INVALID_SPAN:
        span_context = span.get_span_context()
        if span_context != INVALID_SPAN_CONTEXT:
            record["extra"]["span_id"] = str(format(span_context.span_id, "016x"))
            record["extra"]["trace_id"] = str(format(span_context.trace_id, "032x"))

    record["extra"] = {k: to_safe_serializable(v) for k, v in record["extra"].items()}
    record["extra"]["serialized"] = serialize_record_dict(record)


def serialize_any(val: Any) -> str | dict[str, Any]:
    """Serialize value to JSON string."""
    try:
        if isinstance(val, BaseModel):
            return val.model_dump(mode="json")
        return orjson.dumps(val, default=str).decode()
    except Exception:
        return orjson.dumps(val, default=str).decode()


def serialize_record_dict(record: dict[str, Any]) -> str:
    """Serialize log record dict to JSON string."""
    record_extra = {**record["extra"]} if isinstance(record["extra"], dict) else {}
    name = record_extra.pop("name", record["name"])
    line = record_extra.pop("_lineno", record["line"])
    function_name = record_extra.pop("_funcname", record["function"])
    default_map_to_log = {
        "message": record["message"],
        "name": name,
        "lineno": line,
        "function_name": function_name,
        "level": record["level"].name,
        "timestamp": record["time"].timestamp() * 1000,
        "time": record["time"].isoformat(),
        "thread_id": record["thread"].id,
        "thread_name": record["thread"].name,
        "process_id": record["process"].id,
    }
    map_to_log = {**default_map_to_log, "extra": record_extra}

    try:
        exc_val = record.get("exception")
        if exc_val and isinstance(exc_val, RecordException):
            transformer = ExceptionDictTransformer(show_locals=False)
            transformed = transformer((exc_val.type, exc_val.value, exc_val.traceback))
            map_to_log["extra"]["exc_stack"] = transformed
        return orjson.dumps(map_to_log, default=serialize_any).decode()
    except Exception:
        return orjson.dumps(default_map_to_log, default=serialize_any).decode()


def record_formatter(record: dict[str, Any]) -> str:
    """Format log record with structured output.

    In Kubernetes: output JSON to stdout for log aggregation.
    Otherwise: human-readable format with trace/span IDs.
    """
    name = "{name}" if "name" not in record["extra"] else "{extra[name]}"
    line = "{line}" if "_lineno" not in record["extra"] else "{extra[_lineno]}"
    function = "{function}" if "_funcname" not in record["extra"] else "{extra[_funcname]}"
    if "serialized" not in record["extra"]:
        record["extra"]["serialized"] = ""

    if is_in_k8s():
        log_format = "{extra[serialized]}\n"
    else:
        log_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "| <level>{level: <8}</level> "
            r"| <level>{message}</level> | <yellow>serialized: {extra[serialized]}</yellow>"
            f"| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
            "| <magenta>trace_id={extra[trace_id]}</magenta> "
            "| <blue>span_id={extra[span_id]}</blue>\n"
        )
        if record["exception"]:
            log_format = f"{log_format}\n" + "{exception}"

    return log_format


def configure_loguru(level: str = "INFO") -> Logger:
    """Configure and return loguru logger.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).

    Returns:
        Configured Logger instance.
    """
    _logger.remove()
    _logger.add(
        sys.stdout,
        level=level,
        format=record_formatter,  # type: ignore[arg-type]
        enqueue=True,
        catch=True,
    )
    return _logger.patch(record_dict_enricher)  # type: ignore[return-value,arg-type]


app_logger = configure_loguru()
intercept_handler = InterceptHandler(_logger=app_logger)


def patch_logging() -> None:
    """Patch standard logging to use loguru intercept handler."""
    logging.basicConfig(handlers=[intercept_handler], level=logging.NOTSET, force=True)


def patch_uvicorn_logger() -> None:
    """Patch uvicorn loggers to use loguru."""
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        logger_obj = logging.getLogger(logger_name)
        logger_obj.handlers = [intercept_handler]
        logger_obj.propagate = False  # Prevent duplicate logs


def patch_gunicorn_logger() -> None:
    """Patch gunicorn loggers to use loguru."""
    logging.getLogger("gunicorn").handlers = [intercept_handler]
    logging.getLogger("gunicorn.access").handlers = [intercept_handler]
    logging.getLogger("gunicorn.error").handlers = [intercept_handler]


# Apply patches at module import time
patch_logging()
patch_uvicorn_logger()
patch_gunicorn_logger()


def get_logger(name: str | None = None) -> Logger:
    """Get logger instance, optionally bound to a name.

    Args:
        name: Optional logger name for namespacing.

    Returns:
        Logger instance.
    """
    return app_logger.bind(name=name)  # type: ignore[no-untyped-call,no-any-return]


class Level(StrEnum):
    """Log level enum matching loguru levels."""

    TRACE = _logger.level("TRACE").name
    DEBUG = _logger.level("DEBUG").name
    INFO = _logger.level("INFO").name
    WARN = _logger.level("WARNING").name
    WARNING = _logger.level("WARNING").name
    ERROR = _logger.level("ERROR").name
    CRITICAL = _logger.level("CRITICAL").name


R = TypeVar("R")
P = ParamSpec("P")


def _log_context_dict(
    *, extracts: list[str] | None = None, keyw_args: Mapping[str, Any]
) -> dict[str, Any]:
    """Extract specified keys from kwargs for log context."""
    return {arg: keyw_args.get(arg) for arg in extracts or []}


def log_context(
    *,
    from_kwargs: list[str] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to add log context to async/sync functions.

    Args:
        from_kwargs: List of parameter names to extract into log context.

    Returns:
        Decorated function with contextual logging.
    """

    def log_context_decorator(func: Callable[P, R]) -> Callable[P, R]:
        if not from_kwargs:
            return func

        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                async def async_run(*args: P.args, **kwargs: P.kwargs) -> Any:
                    with app_logger.contextualize(
                        **_log_context_dict(extracts=from_kwargs, keyw_args=kwargs)
                    ):
                        return await func(*args, **kwargs)

                return cast("R", async_run(*args, **kwargs))

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with app_logger.contextualize(
                **_log_context_dict(extracts=from_kwargs, keyw_args=kwargs)
            ):
                return func(*args, **kwargs)

        return sync_wrapper

    return log_context_decorator
