"""Web lifespan management - startup and shutdown.

Handles application context setup (database engine, services)
and cleanup on shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, cast

import anyio
import httpx
import prometheus_fastapi_instrumentator
from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    TELEMETRY_SDK_LANGUAGE,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider

from app.app_context.app_context import AppContext, LifeSpanService, create_checkpointer
from app.app_logging import get_logger
from app.common.runs.manager import RunManager
from app.common.stats.metric import custom_metric
from app.common.stream_bridge.memory import MemoryStreamBridge
from app.core.auth.service.auth_service import get_auth_service_by_engine
from app.core.chat.middlewares.memory_middleware import set_memory_middleware_engine
from app.core.chat.service.thread_service import get_thread_service_by_engine
from app.core.user.service.user_service import get_user_service_by_engine
from app.db.dbengine.core import DatabaseEngine
from app.settings import get_settings, settings
from app.util.asyncio_util.adapter import run_in_pool

logger = get_logger()


# Configure logging for apscheduler (suppress its verbose logging)
logging.basicConfig(level=logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)


def init_default_anyio_limiter() -> anyio.CapacityLimiter:
    """Initialize the default thread pool limiter for sync routes.

    FastAPI runs synchronous route handlers and dependencies in a
    thread pool. This sets the pool size.

    Returns:
        Configured CapacityLimiter.
    """
    system_threadpool_limiter = anyio.to_thread.current_default_thread_limiter()
    system_threadpool_limiter.total_tokens = settings.default_main_thread_pool_size
    return system_threadpool_limiter


def set_app_context(app: FastAPI, app_context: AppContext) -> None:
    """Store AppContext in app state.

    Args:
        app: FastAPI application.
        app_context: AppContext to store.
    """
    app.state.app_context = app_context


def get_app_context(app: FastAPI) -> AppContext | None:
    """Retrieve AppContext from app state.

    Args:
        app: FastAPI application.

    Returns:
        AppContext if set, None otherwise.
    """
    return cast("AppContext | None", getattr(app.state, "app_context", None))


async def setup_app_context(app: FastAPI) -> None:
    """Set up application context at startup.

    Creates:
    - DatabaseEngine with connection pool
    - Shared HTTP AsyncClient
    - All services via LifeSpanService

    Args:
        app: FastAPI application.
    """
    cfg = get_settings()

    # Create database engine
    engine = DatabaseEngine(
        url=str(cfg.database_url),
        echo=cfg.db_echo,
        pool_size=cfg.db_pool_size,
        max_overflow=cfg.db_max_overflow,
    )

    # Initialize memory middleware with database engine
    set_memory_middleware_engine(engine)

    # Pre-warm connection pool if configured
    if cfg.db_conn_prewarm:
        logger.info("Pre-warming database connection pool")  # type: ignore[no-untyped-call]
        await engine.prewarm_db_connection()

    # Checkpointer stays open for the app lifetime via AsyncExitStack (closed on shutdown).
    lifespan_exit_stack = AsyncExitStack()
    checkpointer = await create_checkpointer(
        lifespan_exit_stack,
        backend=cfg.checkpointer_backend,
        connection_string=cfg.checkpointer_connection_string,
    )

    # StreamBridge
    stream_bridge = MemoryStreamBridge(queue_maxsize=cfg.stream_bridge_queue_maxsize)
    # RunManager
    run_manager = RunManager()

    # Create shared HTTP client
    http_aclient = httpx.AsyncClient()

    # Create lifespan service with all services
    lifespan_service = LifeSpanService(
        auth_service=get_auth_service_by_engine(db_engine=engine),
        user_service=get_user_service_by_engine(db_engine=engine),
        thread_service=get_thread_service_by_engine(db_engine=engine),
    )

    # Create and store app context
    app_context = AppContext(
        main_db=engine,
        http_aclient=http_aclient,
        lifespan_service=lifespan_service,
        checkpointer=checkpointer,
        stream_bridge=stream_bridge,
        run_manager=run_manager,
        lifespan_exit_stack=lifespan_exit_stack,
    )
    set_app_context(app=app, app_context=app_context)
    logger.info("Application context initialized")  # type: ignore[no-untyped-call]


async def close_app_context(app: FastAPI) -> None:
    """Close application context at shutdown.

    Closes database engine and HTTP client.

    Args:
        app: FastAPI application.
    """
    app_context = get_app_context(app=app)
    if app_context:
        await app_context.close()
        logger.info("Application context closed")  # type: ignore[no-untyped-call]


def setup_opentelemetry(app: FastAPI) -> None:  # pragma: no cover
    """Enable OpenTelemetry instrumentation.

    Args:
        app: FastAPI application.
    """
    if not settings.opentelemetry_endpoint:
        return

    tracer_provider = TracerProvider(
        resource=Resource(
            attributes={
                SERVICE_NAME: settings.app_name,
                TELEMETRY_SDK_LANGUAGE: "python",
                DEPLOYMENT_ENVIRONMENT: settings.environment,
            },
        ),
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=settings.opentelemetry_endpoint,
                insecure=True,
            ),
        ),
    )

    excluded_endpoints = [
        app.url_path_for("health_check"),
        app.url_path_for("openapi"),
        app.url_path_for("swagger_ui_html"),
        app.url_path_for("swagger_ui_redirect"),
        app.url_path_for("redoc_html"),
        "/metrics",
    ]

    FastAPIInstrumentor().instrument_app(
        app,
        tracer_provider=tracer_provider,
        excluded_urls=",".join(excluded_endpoints),
    )
    set_tracer_provider(tracer_provider=tracer_provider)


def stop_opentelemetry(app: FastAPI) -> None:  # pragma: no cover
    """Disable OpenTelemetry instrumentation.

    Args:
        app: FastAPI application.
    """
    if not settings.opentelemetry_endpoint:
        return

    FastAPIInstrumentor().uninstrument_app(app)


def setup_prometheus(app: FastAPI) -> None:  # pragma: no cover
    """Enable Prometheus metrics instrumentation.

    Args:
        app: FastAPI application.
    """
    prometheus_fastapi_instrumentator.PrometheusFastApiInstrumentator(should_group_status_codes=False).instrument(app).expose(  # type: ignore[attr-defined]
        app, should_gzip=True, name="prometheus_metrics"
    )


async def _gauge_event_loop(interval: float = 1.0) -> None:
    """Monitor event loop delay and task count.

    Args:
        interval: Sampling interval in seconds.
    """
    while True:
        start_time = time.perf_counter()
        await asyncio.sleep(interval)
        actual_time = time.perf_counter()
        delay = max(actual_time - start_time - interval, 0)
        custom_metric.gauge("event_loop_delay", delay)
        custom_metric.gauge("event_loop_tasks", len(asyncio.all_tasks()))


ONE_MILLI_SECOND_FLOAT = 0.001


async def _gauge_anyio_threadpool(
    interval: float = 1.0,
    name: str = "worker",
    limiter: anyio.CapacityLimiter | None = None,
) -> None:
    """Monitor anyio thread pool utilization.

    Args:
        interval: Sampling interval in seconds.
        name: Pool name for metrics.
        limiter: CapacityLimiter to monitor.
    """
    if limiter is None:
        limiter = anyio.to_thread.current_default_thread_limiter()

    while True:
        start_time = time.perf_counter()
        await run_in_pool(time.sleep, ONE_MILLI_SECOND_FLOAT, __anyio_limiter=limiter)
        actual_time = time.perf_counter()
        delay = max(actual_time - start_time - ONE_MILLI_SECOND_FLOAT, 0)

        custom_metric.gauge(f"anyio_{name}_delay", delay)
        utilization = limiter.borrowed_tokens / limiter.total_tokens
        custom_metric.gauge(f"anyio_{name}_utilization", utilization)

        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, Any]:
    """FastAPI lifespan context manager.

    Handles startup (setup_app_context) and shutdown (close_app_context).
    Also sets up background monitoring tasks.

    Args:
        app: FastAPI application.

    Yields:
        Control to application.
    """
    task_gauge_event_loop = None
    task_gauge_anyio_worker = None
    task_gauge_anyio_system = None

    try:
        # Initialize middleware stack before context setup
        app.middleware_stack = None
        await setup_app_context(app=app)
        app.middleware_stack = app.build_middleware_stack()

        # Configure thread pool (keep reference to prevent garbage collection)
        init_default_anyio_limiter()

        # Optional instrumentation (commented out by default)
        # task_gauge_event_loop = asyncio.create_task(
        #     _gauge_event_loop(), name="_task_gauge_event_loop"
        # )

        logger.info("Application lifespan started")  # type: ignore[no-untyped-call]

        yield
    except Exception:
        logger.exception("Failed to setup application lifespan")  # type: ignore[no-untyped-call]
        raise
    finally:
        # Cleanup
        await close_app_context(app=app)

        if task_gauge_event_loop:
            task_gauge_event_loop.cancel()
        if task_gauge_anyio_worker:
            task_gauge_anyio_worker.cancel()
        if task_gauge_anyio_system:
            task_gauge_anyio_system.cancel()

        logger.info("Application lifespan ended")  # type: ignore[no-untyped-call]
