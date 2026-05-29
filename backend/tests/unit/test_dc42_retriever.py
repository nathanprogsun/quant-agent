"""DC42Retriever vector search tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.dc42.retriever import DC42Retriever
from app.core.dc42.types import RetrievalResult


@pytest.fixture
def mock_chroma_collection():
    """Mock ChromaDB collection."""
    collection = MagicMock()
    collection.query.return_value = {
        "ids": [["chunk_1", "chunk_2"]],
        "documents": [["小市值策略: 选取市值最小的股票", "低波动轮动: 低波动率股票轮动"]],
        "metadatas": [[{"strategy_id": "abc", "chunk_type": "intent"}, {"strategy_id": "def", "chunk_type": "intent"}]],
        "distances": [[0.3, 0.5]],
    }
    return collection


@pytest.fixture
def mock_db_path(tmp_path: Path) -> Path:
    """Create a test SQLite DB."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dc42_strategies (id TEXT PRIMARY KEY, name TEXT, type TEXT, parameters TEXT, experience TEXT, failure_modes TEXT)")
    conn.execute("INSERT INTO dc42_strategies VALUES ('abc', '小市值策略', 'small_cap', '{\"n\": 5}', 'bull market works', '[\"liquidity\"]')")
    conn.execute("INSERT INTO dc42_strategies VALUES ('def', '低波动轮动', 'low_vol', '{\"window\": 20}', 'stable returns', '[\"regime change\"]')")
    conn.commit()
    conn.close()
    return db_path


@pytest.mark.asyncio
async def test_retrieve_by_intent_returns_chunks(mock_chroma_collection, mock_db_path):
    """retrieve_by_intent should return relevant strategy chunks."""
    retriever = DC42Retriever(
        collection=mock_chroma_collection,
        db_path=mock_db_path,
    )

    result = await retriever.retrieve_by_intent("小市值稳健策略")

    assert isinstance(result, RetrievalResult)
    assert len(result.chunks) > 0
    assert len(result.strategy_names) > 0
    mock_chroma_collection.query.assert_called_once()


@pytest.mark.asyncio
async def test_retrieve_by_parameters_in_range(mock_db_path):
    """retrieve_by_parameters should flag parameters in DC42 range."""
    retriever = DC42Retriever(
        collection=MagicMock(),
        db_path=mock_db_path,
        parameter_stats={"n": {"P10": 3, "P50": 5, "P90": 20}},
    )

    result = await retriever.retrieve_by_parameters({"n": 8})

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].in_range is True


@pytest.mark.asyncio
async def test_retrieve_by_parameters_out_of_range(mock_db_path):
    """retrieve_by_parameters should flag parameters outside DC42 range."""
    retriever = DC42Retriever(
        collection=MagicMock(),
        db_path=mock_db_path,
        parameter_stats={"n": {"P10": 3, "P50": 5, "P90": 20}},
    )

    result = await retriever.retrieve_by_parameters({"n": 100})

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].in_range is False
