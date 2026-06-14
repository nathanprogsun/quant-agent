"""Verify committed DC42 knowledge base artifacts exist on disk."""

from __future__ import annotations

from app.core.dc42.paths import (
    DEFAULT_CHROMA_PATH,
    DEFAULT_DC42_DATA_DIR,
    DEFAULT_DC42_DB_PATH,
    DEFAULT_PARAMETER_LIMITS_PATH,
)


def test_dc42_artifacts_exist() -> None:
    assert DEFAULT_DC42_DATA_DIR.is_dir()
    assert DEFAULT_DC42_DB_PATH.is_file()
    assert DEFAULT_CHROMA_PATH.is_dir()
    assert (DEFAULT_CHROMA_PATH / "chroma.sqlite3").is_file()


def test_dc42_parameter_limits_present() -> None:
    assert DEFAULT_PARAMETER_LIMITS_PATH.is_file()


def test_dc42_db_has_strategies() -> None:
    import sqlite3

    with sqlite3.connect(str(DEFAULT_DC42_DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM dc42_strategies")
        (count,) = cursor.fetchone()
    assert count > 0


async def test_default_retriever_search_returns_results() -> None:
    from app.core.dc42.retriever import create_default_retriever

    retriever = create_default_retriever()
    result = await retriever.retrieve_by_intent("小市值")
    assert result.chunks
