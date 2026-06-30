"""Web lifespan management - startup and shutdown.

Handles application context setup (database engine, services)
and cleanup on shutdown.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.app_context.app_context import AppContext, create_checkpointer
from app.app_logging import get_logger
from app.common.runs.manager import RunManager
from app.common.stream_bridge.memory import MemoryStreamBridge
from app.core.backtest.jqcli_auth import JqcliNotConfiguredError, resolve_jqcli_credentials
from app.core.backtest.registry import BacktestRegistry
from app.core.chat.middlewares.memory_middleware import set_memory_middleware_session_factory
from app.core.chat.skills.registry import SkillRegistry
from app.core.jq_kb.embeddings import warm_up_models
from app.db.models import Base
from app.db.session import make_engine, make_session_factory
from app.settings import get_settings
from app.util.asyncio_util.adapter import run_in_pool

logger = get_logger()

# Configure logging for apscheduler (suppress its verbose logging)
logging.basicConfig(level=logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)


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
    - AsyncEngine + session factory with schema auto-create
    - Shared HTTP AsyncClient
    - All services via LifeSpanService

    Args:
        app: FastAPI application.
    """
    cfg = get_settings()

    # Create AsyncEngine + session factory
    engine: AsyncEngine = make_engine(url=str(cfg.database_url), echo=cfg.db_echo)
    session_factory = make_session_factory(engine)

    # Initialize schema (replaces alembic upgrade head)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
    # BacktestRegistry — process-level ownership registry shared across requests
    backtest_registry = BacktestRegistry()

    set_memory_middleware_session_factory(session_factory)

    # Create and store app context
    app_context = AppContext(
        session_factory=session_factory,
        checkpointer=checkpointer,
        stream_bridge=stream_bridge,
        run_manager=run_manager,
        skill_registry=SkillRegistry(),
        backtest_registry=backtest_registry,
        lifespan_exit_stack=lifespan_exit_stack,
    )
    set_app_context(app=app, app_context=app_context)
    logger.info("Application context initialized")


async def close_app_context(app: FastAPI) -> None:
    """Close application context at shutdown.

    Closes database engine and HTTP client.

    Args:
        app: FastAPI application.
    """
    app_context = get_app_context(app=app)
    if app_context:
        await app_context.close()
        logger.info("Application context closed")


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
    try:
        # Initialize middleware stack before context setup
        app.middleware_stack = None
        await setup_app_context(app=app)
        app.middleware_stack = app.build_middleware_stack()

        try:
            await run_in_pool(warm_up_models)
            logger.info("jq_kb models warmed up")
        except FileNotFoundError as exc:
            # Models not downloaded — log and continue. First request will
            # surface the install hint in the tool error.
            logger.warning("jq_kb warm-up skipped: %s", exc)

        try:
            await run_in_pool(resolve_jqcli_credentials)
            logger.info("jqcli credentials warmed up")
        except JqcliNotConfiguredError:
            pass
        except Exception:
            logger.warning("jqcli credential warmup failed", exc_info=True)

        logger.info("Application lifespan started")

        yield
    except Exception:
        logger.exception("Failed to setup application lifespan")
        raise
    finally:
        # Cleanup
        await close_app_context(app=app)

        logger.info("Application lifespan ended")
