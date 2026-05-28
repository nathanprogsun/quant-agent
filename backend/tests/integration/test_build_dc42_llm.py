"""DC42 build pipeline — LLM enrichment steps (mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from scripts.build_dc42 import llm_enrich, llm_experience, llm_relations


@pytest.fixture
def sample_extracted() -> list[dict[str, Any]]:
    return [
        {
            "hash": "abc123",
            "strategy_name": "小市值策略",
            "year_bucket": "2022",
            "code_status": "ok",
            "code": "import jqdatastd as jq\n\ndef initialize(context):\n    context.stock_count = 5",
            "description": "选取市值最小的5只股票",
        },
    ]


MOCK_L2_RESPONSE = json.dumps({
    "type": "small_cap",
    "factors": ["market_cap"],
    "parameters": {"stock_count": 5},
    "code_logic": "select smallest market cap stocks",
})

MOCK_L3_RESPONSE = json.dumps({
    "experience": "小市值策略在牛市表现好，熊市回撤大",
    "failure_modes": ["流动性风险", "市值陷阱"],
    "boundary_text": "建议止损线10%",
})

MOCK_L4_RESPONSE = json.dumps({
    "similar": ["abc124"],
    "derived": [],
    "complementary": ["abc125"],
    "substitute": [],
})


def _make_llm_call(response_text: str) -> AsyncMock:
    """Create a mock LLM callable that returns a response with .content."""
    response = AsyncMock()
    response.content = response_text
    llm_call = AsyncMock(return_value=response)
    return llm_call


@pytest.mark.asyncio
async def test_llm_enrich_produces_l2(sample_extracted: list, tmp_path: Path) -> None:
    """03_llm_enrich should produce L2 metadata via LLM."""
    mock_llm = _make_llm_call(MOCK_L2_RESPONSE)

    results = await llm_enrich(
        extracted=sample_extracted,
        llm_call=mock_llm,
        output_dir=tmp_path,
        concurrency=1,
    )

    assert len(results) == 1
    assert results[0]["l2_type"] == "small_cap"
    assert results[0]["l2_factors"] == ["market_cap"]
    mock_llm.assert_called_once()


@pytest.mark.asyncio
async def test_llm_experience_produces_l3(sample_extracted: list, tmp_path: Path) -> None:
    """04_llm_experience should produce L3 experience layer."""
    enriched = [{**sample_extracted[0], "l2_type": "small_cap", "l2_factors": ["market_cap"]}]

    mock_llm = _make_llm_call(MOCK_L3_RESPONSE)

    results = await llm_experience(
        enriched=enriched,
        llm_call=mock_llm,
        output_dir=tmp_path,
        concurrency=1,
    )

    assert len(results) == 1
    assert "experience" in results[0]
    assert len(results[0]["failure_modes"]) > 0


@pytest.mark.asyncio
async def test_llm_relations_produces_l4(sample_extracted: list, tmp_path: Path) -> None:
    """05_llm_relations should produce L4 relation layer."""
    enriched = [{**sample_extracted[0], "l2_type": "small_cap", "experience": "test"}]

    mock_llm = _make_llm_call(MOCK_L4_RESPONSE)

    results = await llm_relations(
        enriched=enriched,
        llm_call=mock_llm,
        output_dir=tmp_path,
        concurrency=1,
    )

    assert len(results) == 1
    assert "l4_similar" in results[0]
    assert isinstance(results[0]["l4_similar"], list)


@pytest.mark.asyncio
async def test_llm_enrich_respects_concurrency_limit(sample_extracted: list, tmp_path: Path) -> None:
    """Concurrency semaphore should limit parallel LLM calls."""
    call_count = 0

    async def counting_invoke(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        response = AsyncMock()
        response.content = MOCK_L2_RESPONSE
        return response

    mock_llm = AsyncMock(side_effect=counting_invoke)

    # 5 items, concurrency=2 → max 2 concurrent
    items = [{**sample_extracted[0], "hash": f"hash{i}"} for i in range(5)]
    results = await llm_enrich(
        extracted=items,
        llm_call=mock_llm,
        output_dir=tmp_path,
        concurrency=2,
    )

    assert len(results) == 5
    assert call_count == 5
