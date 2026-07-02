"""Model-layer probe: time ainvoke vs astream in isolation.

Bypasses the entire graph/middleware/bridge layer. Goes directly to the
ChatOpenAI client that the production agent uses. Two timings are taken
for the same query:

  ainvoke_ttft ≈ ainvoke_total (it's a single blocking call)
  astream_ttft  = time to first chunk
  astream_total = time to full response

If ainvoke_ttft is ~25s and astream_ttft is ~1-3s on the same query,
the bug is confirmed to be in lead_agent.py's call site, not the model
itself.
"""

from __future__ import annotations

import os
import time

import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.settings import get_settings


def _should_run() -> bool:
    return os.environ.get("RUN_TTFT_REPRO") == "1"


# Same query as test_ttft_full_repro
QUERY = (
    "List the prime numbers between 1 and 30 one per line, "
    "then write a single line with the sum of those primes. "
    "Show your reasoning step by step."
)


def _build_model() -> ChatOpenAI:
    """Build the exact same ChatOpenAI that make_lead_agent builds."""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.model,
        api_key=SecretStr(settings.openai_api_key.get_secret_value()),
        base_url=settings.openai_base_url,
        streaming=True,
        extra_body={"reasoning_split": True},
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _should_run(),
    reason="Diagnostic only — export RUN_TTFT_REPRO=1 to enable",
)
async def test_model_layer_ainvoke_vs_astream() -> None:
    settings = get_settings()
    print(f"[diag-probe] model={settings.model} base={settings.openai_base_url}")

    model = _build_model()
    msgs = [HumanMessage(content=QUERY)]

    # 1) ainvoke — single blocking call
    t0 = time.perf_counter()
    resp = await model.ainvoke(msgs)
    ainvoke_total = time.perf_counter() - t0
    n_chars = len(getattr(resp, "content", "") or "")
    print(f"[diag-probe] ainvoke total={ainvoke_total:.3f}s chars={n_chars}")
    print(f"[diag-probe] ainvoke_content[:120]={str(resp.content)[:120]!r}")

    # 2) astream — measure TTFT to first chunk and total
    t0 = time.perf_counter()
    first_chunk_time: float | None = None
    chunk_count = 0
    last_content = ""
    async for chunk in model.astream(msgs):
        now = time.perf_counter()
        if first_chunk_time is None:
            first_chunk_time = now
            print(
                f"[diag-probe] first_chunk at "
                f"{now - t0:.3f}s content[:80]={str(getattr(chunk, 'content', chunk))[:80]!r}"
            )
        chunk_count += 1
        last_content = getattr(chunk, "content", "") or last_content

    astream_total = time.perf_counter() - t0
    astream_ttft = (first_chunk_time - t0) if first_chunk_time is not None else None

    print(
        f"[diag-probe] astream ttft="
        f"{astream_ttft:.3f}s total={astream_total:.3f}s chunks={chunk_count}"
        if astream_ttft is not None
        else f"[diag-probe] astream total={astream_total:.3f}s chunks={chunk_count}"
    )

    print(
        f"[diag-probe] RESULT: ainvoke={ainvoke_total:.3f}s "
        f"astream_ttft={astream_ttft!r}s "
        f"delta_total={astream_total - ainvoke_total:+.3f}s"
    )
