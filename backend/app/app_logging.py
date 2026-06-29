"""Application logging configuration."""

from __future__ import annotations

import logging
import sys

LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(message)s | %(name)s:%(funcName)s:%(lineno)d"
)
FORMATTER = logging.Formatter(LOG_FORMAT)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with a single stdout handler."""
    root = logging.getLogger()
    if root.handlers:
        return

    resolved = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(resolved)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(resolved)
    handler.setFormatter(FORMATTER)
    root.addHandler(handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a stdlib logger."""
    return logging.getLogger(name or "app")


configure_logging()
