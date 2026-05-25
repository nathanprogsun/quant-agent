"""Database engine utilities."""

from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from uuid import UUID

import orjson
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import create_async_engine as sac_create_async_engine


def sad_json_serializer(any_value: Any) -> str | None:
    """Serialize value to JSON string for SQLAlchemy."""
    if isinstance(any_value, dict):
        serialized_dict = {k: str(v) if isinstance(v, UUID) else v for k, v in any_value.items()}
        return orjson.dumps(serialized_dict).decode()
    if isinstance(any_value, BaseModel):
        return any_value.model_dump_json()
    if isinstance(any_value, (list, tuple, set)):
        serialized_children = [sad_json_serializer(it) for it in any_value]
        generic_deserialized_children = [
            orjson.loads(chd) if chd else None for chd in serialized_children
        ]
        if isinstance(any_value, list):
            return orjson.dumps(generic_deserialized_children).decode()
        if isinstance(any_value, tuple):
            return orjson.dumps(tuple(generic_deserialized_children)).decode()
        return orjson.dumps(set(generic_deserialized_children)).decode()
    return str(any_value) if any_value is not None else None


def create_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
    """Create async engine with prepared statement cache disabled.

    Args:
        url: Database URL.
        **kwargs: Additional arguments to pass to create_async_engine.

    Returns:
        Configured AsyncEngine instance.
    """
    json_serializer = kwargs.pop("json_serializer", sad_json_serializer)

    # Check if this is a SQLite URL with triple slash (sqlite+aiosqlite:///path)
    is_sqlite = url.startswith("sqlite")

    # SQLite doesn't support pool_size/max_overflow/pool_recycle
    if is_sqlite:
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        kwargs.pop("pool_recycle", None)

    parsed_url = urlparse(url)
    queries = parse_qs(parsed_url.query)
    queries["prepared_statement_cache_size"] = ["0"]
    new_query_string = urlencode(queries, doseq=True)
    new_db_url = str(urlunparse(parsed_url._replace(query=new_query_string)))

    # urlunparse may reduce /// to / for SQLite paths; restore it if needed
    if is_sqlite and ":///" in url and ":///" not in new_db_url:
        new_db_url = new_db_url.replace(":/", ":///", 1)

    return sac_create_async_engine(url=new_db_url, json_serializer=json_serializer, **kwargs)
