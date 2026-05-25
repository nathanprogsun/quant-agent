"""AsyncIO utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, ParamSpec, TypeVar

import anyio

if TYPE_CHECKING:
    from collections.abc import Callable

P = ParamSpec("P")
R = TypeVar("R")


async def run_in_pool(
    func: Callable[P, R],
    *args: P.args,
    __anyio_limiter: anyio.CapacityLimiter | None = None,
    **kwargs: P.kwargs,
) -> R:
    """Run a blocking function in the thread pool.

    This is a wrapper around anyio.to_thread.run_sync that
    respects a CapacityLimiter for controlling concurrency.

    Args:
        func: Synchronous function to run.
        *args: Positional arguments to pass to func.
        __anyio_limiter: Optional CapacityLimiter to use.
        **kwargs: Keyword arguments to pass to func.

    Returns:
        Result from calling func(*args, **kwargs).
    """
    return await anyio.to_thread.run_sync(
        lambda: func(*args, **kwargs),
        limiter=__anyio_limiter,
    )


def worker_threadpool_limiter() -> anyio.CapacityLimiter:
    """Get the default worker thread pool limiter.

    Returns:
        CapacityLimiter for the worker thread pool.
    """
    return anyio.to_thread.current_default_thread_limiter()
