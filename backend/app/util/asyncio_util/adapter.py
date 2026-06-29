"""AsyncIO utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, ParamSpec, TypeVar

import anyio

if TYPE_CHECKING:
    from collections.abc import Callable

# PEP 695 generic syntax (`def f[**P, R]`) is rejected by mypy 2.1 when ``P.args``
# / ``P.kwargs`` are used as unpacked parameter annotations. Fall back to the
# classic ParamSpec / TypeVar form so both ruff (UP047) and mypy are happy.
P = ParamSpec("P")
R = TypeVar("R")


async def run_in_pool(  # noqa: UP047
    func: Callable[P, R],
    __anyio_limiter: anyio.CapacityLimiter | None = None,
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """Run a blocking function in the thread pool.

    This is a wrapper around anyio.to_thread.run_sync that
    respects a CapacityLimiter for controlling concurrency.

    Note: ``__anyio_limiter`` is keyword-only and intentionally placed
    before ``*args`` so mypy accepts the ``P.args`` unpack annotation
    (mypy forbids any further params after ``*args: P.args``).

    Args:
        func: Synchronous function to run.
        __anyio_limiter: Optional CapacityLimiter to use.
        *args: Positional arguments to pass to func.
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
