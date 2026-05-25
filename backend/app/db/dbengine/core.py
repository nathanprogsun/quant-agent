"""Database engine with connection pooling and transaction management."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import weakref
from typing import TYPE_CHECKING, Any, Self, cast

from app.db.dbengine.util import create_async_engine

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from inspect import Traceback

    from sqlalchemy import Executable, Result, Row
    from sqlalchemy.engine.interfaces import (
        CoreExecuteOptionsParameter,
        _CoreAnyExecuteParams,
    )
    from sqlalchemy.ext.asyncio import (
        AsyncConnection,
        AsyncTransaction,
    )
    from sqlalchemy.pool import AsyncAdaptedQueuePool

logger = logging.getLogger(__name__)


class DatabaseEngine:
    """Async database engine wrapper."""

    def __init__(
        self,
        url: str,
        *,
        pool_size: int = 1,
        max_overflow: int = 5,
        echo: bool = False,
        pool_recycle: int = 43200,
    ):
        self.engine = create_async_engine(
            url=url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
        )
        self._connection_map: weakref.WeakKeyDictionary[asyncio.Task[Any], Connection] = (
            weakref.WeakKeyDictionary()
        )
        self._closed: bool = False
        self._connection_acquire_lock: asyncio.Lock = asyncio.Lock()

    @property
    def closed(self) -> bool:
        return self._closed

    async def prewarm_db_connection(self) -> None:
        """Pre-warm the connection pool.

        Acquires and releases connections up to pool maxsize to ensure
        the pool is ready for incoming requests.
        """
        logger.info("Pre-warming database connection pool")
        connections: list[AsyncConnection] = []
        conn_pool: AsyncAdaptedQueuePool = cast("AsyncAdaptedQueuePool", self.engine.pool)

        for _ in range(conn_pool._pool.maxsize):
            conn = await self.engine.connect()
            connections.append(conn)
        for conn in connections:
            await conn.close()
        logger.info("Connection pool pre-warmed")

    @property
    def _current_task(self) -> asyncio.Task[Any]:
        task = asyncio.current_task()
        if not task:
            raise RuntimeError("no asyncio.Task is running")
        return task

    @property
    def _connection(self) -> Connection | None:
        return self._connection_map.get(self._current_task)

    @_connection.setter
    def _connection(self, connection: Connection | None) -> None:
        task = self._current_task
        if connection is None:
            self._connection_map.pop(task, None)
        else:
            self._connection_map[task] = connection

    async def close(self) -> None:
        if not self.closed:
            await self.engine.dispose()
            self._closed = True

    async def _connect(self) -> Connection:
        if self.closed:
            raise RuntimeError("Connection pool already closed")
        async with self._connection_acquire_lock:
            if not self._connection:
                self._connection = Connection(raw_connection=self.engine.connect(), engine=self)
            return self._connection

    @contextlib.asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        connection = await self._connect()
        async with connection._begin():
            yield

    async def execute(
        self,
        statement: Executable,
        parameters: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: CoreExecuteOptionsParameter | None = None,
    ) -> Result[Any]:
        connection = await self._connect()
        async with connection as conn:
            return await conn._execute(statement, parameters, execution_options=execution_options)

    async def all(
        self,
        statement: Executable,
        parameters: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: CoreExecuteOptionsParameter | None = None,
    ) -> Sequence[Row[Any]]:
        connection = await self._connect()
        async with connection as conn:
            return await conn._all(statement, parameters, execution_options=execution_options)

    async def at_most_one(
        self,
        statement: Executable,
        parameters: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: CoreExecuteOptionsParameter | None = None,
    ) -> Row[Any] | None:
        connection = await self._connect()
        async with connection as conn:
            return await conn._at_most_one(
                statement, parameters, execution_options=execution_options
            )

    async def one(
        self,
        statement: Executable,
        parameters: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: CoreExecuteOptionsParameter | None = None,
    ) -> Row[Any]:
        connection = await self._connect()
        async with connection as conn:
            return await conn._one(statement, parameters, execution_options=execution_options)

    async def first_or_none(
        self,
        statement: Executable,
        parameters: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: CoreExecuteOptionsParameter | None = None,
    ) -> Row[Any] | None:
        connection = await self._connect()
        async with connection as conn:
            return await conn._first_or_none(
                statement, parameters, execution_options=execution_options
            )


class Transaction:
    def __init__(self, connection: Connection):
        self._connection = connection
        self._raw_transaction: AsyncTransaction | None = None

    async def __aenter__(self) -> None:
        async with self._connection.transaction_lock:
            if self._connection.active_transaction:
                raise RuntimeError("only one active transaction is allowed per connection")
            await self._connection.__aenter__()
            self._raw_transaction = await self._connection.raw_connection.begin()
            self._connection.active_transaction = self

    async def __aexit__(
        self,
        exc_type: type[Exception] | None,
        exc_val: Exception | None,
        exc_tb: Traceback | None,
    ) -> None:
        async with self._connection.transaction_lock:
            try:
                if self._raw_transaction:
                    if exc_val:
                        await self._raw_transaction.rollback()
                    else:
                        await self._raw_transaction.commit()
            finally:
                await self._connection.__aexit__(exc_type, exc_val, exc_tb)
                self._connection.active_transaction = None
                self._raw_transaction = None


class Connection:
    def __init__(self, raw_connection: AsyncConnection, engine: DatabaseEngine):
        self._engine = engine
        self._raw_connection = raw_connection
        self._connection_lock: asyncio.Lock = asyncio.Lock()
        self._transaction_lock: asyncio.Lock = asyncio.Lock()
        self._query_lock: asyncio.Lock = asyncio.Lock()
        self._connection_count: int = 0
        self._active_transaction: Transaction | None = None

    @property
    def id(self) -> str:
        if self._raw_connection.sync_connection:
            return f"[{id(self)} -> {id(self._raw_connection.sync_connection)}]"
        return f"[{id(self)} -> uninitialized]"

    @property
    def transaction_lock(self) -> asyncio.Lock:
        return self._transaction_lock

    @property
    def raw_connection(self) -> AsyncConnection:
        return self._raw_connection

    @property
    def active_transaction(self) -> Transaction | None:
        return self._active_transaction

    @active_transaction.setter
    def active_transaction(self, transaction: Transaction | None) -> None:
        self._active_transaction = transaction

    async def __aenter__(self) -> Self:
        async with self._connection_lock:
            if not self._raw_connection.sync_connection:
                await self._raw_connection.__aenter__()
            elif self._raw_connection.closed:
                raise RuntimeError("connection already closed")
            self._connection_count += 1
            return self

    async def __aexit__(
        self,
        exc_type: type[Exception] | None,
        exc_val: Exception | None,
        exc_tb: Traceback | None,
    ) -> None:
        async with self._connection_lock:
            try:
                if not self.active_transaction:
                    if exc_val:
                        await self._raw_connection.rollback()
                    else:
                        await self._raw_connection.commit()
            finally:
                if self._connection_count == 1:
                    await self._raw_connection.__aexit__(exc_type, exc_val, exc_tb)
                    self._engine._connection = None
                self._connection_count -= 1

    def _begin(self) -> Transaction:
        return Transaction(connection=self)

    async def _execute(
        self,
        statement: Executable,
        parameters: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: CoreExecuteOptionsParameter | None = None,
    ) -> Result[Any]:
        async with self._query_lock:
            return await self._raw_connection.execute(
                statement, parameters, execution_options=execution_options
            )

    async def _all(
        self,
        statement: Executable,
        parameters: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: CoreExecuteOptionsParameter | None = None,
    ) -> Sequence[Row[Any]]:
        result = await self._execute(statement, parameters, execution_options=execution_options)
        return result.all()

    async def _at_most_one(
        self,
        statement: Executable,
        parameters: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: CoreExecuteOptionsParameter | None = None,
    ) -> Row[Any] | None:
        result = await self._execute(statement, parameters, execution_options=execution_options)
        return result.one_or_none()

    async def _one(
        self,
        statement: Executable,
        parameters: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: CoreExecuteOptionsParameter | None = None,
    ) -> Row[Any]:
        result = await self._execute(statement, parameters, execution_options=execution_options)
        return result.one()

    async def _first_or_none(
        self,
        statement: Executable,
        parameters: _CoreAnyExecuteParams | None = None,
        *,
        execution_options: CoreExecuteOptionsParameter | None = None,
    ) -> Row[Any] | None:
        result = await self._execute(statement, parameters, execution_options=execution_options)
        return result.first()
