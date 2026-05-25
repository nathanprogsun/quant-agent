"""No-op DogStatsD client for local development and testing.

This module provides a stub implementation of the DogStatsD client interface
that can be used when Datadog is not available or not configured.
"""

from typing import Any

__all__ = ["NoopDogStatsD"]


class NoopDogStatsD:
    """No-operation DogStatsD client stub.

    This class provides a no-op implementation of the DogStatsD client
    for use in development environments where Datadog is not available.
    All methods are no-ops that do nothing.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the no-op client.

        Args:
            **kwargs: Any arguments are accepted but ignored.
        """

    def gauge(self, *args: Any, **kwargs: Any) -> None:
        """No-op gauge metric."""

    def increment(self, *args: Any, **kwargs: Any) -> None:
        """No-op counter increment."""

    def decrement(self, *args: Any, **kwargs: Any) -> None:
        """No-op counter decrement."""

    def histogram(self, *args: Any, **kwargs: Any) -> None:
        """No-op histogram metric."""

    def distribution(self, *args: Any, **kwargs: Any) -> None:
        """No-op distribution metric."""

    def timing(self, *args: Any, **kwargs: Any) -> None:
        """No-op timing metric."""

    def timed(self, *args: Any, **kwargs: Any) -> Any:
        """No-op timed decorator/context manager.

        This decorator passes through the decorated function without timing.
        """

        def decorator(func: Any) -> Any:
            return func

        return decorator

    def set(self, *args: Any, **kwargs: Any) -> None:
        """No-op set metric."""

    def close(self) -> None:
        """No-op close method."""

    def start_service_check(self, *args: Any, **kwargs: Any) -> None:
        """No-op service check start."""

    def stop_service_check(self, *args: Any, **kwargs: Any) -> None:
        """No-op service check stop."""

    def service_check(self, *args: Any, **kwargs: Any) -> None:
        """No-op service check."""

    def event(self, *args: Any, **kwargs: Any) -> None:
        """No-op event."""

    def batched(self, *args: Any, **kwargs: Any) -> Any:
        """No-op batched context manager."""

        class NoopBatch:
            def __enter__(self) -> "NoopBatch":
                return self

            def __exit__(self, *args: Any) -> None:
                pass

        return NoopBatch()
