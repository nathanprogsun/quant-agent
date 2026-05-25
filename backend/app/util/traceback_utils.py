"""Traceback utilities for exception serialization."""

from __future__ import annotations

from typing import Any


class ExceptionDictTransformer:
    """Transform exception info into a serializable dict.

    Used for logging exceptions with structured data.
    """

    def __init__(self, show_locals: bool = False) -> None:
        """Initialize transformer.

        Args:
            show_locals: Whether to include local variables in traceback.
        """
        self.show_locals = show_locals

    def __call__(
        self,
        exc_info: tuple[type[BaseException], BaseException, Any],
    ) -> dict[str, Any]:
        """Transform exception info into dict.

        Args:
            exc_info: (type, value, traceback) tuple from sys.exc_info().

        Returns:
            Dict with exception type, message, and optionally traceback.
        """
        exc_type, exc_value, exc_tb = exc_info
        result: dict[str, Any] = {
            "type": exc_type.__name__ if exc_type else None,
            "message": str(exc_value) if exc_value else None,
        }

        if exc_tb and self.show_locals:
            frames = []
            while exc_tb:
                frame_info = {
                    "filename": exc_tb.tb_frame.f_code.co_filename,
                    "lineno": exc_tb.tb_lineno,
                    "function": exc_tb.tb_frame.f_code.co_name,
                }
                if self.show_locals:
                    frame_info["locals"] = {k: str(v) for k, v in exc_tb.tb_frame.f_locals.items()}
                frames.append(frame_info)
                exc_tb = exc_tb.tb_next
            result["traceback"] = frames

        return result
